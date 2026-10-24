"""
Main Window GUI Module
Primary application window with text input, controls, and status display.
"""

import customtkinter as ctk
import threading
import tkinter as tk
from typing import Callable, Optional
import os
import logging

from collections import OrderedDict

from ..tts.text_preprocessor import TextPreprocessor
from ..gui.keybind_manager import KeybindManager
from ..vrchat import VRChatOSCClient
from ..vrchat.viseme_mapper import VisemeMapper, AmplitudeAnalyzer
from ..vrchat.chatbox_controller import ChatboxController
from .recording_overlay import RecordingOverlay
from .gui_utils import (
    STTState,
    LatestWinsTextAnalysisScheduler,
)
from .mixins.text_editor_mixin import TextEditorMixin
from .mixins.tts_pipeline_mixin import TTSPipelineMixin
from .mixins.stt_mixin import STTMixin
from .mixins.animation_mixin import AnimationMixin
from .mixins.quick_controls_mixin import QuickControlsMixin
from .mixins.integrations_mixin import IntegrationsMixin
from .theme_constants import (
    COLOR_NEUTRAL_LIGHT,
    SPACING_XS,
    FONT_LG,
    BUTTON_HEIGHT,
    BUTTON_HEIGHT_SM,
    SPACING_SM,
    SPACING_MD,
    SPACING_LG,
    COLOR_SUCCESS,
    COLOR_SUCCESS_HOVER,
    COLOR_BG_PRIMARY,
    COLOR_STATUS_IDLE,
    FONT_XS,
    FONT_SM,
    FONT_MD,
    FONT_WEIGHT_BOLD,
    RADIUS_MD,
    WINDOW_MAIN_MIN_WIDTH,
    WINDOW_MAIN_MIN_HEIGHT,
    WINDOW_MAIN_WIDTH,
    WINDOW_MAIN_HEIGHT,
    COLOR_ON_FILL,
    get_active_appearance_mode,
    get_theme_colors,
    neutral_button_style,
    toggle_switch_style,
)


