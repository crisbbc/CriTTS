"""
Main Window GUI Module
Primary application window with text input, controls, and status display.
"""
import customtkinter as ctk
import threading
import tkinter as tk
from typing import Optional, Callable
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
    DeferredTextAnalysisRequest,
    LatestWinsTextAnalysisScheduler,
)
from .mixins.text_editor_mixin import TextEditorMixin
from .mixins.tts_pipeline_mixin import TTSPipelineMixin
from .mixins.stt_mixin import STTMixin
from .mixins.animation_mixin import AnimationMixin
from .mixins.quick_controls_mixin import QuickControlsMixin
from .mixins.integrations_mixin import IntegrationsMixin
from .theme_constants import (
    SPACING_SM, SPACING_MD, SPACING_LG,
    COLOR_SUCCESS, COLOR_SUCCESS_HOVER,
    COLOR_DANGER, COLOR_DANGER_HOVER,
    COLOR_PRIMARY, COLOR_PRIMARY_HOVER, COLOR_PRIMARY_LIGHT,
    COLOR_ACCENT, COLOR_ACCENT_HOVER,
    COLOR_WARNING,
    COLOR_NEUTRAL_DARK, COLOR_NEUTRAL_MEDIUM, COLOR_NEUTRAL, COLOR_NEUTRAL_LIGHT, COLOR_NEUTRAL_LIGHTER, COLOR_NEUTRAL_LIGHTEST,
    COLOR_BG_PRIMARY, COLOR_BG_SECONDARY,
    COLOR_STATUS_IDLE,
    COLOR_TRANSCRIBING,
    FONT_XS, FONT_SM, FONT_MD, FONT_WEIGHT_BOLD,
    BUTTON_HEIGHT_LG, BUTTON_WIDTH_DEFAULT,
    FRAME_CONTROLS_HEIGHT, FRAME_STATUS_HEIGHT,
    RADIUS_MD, RADIUS_LG,
    ANIMATION_NORMAL,
    WINDOW_MAIN_MIN_WIDTH, WINDOW_MAIN_MIN_HEIGHT,
    WINDOW_MAIN_WIDTH, WINDOW_MAIN_HEIGHT,
    get_theme_colors
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
        stt_engine=None

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
        self.main_frame.grid_rowconfigure(2, weight=0)  # Controls fixed
        self.main_frame.grid_rowconfigure(3, weight=0)  # Quick controls (collapsible)
        self.main_frame.grid_rowconfigure(4, weight=0)  # Status fixed
        
        # Header with voice indicator
        self.header_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, padx=SPACING_MD, pady=(SPACING_MD, SPACING_SM), sticky="ew")
        self.header_frame.grid_columnconfigure(1, weight=1)
        
        # Voice indicator with modern styling
        self.voice_indicator_label = ctk.CTkLabel(
            self.header_frame,
            text="🎤 Voice:",
            font=ctk.CTkFont(size=FONT_SM, weight=FONT_WEIGHT_BOLD),
            text_color=COLOR_NEUTRAL_LIGHTER
        )
        self.voice_indicator_label.grid(row=0, column=0, sticky="w")
        
        self.voice_indicator_value = ctk.CTkLabel(
            self.header_frame,
            text="Loading...",
            font=ctk.CTkFont(size=FONT_SM),
            text_color=COLOR_PRIMARY_LIGHT
        )
        self.voice_indicator_value.grid(row=0, column=1, padx=SPACING_SM, sticky="w")
        
        # Text input card with modern styling
        self.text_frame = ctk.CTkFrame(
            self.main_frame, 
            fg_color=COLOR_BG_SECONDARY,
            corner_radius=RADIUS_LG
        )
        self.text_frame.grid(row=1, column=0, padx=SPACING_MD, pady=SPACING_MD, sticky="nsew")
        self.text_frame.grid_columnconfigure(0, weight=1)
        self.text_frame.grid_rowconfigure(1, weight=1)
        
        self.text_label = ctk.CTkLabel(
            self.text_frame, 
            text="✍️ Enter text to speak:",
            font=ctk.CTkFont(size=FONT_MD, weight=FONT_WEIGHT_BOLD),
            text_color=COLOR_NEUTRAL_LIGHTEST
        )
        self.text_label.grid(row=0, column=0, padx=SPACING_LG, pady=(SPACING_LG, SPACING_SM), sticky="w")
        
        self.text_input = ctk.CTkTextbox(
            self.text_frame,
            font=ctk.CTkFont(size=FONT_MD),
            wrap="word",
            activate_scrollbars=True,
            fg_color=COLOR_NEUTRAL_DARK,
            border_width=0,
            corner_radius=RADIUS_MD
        )
        self.text_input.grid(row=1, column=0, padx=SPACING_LG, pady=(SPACING_SM, SPACING_LG), sticky="nsew")
        self.text_input.tag_config("current_line", background=COLOR_NEUTRAL_MEDIUM)
        self.text_input.bind("<KeyRelease>", lambda e: self._highlight_current_line())
        self.text_input.bind("<ButtonRelease>", lambda e: self._highlight_current_line())
        self.text_input.bind("<KeyRelease>", lambda e: self._on_text_changed(), add="+")
        
        # Bind Enter to trigger speak, Shift+Enter to allow line breaks
        self.text_input.bind("<Return>", self._on_enter_key)
        self.text_input.bind("<Shift-Return>", self._on_shift_enter_key)
        
        # Add explicit bindings for text editing shortcuts
        self._bind_text_editing_shortcuts()
        self._setup_text_context_menu()
        
        # Control buttons frame with modern styling
        self.controls_frame = ctk.CTkFrame(
            self.main_frame, 
            fg_color="transparent"
        )
        self.controls_frame.grid(row=2, column=0, padx=SPACING_MD, pady=(SPACING_MD, SPACING_MD), sticky="ew")
        self.controls_frame.grid_propagate(False)
        self.controls_frame.configure(height=FRAME_CONTROLS_HEIGHT)
        
        # Speak button (primary action) - prominent styling
        self.speak_button = ctk.CTkButton(
            self.controls_frame,
            text="▶  Speak",
            font=ctk.CTkFont(size=FONT_MD, weight=FONT_WEIGHT_BOLD),
            command=self._on_speak,
            height=BUTTON_HEIGHT_LG,
            width=BUTTON_WIDTH_DEFAULT,
            fg_color=COLOR_SUCCESS,
            hover_color=COLOR_SUCCESS_HOVER,
            corner_radius=RADIUS_MD
        )
        self.speak_button.pack(side="left", padx=SPACING_SM, pady=SPACING_SM, expand=True)
        
        # Stop button - danger styling
        self.stop_button = ctk.CTkButton(
            self.controls_frame,
            text="⏹  Stop",
            font=ctk.CTkFont(size=FONT_MD, weight=FONT_WEIGHT_BOLD),
            command=self._on_stop,
            height=BUTTON_HEIGHT_LG,
            width=BUTTON_WIDTH_DEFAULT,
            fg_color=COLOR_DANGER,
            hover_color=COLOR_DANGER_HOVER,
            state="disabled",
            corner_radius=RADIUS_MD
        )
        self.stop_button.pack(side="left", padx=SPACING_SM, pady=SPACING_SM, expand=True)
        
        # Clear button - subtle styling
        self.clear_button = ctk.CTkButton(
            self.controls_frame,
            text="🗑  Clear",
            font=ctk.CTkFont(size=FONT_MD),
            command=self._on_clear,
            height=BUTTON_HEIGHT_LG,
            width=BUTTON_WIDTH_DEFAULT,
            fg_color=COLOR_NEUTRAL_MEDIUM,
            hover_color=COLOR_NEUTRAL,
            corner_radius=RADIUS_MD
        )
        self.clear_button.pack(side="left", padx=SPACING_SM, pady=SPACING_SM, expand=True)
        
        # Voice input button - accent styling (for STT)
        self.voice_button = ctk.CTkButton(
            self.controls_frame,
            text="🎙  Voice",
            font=ctk.CTkFont(size=FONT_MD),
            command=self._on_voice_input,
            height=BUTTON_HEIGHT_LG,
            width=BUTTON_WIDTH_DEFAULT,
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            corner_radius=RADIUS_MD
        )
        self.voice_button.pack(side="left", padx=SPACING_SM, pady=SPACING_SM, expand=True)
        
        # Overlay toggle button - secondary styling
        overlay_color = COLOR_PRIMARY if self._overlay_visible else COLOR_NEUTRAL_MEDIUM
        overlay_hover = COLOR_PRIMARY_HOVER if self._overlay_visible else COLOR_NEUTRAL
        self.overlay_button = ctk.CTkButton(
            self.controls_frame,
            text="👁  Overlay",
            font=ctk.CTkFont(size=FONT_MD),
            command=self._on_toggle_overlay,
            height=BUTTON_HEIGHT_LG,
            width=BUTTON_WIDTH_DEFAULT,
            fg_color=overlay_color,
            hover_color=overlay_hover,
            corner_radius=RADIUS_MD
        )
        self.overlay_button.pack(side="left", padx=SPACING_SM, pady=SPACING_SM, expand=True)
        
        # Settings button - accent styling
        self.settings_button = ctk.CTkButton(
            self.controls_frame,
            text="⚙  Settings",
            font=ctk.CTkFont(size=FONT_MD),
            command=self._on_settings,
            height=BUTTON_HEIGHT_LG,
            width=BUTTON_WIDTH_DEFAULT,
            fg_color=COLOR_PRIMARY,
            hover_color=COLOR_PRIMARY_HOVER,
            corner_radius=RADIUS_MD
        )
        self.settings_button.pack(side="left", padx=SPACING_SM, pady=SPACING_SM, expand=True)
        
        # Quick controls toggle button - always visible, toggles the slider panel
        self._quick_controls_visible = self.settings.get("quick_controls_visible", False)
        qc_color = COLOR_PRIMARY if self._quick_controls_visible else COLOR_NEUTRAL_MEDIUM
        qc_hover = COLOR_PRIMARY_HOVER if self._quick_controls_visible else COLOR_NEUTRAL
        self.controls_toggle_button = ctk.CTkButton(
            self.controls_frame,
            text="🎚  Controls",
            font=ctk.CTkFont(size=FONT_MD),
            command=self._toggle_quick_controls,
            height=BUTTON_HEIGHT_LG,
            width=BUTTON_WIDTH_DEFAULT,
            fg_color=qc_color,
            hover_color=qc_hover,
            corner_radius=RADIUS_MD
        )
        self.controls_toggle_button.pack(side="left", padx=SPACING_SM, pady=SPACING_SM, expand=True)
        
        # Quick controls panel (collapsible) - row 3
        self._create_quick_controls()
        
        # Status frame with modern styling
        self.status_frame = ctk.CTkFrame(
            self.main_frame, 
            fg_color=COLOR_BG_SECONDARY,
            corner_radius=RADIUS_MD
        )
        self.status_frame.grid(row=4, column=0, padx=SPACING_MD, pady=(0, SPACING_MD), sticky="ew")
        self.status_frame.grid_propagate(False)
        self.status_frame.configure(height=FRAME_STATUS_HEIGHT)
        
        # Status content
        self.status_log_frame = ctk.CTkFrame(self.status_frame, fg_color="transparent")
        self.status_log_frame.pack(fill="both", expand=True, padx=SPACING_LG, pady=SPACING_MD)
        
        # Activity indicator (modern dot)
        self.activity_indicator = ctk.CTkLabel(
            self.status_log_frame,
            text="●",
            font=ctk.CTkFont(size=FONT_MD),
            text_color=COLOR_STATUS_IDLE
        )
        self.activity_indicator.pack(side="right", padx=(SPACING_SM, 0))
        
        # Progress indicator
        self.progress_label = ctk.CTkLabel(
            self.status_log_frame,
            text="",
            font=ctk.CTkFont(size=FONT_XS),
            text_color=COLOR_NEUTRAL_LIGHT
        )
        self.progress_label.pack(side="right", padx=SPACING_SM)
        
        # Main status message
        self.status_label = ctk.CTkLabel(
            self.status_log_frame,
            text="Ready to speak",
            font=ctk.CTkFont(size=FONT_MD),
            text_color=COLOR_NEUTRAL_LIGHTEST,
            anchor="w",
            wraplength=400
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

        self._status_wraplength_job = self._safe_after(
            0, self._apply_pending_status_wraplength
        )

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
            "voice_input": self._on_voice_input_toggle
        }
        
        # Register each keybind with error handling
        for action_name, callback in actions.items():
            keybind_string = keybinds.get(action_name)
            
            # Skip empty/None keybind strings gracefully
            if not keybind_string:
                continue
            
            try:
                success = self.keybind_manager.register_keybind(
                    self.root, keybind_string, callback, action_name
                )
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
            "voice_input": self._on_voice_input_toggle
        }
        
        # Register global hotkeys
        registered_count = 0
        for action_name, callback in global_actions.items():
            keybind_string = keybinds.get(action_name)
            
            if not keybind_string:
                continue
            
            try:
                success = self.keybind_manager.register_global_hotkey(
                    keybind_string, callback, action_name
                )
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
        
        label = ctk.CTkLabel(
            dialog,
            text=message,
            font=ctk.CTkFont(size=12),
            wraplength=350
        )
        label.pack(padx=SPACING_LG, pady=SPACING_LG)
        
        ok_button = ctk.CTkButton(
            dialog,
            text="OK",
            command=dialog.destroy
        )
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
        
        # Reconfigure text frame and input
        self.text_frame.configure(fg_color=colors["bg_secondary"])
        self.text_input.configure(fg_color=colors["input_bg"])
        self.text_input.tag_config("current_line", background=colors["line_highlight"])
        
        # Reconfigure text label
        self.text_label.configure(text_color=colors["text_primary"])
        
        # Reconfigure voice indicator labels
        self.voice_indicator_label.configure(text_color=colors["text_secondary"])
        self.voice_indicator_value.configure(text_color=colors["voice_name"])
        
        # Reconfigure status frame and labels
        self.status_frame.configure(fg_color=colors["bg_secondary"])
        self.status_label.configure(text_color=colors["text_primary"])
        self.progress_label.configure(text_color=colors["text_muted"])
        self._apply_quick_controls_theme(mode)

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
        Settings button is always visible. Re-packs in fixed order for consistency.
        """
        # Get visible buttons from settings (default: all five toggleable buttons visible)
        visible_buttons = self.settings.get("visible_buttons", ["speak", "stop", "clear", "voice", "overlay"])
        
        # All toggleable buttons in fixed order
        toggleable_buttons = [
            ("speak", self.speak_button),
            ("stop", self.stop_button),
            ("clear", self.clear_button),
            ("voice", self.voice_button),
            ("overlay", self.overlay_button),
        ]
        
        # Unpack all toggleable buttons AND always-visible buttons
        for _, button in toggleable_buttons:
            button.pack_forget()
        self.controls_toggle_button.pack_forget()
        self.settings_button.pack_forget()
        
        # Re-pack everything left-to-right in fixed order; expand=True makes
        # buttons spread out evenly when the window is stretched.
        for name, button in toggleable_buttons:
            if name in visible_buttons:
                button.pack(side="left", padx=SPACING_SM, pady=SPACING_SM, expand=True)

        self.settings_button.pack_forget()
        self.settings_button.pack(side="left", padx=SPACING_SM, pady=SPACING_SM, expand=True)
        self.controls_toggle_button.pack_forget()
        self.controls_toggle_button.pack(side="left", padx=SPACING_SM, pady=SPACING_SM, expand=True)

        # Enforce a minimum width wide enough to always show every visible button.
        # Each button occupies BUTTON_WIDTH_DEFAULT + 2 * SPACING_SM horizontal space.
        # Add 2 visible fixed buttons (controls_toggle + settings) to the count.
        n_visible = sum(1 for name, _ in toggleable_buttons if name in visible_buttons) + 2
        required = n_visible * (BUTTON_WIDTH_DEFAULT + 2 * SPACING_SM) + 2 * SPACING_MD
        self.root.minsize(max(required, WINDOW_MAIN_MIN_WIDTH), WINDOW_MAIN_MIN_HEIGHT)
    

    def set_text(self, text: str):
        """Set text in the input area."""
        self.text_input.delete("1.0", "end")
        self.text_input.insert("1.0", text)
        self._refresh_after_text_mutation()

    
    def get_text(self) -> str:
        """Get text from the input area."""
        return self.text_input.get("1.0", "end-1c")
    