class MainWindow(
    TextEditorMixin,
    TTSPipelineMixin,
    STTMixin,
    AnimationMixin,
    QuickControlsMixin,
    IntegrationsMixin,
):
    """Main application window for CriTTS Recoded."""

    def __init__(
        self,
        root: ctk.CTk,
        settings_manager,
        tts_engine,
        audio_router,
        on_open_settings: Callable,
        icon_path: Optional[str] = None,
        stt_engine=None,
    ):
        """
        Initialize the main window.

        Args:
            root: CustomTkinter root window
            settings_manager: SettingsManager instance
            tts_engine: TTSEngine instance
            audio_router: AudioRouter instance
            on_open_settings: Callback to open settings window
            icon_path: Path to application icon
            stt_engine: STTEngine instance (optional)
        """
        self.root = root
        self.settings = settings_manager
        self.tts_engine = tts_engine
        self.audio_router = audio_router
        self.on_open_settings = on_open_settings
        self.icon_path = icon_path
        self.stt_engine = stt_engine

        self._speaking = False
        self._speaking_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        # Monotonic generation counter for speak operations.  Workers capture
        # their generation and only clear shared state while still current, so a
        # late-finishing worker can't clobber a newer speak.
        self._speak_generation = 0
        # Offloads VRChat voice-amplitude OSC sends off the audio callback thread.
        self._amplitude_forwarder = None
        # Background threads must stop scheduling Tk callbacks before the root
        # window is destroyed.
        self._async_callbacks_active = True

        # TTS speaking animation state
        self._tts_speaking = False
        self._speaking_animation_running = False
        self._speaking_animation_index = 0
        self._speaking_animation_frames = ["▶  Speaking.", "▶  Speaking..", "▶  Speaking..."]

        # STT (Voice Input) state machine
        self._stt_state = STTState.IDLE
        self._stt_timeout_timer = None
        self._STT_TIMEOUT_MS = 30000  # 30 seconds timeout for transcription

        # STT loading animation state
        self._stt_spinner_running = False
        self._stt_spinner_index = 0
        self._stt_spinner_frames = ["⏳", "⌛"]

        # Progress animation state
        self._progress_animation_running = False
        self._progress_animation_index = 0
        self._progress_base_message = ""

        # Abbreviation expansion cache with LRU eviction
        # Uses OrderedDict to implement LRU: most recently used items at the end
        self._abbreviation_cache: OrderedDict = OrderedDict()
        self._abbreviation_cache_max_size = 100

        # Initialize OSC client
        self.osc_client: Optional[VRChatOSCClient] = None

        # Initialize keybind manager
        self.keybind_manager = KeybindManager()

        # Track text-widget-level bindings for keybinds (to override class bindings)
        self._text_widget_bound_sequences = []

        # Initialize viseme mapper for lip-sync
        self._viseme_mapper: Optional[VisemeMapper] = None
        self._amplitude_analyzer: Optional[AmplitudeAnalyzer] = None

        # Typing animation / chatbox state lives in the ChatboxController;
        # the wrappers below keep the original method names for callers/tests.
        self._chatbox = ChatboxController(
            get_client=lambda: self.osc_client,
            settings=self.settings,
            status_cb=self._set_status,
            schedule_cb=self._safe_after,
            cancel_cb=self._cancel_after,
        )

        # Voice indicator debounce timer
        self._voice_indicator_timer = None
        self._voice_indicator_animating = False
        self._voice_indicator_scheduler = LatestWinsTextAnalysisScheduler()

        # Status-label wraplength resize debounce (coalesces <Configure> events)
        self._pending_status_wraplength: Optional[int] = None
        self._status_wraplength_job = None
        self._last_status_wraplength: Optional[int] = None

        # Text preprocessor (reused across speak calls)
        self._text_preprocessor = TextPreprocessor()
        self._text_context_menu: Optional[tk.Menu] = None
        self._text_sound_token_menu: Optional[tk.Menu] = None

        # Recording overlay state
        self._overlay_visible: bool = self.settings.get("overlay_visible", False)
        self._recording_overlay: Optional[RecordingOverlay] = None

        self._setup_window()
        self._create_widgets()
        self._bind_shortcuts()
        self._update_status()
        self._setup_osc_client()
        self._setup_recording_overlay()
        self._setup_coqui_status_callback()

    def _safe_after(self, delay_ms: int, callback):
        """Schedule a Tk callback unless shutdown has invalidated callbacks."""
        if not getattr(self, "_async_callbacks_active", True):
            return None

        def guarded_callback(*args, **kwargs):
            if not getattr(self, "_async_callbacks_active", True):
                return None
            return callback(*args, **kwargs)

        try:
            return self.root.after(delay_ms, guarded_callback)
        except Exception:
            return None

    def _cancel_after(self, timer_id) -> None:
        """Cancel a Tk timer while tolerating a root that is already closing."""
        if not timer_id:
            return
        try:
            self.root.after_cancel(timer_id)
        except Exception:
            pass

    def _setup_window(self):
        """Configure the main window."""
        self.root.title("CriTTS Recoded")
        self.root.geometry(f"{WINDOW_MAIN_WIDTH}x{WINDOW_MAIN_HEIGHT}")
        self.root.minsize(WINDOW_MAIN_MIN_WIDTH, WINDOW_MAIN_MIN_HEIGHT)

        # Set icon if available
        if self.icon_path and os.path.exists(self.icon_path):
            try:
                self.root.iconbitmap(self.icon_path)
            except Exception:
                pass

        # Configure grid - all rows need proper weight
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)  # Text area expands
        self.root.grid_rowconfigure(1, weight=0)  # Controls fixed
        self.root.grid_rowconfigure(2, weight=0)  # Status fixed

        # Set root window background color to match app theme
        self.root.configure(fg_color=COLOR_BG_PRIMARY)

    def _create_widgets(self):
        """Create and layout all GUI widgets with modern styling."""
        # Main container with modern padding
        self.main_frame = ctk.CTkFrame(self.root, fg_color=COLOR_BG_PRIMARY)
        self.main_frame.grid(row=0, column=0, padx=0, pady=0, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=1)  # Text area expands
        # 2 actions, 3 switches, 4 quick controls (collapsible), 5 status: fixed height

        colors = get_theme_colors(get_active_appearance_mode())

        # Header: which voice will speak (click to change it) and Settings.
        self.header_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, padx=SPACING_MD, pady=(SPACING_SM, SPACING_XS), sticky="ew")
        self.header_frame.grid_columnconfigure(1, weight=1)

        self.voice_indicator_label = ctk.CTkLabel(
            self.header_frame,
            text="Voice",
            font=ctk.CTkFont(size=FONT_SM),
            text_color=colors["text_secondary"],
        )
        self.voice_indicator_label.grid(row=0, column=0, sticky="w")

        # Opens Settings, which starts on the Voice page.
        self.voice_indicator_value = ctk.CTkButton(
            self.header_frame,
            text="Loading...",
            font=ctk.CTkFont(size=FONT_MD, weight=FONT_WEIGHT_BOLD),
            anchor="w",
            height=32,
            fg_color="transparent",
            hover_color=colors["button_neutral"],
            text_color=colors["text_primary"],
            corner_radius=RADIUS_MD,
            command=self._on_settings,
        )
        self.voice_indicator_value.grid(row=0, column=1, padx=(SPACING_XS, 0), sticky="w")

        self.settings_button = ctk.CTkButton(
            self.header_frame,
            text="Settings",
            font=ctk.CTkFont(size=FONT_SM),
            command=self._on_settings,
            height=32,
            width=96,
            **neutral_button_style(),
            corner_radius=RADIUS_MD,
        )
        self.settings_button.grid(row=0, column=2, sticky="e")

        # The text box sits directly on the window: no card or caption around it.
        self.text_input = ctk.CTkTextbox(
            self.main_frame,
            font=ctk.CTkFont(size=FONT_LG),
            wrap="word",
            activate_scrollbars=True,
            fg_color=colors["input_bg"],
            border_width=1,
            border_color=COLOR_NEUTRAL_LIGHT,
            corner_radius=RADIUS_MD,
        )
        self.text_input.grid(row=1, column=0, padx=SPACING_MD, pady=SPACING_XS, sticky="nsew")
        self.text_input.tag_config("current_line", background=colors["line_highlight"])
        self.text_input.bind("<KeyRelease>", lambda e: self._highlight_current_line())
        self.text_input.bind("<ButtonRelease>", lambda e: self._highlight_current_line())
        self.text_input.bind("<KeyRelease>", lambda e: self._on_text_changed(), add="+")

        # CTkTextbox has no placeholder; a label over the empty box stands in.
        self._placeholder_label = ctk.CTkLabel(
            self.text_input,
            text="Type something to say, then press Enter",
            font=ctk.CTkFont(size=FONT_LG),
            text_color=colors["text_secondary"],
        )
        self._placeholder_label.bind("<Button-1>", lambda _e: self.text_input.focus_set())
        self._update_placeholder()

        # Bind Enter to trigger speak, Shift+Enter to allow line breaks
        self.text_input.bind("<Return>", self._on_enter_key)
        self.text_input.bind("<Shift-Return>", self._on_shift_enter_key)

        # Add explicit bindings for text editing shortcuts
        self._bind_text_editing_shortcuts()
        self._setup_text_context_menu()

        # Actions: editing helpers on the left, Stop and Speak on the right.
        self.controls_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.controls_frame.grid(row=2, column=0, padx=SPACING_MD, pady=(SPACING_SM, 0), sticky="ew")
        self._actions_left = ctk.CTkFrame(self.controls_frame, fg_color="transparent")
        self._actions_left.pack(side="left")
        self._actions_right = ctk.CTkFrame(self.controls_frame, fg_color="transparent")
        self._actions_right.pack(side="right")

        self.clear_button = ctk.CTkButton(
            self._actions_left,
            text="Clear",
            font=ctk.CTkFont(size=FONT_MD),
            command=self._on_clear,
            height=BUTTON_HEIGHT_SM,
            width=84,
            **neutral_button_style(),
            corner_radius=RADIUS_MD,
        )

        self.voice_button = ctk.CTkButton(
            self._actions_left,
            text="Voice input",
            font=ctk.CTkFont(size=FONT_MD),
            command=self._on_voice_input,
            height=BUTTON_HEIGHT_SM,
            width=120,
            **neutral_button_style(),
            corner_radius=RADIUS_MD,
        )

        self.stop_button = ctk.CTkButton(
            self._actions_right,
            text="⏹  Stop",
            font=ctk.CTkFont(size=FONT_MD, weight=FONT_WEIGHT_BOLD),
            command=self._on_stop,
            height=BUTTON_HEIGHT,
            width=100,
            **neutral_button_style(),
            state="disabled",
            corner_radius=RADIUS_MD,
        )

        # The one accent on the screen: the action the window exists for.
        self.speak_button = ctk.CTkButton(
            self._actions_right,
            text="▶  Speak",
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD),
            command=self._on_speak,
            height=BUTTON_HEIGHT,
            width=148,
            fg_color=COLOR_SUCCESS,
            hover_color=COLOR_SUCCESS_HOVER,
            text_color=COLOR_ON_FILL,
            corner_radius=RADIUS_MD,
        )

        # On/off settings are switches, so they no longer look like actions.
        self.toggles_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.toggles_frame.grid(row=3, column=0, padx=SPACING_MD, pady=(SPACING_SM, SPACING_SM), sticky="ew")
        switch_colors = toggle_switch_style()

        self.overlay_button = ctk.CTkSwitch(
            self.toggles_frame,
            text="Recording overlay",
            font=ctk.CTkFont(size=FONT_SM),
            command=self._on_toggle_overlay,
            **switch_colors,
        )
        self._sync_switch(self.overlay_button, self._overlay_visible)

        self._quick_controls_visible = self.settings.get("quick_controls_visible", False)
        self.controls_toggle_button = ctk.CTkSwitch(
            self.toggles_frame,
            text="Speed, volume and pitch",
            font=ctk.CTkFont(size=FONT_SM),
            command=self._toggle_quick_controls,
            **switch_colors,
        )
        self._sync_switch(self.controls_toggle_button, self._quick_controls_visible)

        # Quick controls panel (collapsible) - row 3
        self._create_quick_controls()

        # Status strip along the bottom edge: a state dot and one line of text.
        self.status_frame = ctk.CTkFrame(self.main_frame, fg_color=colors["bg_secondary"], corner_radius=0)
        self.status_frame.grid(row=5, column=0, sticky="ew")

        self.status_log_frame = ctk.CTkFrame(self.status_frame, fg_color="transparent")
        self.status_log_frame.pack(fill="both", expand=True, padx=SPACING_MD, pady=SPACING_XS)

        self.activity_indicator = ctk.CTkLabel(
            self.status_log_frame, text="●", font=ctk.CTkFont(size=FONT_SM), text_color=COLOR_STATUS_IDLE
        )
        self.activity_indicator.pack(side="left", padx=(0, SPACING_XS))

        self.progress_label = ctk.CTkLabel(
            self.status_log_frame, text="", font=ctk.CTkFont(size=FONT_XS), text_color=colors["text_secondary"]
        )
        self.progress_label.pack(side="right", padx=(SPACING_SM, 0))

        self.status_label = ctk.CTkLabel(
            self.status_log_frame,
            text="Ready to speak",
            font=ctk.CTkFont(size=FONT_SM),
            text_color=colors["text_primary"],
            anchor="w",
            justify="left",
            wraplength=400,
        )
        self.status_label.pack(side="left", fill="x", expand=True)

        # Bind window resize
        self.root.bind("<Configure>", self._on_window_resize)

        self._highlight_current_line()

        # Apply theme based on saved settings
        appearance_mode = self.settings.get("appearance_mode", "Dark")
        self.apply_theme(appearance_mode)

        # Apply button visibility from saved settings
        self.apply_button_visibility()

    def _on_window_resize(self, event):
        """Coalesce window <Configure> events into one status-label rewrap.

        A resize drag emits a stream of <Configure> events; configuring the
        label on every one of them forces repeated text reflow and can make
        resizing janky.  Mirror the settings tabs: record the latest width and
        apply it once per event-loop cycle via ``after(0)``.
        """
        if event.widget != self.root:
            return

        window_width = event.width
        # Reserve space for progress, activity indicator, and padding
        reserved_width = 150
        new_wraplength = max(200, window_width - reserved_width)

        self._pending_status_wraplength = new_wraplength

        if new_wraplength == self._last_status_wraplength:
            return
        if self._status_wraplength_job is not None:
            return

        self._status_wraplength_job = self._safe_after(0, self._apply_pending_status_wraplength)

    def _apply_pending_status_wraplength(self):
        """Apply the latest coalesced status-label wraplength, if it changed."""
        self._status_wraplength_job = None
        pending_wraplength = self._pending_status_wraplength
        self._pending_status_wraplength = None

        if pending_wraplength is None or pending_wraplength == self._last_status_wraplength:
            return

        try:
            self.status_label.configure(wraplength=pending_wraplength)
            self._last_status_wraplength = pending_wraplength
        except Exception:
            pass  # Ignore errors during resize

    def _bind_shortcuts(self):
        """Bind keyboard shortcuts dynamically from settings."""
        logger = logging.getLogger(__name__)

        # Get keybinds from settings
        keybinds = self.settings.get("keybinds", {})

        # Create action mapping dictionary
        actions = {
            "stop": self._on_stop,
            "clear": self._on_clear,
            "open_settings": self._on_settings,
            "voice_input": self._on_voice_input_toggle,
        }

        # Register each keybind with error handling
        for action_name, callback in actions.items():
            keybind_string = keybinds.get(action_name)

            # Skip empty/None keybind strings gracefully
            if not keybind_string:
                continue

            try:
                success = self.keybind_manager.register_keybind(self.root, keybind_string, callback, action_name)
                if not success:
                    logger.warning("Failed to register keybind for '%s': '%s'", action_name, keybind_string)
            except Exception as e:
                logger.warning("Error registering keybind for '%s': %s", action_name, e)

        # Also bind each keybind directly to text_input widget (widget-level binding)
        # This overrides the Text widget's class bindings (e.g., Ctrl+T transpose)
        # Widget-level bindings have higher priority than class bindings
        for action_name, callback in actions.items():
            keybind_string = keybinds.get(action_name)

            if not keybind_string:
                continue

            try:
                tk_format = self.keybind_manager.parse_keybind(keybind_string)
                if tk_format:
                    # Bind directly to text_input with widget-level priority
                    # Return "break" to prevent class binding and bind_all from firing
                    self.text_input.bind(tk_format, lambda e, cb=callback: self._handle_widget_keybind(e, cb))
                    self._text_widget_bound_sequences.append(tk_format)
            except Exception as e:
                logger.warning("Error binding widget-level keybind for '%s': %s", action_name, e)

        # Setup global hotkeys if enabled
        self._setup_global_hotkeys()

    def _setup_global_hotkeys(self):
        """Setup system-wide global hotkeys if enabled in settings."""
        logger = logging.getLogger(__name__)

        # Check if global hotkeys are enabled in settings
        global_hotkeys_enabled = self.settings.get("global_hotkeys_enabled", False)

        # Enable/disable global hotkeys in the keybind manager
        if not self.keybind_manager.enable_global_hotkeys(global_hotkeys_enabled):
            if global_hotkeys_enabled:
                logger.warning("Global hotkeys requested but keyboard library not available")
            return

        if not global_hotkeys_enabled:
            logger.debug("Global hotkeys disabled in settings")
            return

        # Get keybinds from settings
        keybinds = self.settings.get("keybinds", {})

        # Create action mapping dictionary for global hotkeys
        # Note: "speak" is excluded because it requires text input focus
        global_actions = {
            "stop": self._on_stop,
            "clear": self._on_clear,
            "open_settings": self._on_settings,
            "voice_input": self._on_voice_input_toggle,
        }

        # Register global hotkeys
        registered_count = 0
        for action_name, callback in global_actions.items():
            keybind_string = keybinds.get(action_name)

            if not keybind_string:
                continue

            # The keyboard library fires hotkeys on its own listener thread,
            # and these handlers touch Tk widgets, so marshal them onto the
            # Tk main loop instead of calling them directly.
            def on_hotkey(cb=callback):
                self._safe_after(0, cb)

            try:
                success = self.keybind_manager.register_global_hotkey(keybind_string, on_hotkey, action_name)
                if success:
                    registered_count += 1
                    logger.debug("Registered global hotkey for '%s': '%s'", action_name, keybind_string)
                else:
                    logger.warning("Failed to register global hotkey for '%s': '%s'", action_name, keybind_string)
            except Exception as e:
                logger.warning("Error registering global hotkey for '%s': %s", action_name, e)

        logger.info("Registered %d global hotkeys", registered_count)

    def _handle_widget_keybind(self, event, callback):
        """Handle widget-level keybind event."""
        try:
            callback()
        except Exception:
            pass
        return "break"  # Prevent class binding and bind_all from firing

    def _rebind_shortcuts(self):
        """Unregister and re-register all keybinds (called after settings change)."""
        logger = logging.getLogger(__name__)

        # Unbind widget-level bindings first
        for sequence in self._text_widget_bound_sequences:
            try:
                self.text_input.unbind(sequence)
            except Exception:
                pass
        self._text_widget_bound_sequences.clear()

        try:
            self.keybind_manager.unregister_all(self.root)
        except Exception as e:
            logger.warning("Error unregistering keybinds: %s", e)

        try:
            self._bind_shortcuts()
        except Exception as e:
            logger.error("Error rebinding shortcuts: %s", e)

    def rebind_shortcuts(self):
        """
        Public method to rebind all keyboard shortcuts.

        Called from CriTTSApp after settings are saved to refresh keybinds.
        """
        self._rebind_shortcuts()

    def _on_text_changed(self):
        """Handle text input changes for typing animation."""
        self._update_placeholder()
        self._schedule_voice_indicator_update()

        # Handle typing animation if OSC is enabled
        self._handle_typing_animation()

    def _handle_typing_animation(self):
        """Handle typing animation for VRChat OSC chatbox."""
        self._chatbox.handle_typing(self._speaking)

    def _animate_typing_indicator(self):
        """Animate the typing indicator with dots."""
        self._chatbox.animate_typing()

    def _stop_typing_animation(self, send_clear: bool = True):
        """Stop the typing animation.

        Args:
            send_clear: If True, clear the chatbox after stopping. Set to False
                       when the actual message will replace the typing text,
                       avoiding VRChat's rate limit on chatbox messages.
        """
        self._chatbox.stop_typing(send_clear)

    def _on_clear(self):
        """Handle clear button click."""
        # Stop typing animation when clearing (clear chatbox since no message will replace it)
        if self._chatbox.is_typing_active:
            self._stop_typing_animation(send_clear=True)

        self.text_input.delete("1.0", "end")
        self._refresh_after_text_mutation()
        self.text_input.focus()

    def _on_settings(self):
        """Handle settings button click."""
        self.on_open_settings()

    def _show_error(self, message: str):
        """Show error message in status and popup."""
        self._set_status(message, "❌")

        # Show error dialog
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Error")
        dialog.geometry("400x150")
        dialog.transient(self.root)
        dialog.grab_set()

        label = ctk.CTkLabel(dialog, text=message, font=ctk.CTkFont(size=12), wraplength=350)
        label.pack(padx=SPACING_LG, pady=SPACING_LG)

        ok_button = ctk.CTkButton(dialog, text="OK", command=dialog.destroy)
        ok_button.pack(pady=SPACING_SM)

        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (400 // 2)
        y = (dialog.winfo_screenheight() // 2) - (150 // 2)
        dialog.geometry(f"+{x}+{y}")

    def apply_theme(self, mode: str):
        """
        Apply theme colors based on appearance mode.

        Args:
            mode: Appearance mode ('Dark', 'Light', or 'System')
        """
        colors = get_theme_colors(mode)

        # Reconfigure root and main frame
        self.root.configure(fg_color=colors["bg_primary"])
        self.main_frame.configure(fg_color=colors["bg_primary"])

        self.text_input.configure(fg_color=colors["input_bg"])
        self.text_input.tag_config("current_line", background=colors["line_highlight"])
        self._placeholder_label.configure(text_color=colors["text_secondary"])

        self.voice_indicator_label.configure(text_color=colors["text_secondary"])
        self.voice_indicator_value.configure(text_color=colors["text_primary"], hover_color=colors["button_neutral"])

        # Reconfigure status frame and labels
        self.status_frame.configure(fg_color=colors["bg_secondary"])
        self.status_label.configure(text_color=colors["text_primary"])
        self.progress_label.configure(text_color=colors["text_muted"])
        self._apply_quick_controls_theme(mode)
        self._apply_button_row_theme(mode)

    @staticmethod
    def _sync_switch(switch, on: bool) -> None:
        """Show *on* on a toggle switch (after a click, or when saving reverted it)."""
        if on:
            switch.select()
        else:
            switch.deselect()

    def _update_placeholder(self) -> None:
        """Show the hint only while the text box is empty."""
        if self.text_input.index("end-1c") != "1.0":
            self._placeholder_label.place_forget()
        else:
            self._placeholder_label.place(x=14, y=10)

    def _apply_button_row_theme(self, mode: str) -> None:
        """Recolor the neutral buttons for *mode*; state colors (speaking, recording) are left alone."""
        neutral = neutral_button_style(mode)
        self.clear_button.configure(**neutral)
        self.settings_button.configure(**neutral)
        self.overlay_button.configure(**toggle_switch_style(mode))
        if not getattr(self, "_tts_speaking", False):
            self.stop_button.configure(**neutral)
        if self._stt_state == STTState.IDLE:
            self.voice_button.configure(**neutral)

    def refresh_status(self):
        """Refresh status display (called after settings change)."""
        self._abbreviation_cache.clear()
        self._update_status()
        self._rebuild_text_token_menu()
        self._setup_viseme_mapper()
        self.refresh_quick_controls()
        self._set_status("Settings updated", "✅")

    def apply_button_visibility(self):
        """
        Apply button visibility based on saved settings.

        Reads the 'visible_buttons' setting and shows/hides toggleable buttons.
        Settings and the speed/volume/pitch switch are always visible.
        """
        visible_buttons = self.settings.get("visible_buttons", ["speak", "stop", "clear", "voice", "overlay"])

        placements = [
            ("clear", self.clear_button, {"side": "left", "padx": (0, SPACING_SM)}),
            ("voice", self.voice_button, {"side": "left", "padx": (0, SPACING_SM)}),
            # Right group packs right-to-left so Speak ends at the edge.
            ("speak", self.speak_button, {"side": "right"}),
            ("stop", self.stop_button, {"side": "right", "padx": (0, SPACING_SM)}),
            ("overlay", self.overlay_button, {"side": "left", "padx": (0, SPACING_LG)}),
        ]
        for _, widget, _ in placements:
            widget.pack_forget()
        self.controls_toggle_button.pack_forget()

        for name, widget, pack_options in placements:
            if name in visible_buttons:
                widget.pack(**pack_options)
        self.controls_toggle_button.pack(side="left")

    def set_text(self, text: str):
        """Set text in the input area."""
        self.text_input.delete("1.0", "end")
        self.text_input.insert("1.0", text)
        self._refresh_after_text_mutation()

    def get_text(self) -> str:
        """Get text from the input area."""
        return self.text_input.get("1.0", "end-1c")
