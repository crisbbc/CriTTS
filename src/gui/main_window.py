"""
Main Window GUI Module
Primary application window with text input, controls, and status display.
"""
import customtkinter as ctk
import asyncio
import threading
from typing import Optional, Callable
import os
import time
import datetime
import logging

from ..tts.text_preprocessor import TextPreprocessor
from ..gui.keybind_manager import KeybindManager
from ..vrchat import VRChatOSCClient
from ..vrchat.viseme_mapper import VisemeMapper, AmplitudeAnalyzer
from .recording_overlay import RecordingOverlay
from .theme_constants import (
    SPACING_XS, SPACING_SM, SPACING_MD, SPACING_LG, SPACING_XL, SPACING_2XL,
    COLOR_SUCCESS, COLOR_SUCCESS_HOVER, COLOR_SUCCESS_LIGHT,
    COLOR_DANGER, COLOR_DANGER_HOVER, COLOR_DANGER_LIGHT,
    COLOR_PRIMARY, COLOR_PRIMARY_HOVER, COLOR_PRIMARY_LIGHT,
    COLOR_ACCENT, COLOR_ACCENT_HOVER,
    COLOR_INFO, COLOR_WARNING,
    COLOR_NEUTRAL_DARKEST, COLOR_NEUTRAL_DARK, COLOR_NEUTRAL_MEDIUM, COLOR_NEUTRAL, COLOR_NEUTRAL_LIGHT, COLOR_NEUTRAL_LIGHTER, COLOR_NEUTRAL_LIGHTEST,
    COLOR_BG_PRIMARY, COLOR_BG_SECONDARY, COLOR_BG_TERTIARY,
    COLOR_STATUS_ACTIVE, COLOR_STATUS_ERROR, COLOR_STATUS_WARNING, COLOR_STATUS_SUCCESS, COLOR_STATUS_IDLE,
    FONT_XS, FONT_SM, FONT_MD, FONT_LG, FONT_XL, FONT_2XL, FONT_WEIGHT_BOLD,
    BUTTON_HEIGHT, BUTTON_HEIGHT_SM, BUTTON_HEIGHT_LG, BUTTON_MIN_WIDTH, BUTTON_WIDTH_DEFAULT,
    INPUT_HEIGHT, INPUT_HEIGHT_SM,
    FRAME_CONTROLS_HEIGHT, FRAME_STATUS_HEIGHT,
    RADIUS_SM, RADIUS_MD, RADIUS_LG, RADIUS_XL,
    ANIMATION_FAST, ANIMATION_NORMAL, ANIMATION_SLOW,
    WINDOW_MAIN_MIN_WIDTH, WINDOW_MAIN_MIN_HEIGHT,
    WINDOW_MAIN_WIDTH, WINDOW_MAIN_HEIGHT,
    get_theme_colors
)






class MainWindow:
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
        
        # STT (Voice Input) state
        self._stt_recording = False
        
        # Abbreviation expansion cache: (input_text) -> expanded_text
        self._abbreviation_cache = {}
        
        # Initialize OSC client
        self.osc_client: Optional[VRChatOSCClient] = None
        
        # Initialize keybind manager
        self.keybind_manager = KeybindManager()
        
        # Track text-widget-level bindings for keybinds (to override class bindings)
        self._text_widget_bound_sequences = []
        
        # Initialize viseme mapper for lip-sync
        self._viseme_mapper: Optional[VisemeMapper] = None
        self._amplitude_analyzer: Optional[AmplitudeAnalyzer] = None
        
        # Typing animation state variables
        self._typing_animation_timer = None
        self._typing_debounce_timer = None
        self._typing_animation_state = 0
        self._is_typing_active = False
        self._last_typing_time = 0
        
        # Voice indicator debounce timer
        self._voice_indicator_timer = None
        self._voice_indicator_animating = False
        
        # Text preprocessor (reused across speak calls)
        self._text_preprocessor = TextPreprocessor()
        
        # Recording overlay state
        self._overlay_visible: bool = self.settings.get("overlay_visible", False)
        self._recording_overlay: Optional[RecordingOverlay] = None
        
        self._setup_window()
        self._create_widgets()
        self._bind_shortcuts()
        self._update_status()
        self._setup_osc_client()
        self._setup_recording_overlay()



    
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
        self.main_frame.grid_rowconfigure(3, weight=0)  # Status fixed
        
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
        self.speak_button.pack(side="left", padx=(0, SPACING_SM), pady=SPACING_SM)
        
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
        self.stop_button.pack(side="left", padx=SPACING_SM, pady=SPACING_SM)
        
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
        self.clear_button.pack(side="left", padx=SPACING_SM, pady=SPACING_SM)
        
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
        self.voice_button.pack(side="left", padx=SPACING_SM, pady=SPACING_SM)
        
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
        self.overlay_button.pack(side="left", padx=SPACING_SM, pady=SPACING_SM)
        
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
        self.settings_button.pack(side="left", padx=SPACING_SM, pady=SPACING_SM)
        
        # Status frame with modern styling
        self.status_frame = ctk.CTkFrame(
            self.main_frame, 
            fg_color=COLOR_BG_SECONDARY,
            corner_radius=RADIUS_MD
        )
        self.status_frame.grid(row=3, column=0, padx=SPACING_MD, pady=(0, SPACING_MD), sticky="ew")
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

    
    def _highlight_current_line(self):
        """Remove current_line tag from all text, then apply to the line containing the cursor."""
        self.text_input.tag_remove("current_line", "1.0", "end")
        cursor_index = self.text_input.index("insert")
        line_num = cursor_index.split(".")[0]
        self.text_input.tag_add("current_line", f"{line_num}.0", f"{line_num}.end")
    
    def _on_window_resize(self, event):
        """Handle window resize to update dynamic elements like status label wraplength."""
        # Only process resize for the root window
        if event.widget == self.root:
            # Calculate available width for status label
            window_width = event.width
            # Reserve space for progress, activity indicator, and padding
            reserved_width = 150
            new_wraplength = max(200, window_width - reserved_width)
            
            # Update status label wraplength
            try:
                self.status_label.configure(wraplength=new_wraplength)
            except Exception:
                pass  # Ignore errors during resize

    
    def _bind_text_editing_shortcuts(self):
        """Bind text editing shortcuts with higher priority to prevent custom keybind interference."""
        # These bindings ensure standard text editing works properly
        text_shortcuts = {
            "<Control-a>": lambda e: self._on_text_select_all(),
            "<Control-c>": lambda e: self._on_text_copy(),
            "<Control-v>": lambda e: self._on_text_paste(),
            "<Control-x>": lambda e: self._on_text_cut(),
            "<Control-z>": lambda e: self._on_text_undo(),
        }
        
        for sequence, handler in text_shortcuts.items():
            self.text_input.bind(sequence, handler)
    
    def _on_text_select_all(self):
        """Select all text in the input."""
        self.text_input.tag_add("sel", "1.0", "end")
        self.text_input.mark_set("insert", "end")
        return "break"
    
    def _on_text_copy(self):
        """Copy selected text to clipboard."""
        try:
            selected = self.text_input.get("sel.first", "sel.last")
            self.root.clipboard_clear()
            self.root.clipboard_append(selected)
        except Exception:
            pass  # No selection
        return "break"
    
    def _on_text_paste(self):
        """Paste text from clipboard."""
        try:
            clipboard_text = self.root.clipboard_get()
            self.text_input.insert("insert", clipboard_text)
        except Exception:
            pass  # Clipboard empty or error
        return "break"
    
    def _on_text_cut(self):
        """Cut selected text to clipboard."""
        try:
            selected = self.text_input.get("sel.first", "sel.last")
            self.root.clipboard_clear()
            self.root.clipboard_append(selected)
            self.text_input.delete("sel.first", "sel.last")
        except Exception:
            pass  # No selection
        return "break"
    
    def _on_text_undo(self):
        """Undo last action (limited support)."""
        try:
            self.text_input.edit_undo()
        except Exception:
            pass  # Nothing to undo
        return "break"
    
    def _on_enter_key(self, event):
        """Handle Enter key press - prevent line breaks unless Shift is held."""
        # Only trigger speak action, don't insert newline
        self._on_speak()
        return "break"  # Prevent default Enter behavior (new line)
    
    def _on_shift_enter_key(self, event):
        """Handle Shift+Enter key press - allow line breaks."""
        # Allow default Shift+Enter behavior (new line)
        return "continue"  # Allow default behavior
    
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
                    logger.warning(f"Failed to register keybind for '{action_name}': '{keybind_string}'")
            except Exception as e:
                logger.warning(f"Error registering keybind for '{action_name}': {e}")
        
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
                logger.warning(f"Error binding widget-level keybind for '{action_name}': {e}")
        
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
                    logger.debug(f"Registered global hotkey for '{action_name}': '{keybind_string}'")
                else:
                    logger.warning(f"Failed to register global hotkey for '{action_name}': '{keybind_string}'")
            except Exception as e:
                logger.warning(f"Error registering global hotkey for '{action_name}': {e}")
        
        logger.info(f"Registered {registered_count} global hotkeys")
    
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


    
    def _update_status(self):
        """Update status label with current voice and device."""
        voice = self.settings.get("voice", "Default")
        device_idx = self.settings.get("device_index")
        
        if device_idx is not None:
            devices = self.audio_router.get_audio_devices()
            device_name = next(
                (d['name'] for d in devices if d['index'] == device_idx),
                "Unknown Device"
            )
        else:
            device_name = "Default Device"
        
        self.status_label.configure(
            text=f"Voice: {voice} | Output: {device_name}"
        )
        
        # Update voice indicator
        self._update_voice_indicator()
    
    def _update_voice_indicator(self):
        """Update the voice indicator label with current voice information."""
        voice = self.settings.get("voice", "Default")
        auto_language = self.settings.get("auto_language_detection", False)
        
        if auto_language:
            # Get current text to show language detection status
            text = self.text_input.get("1.0", "end-1c").strip()
            if text:
                # Use the TTS engine's comprehensive language detection
                detected_lang = self.tts_engine._detect_language_from_text(text)
                voice_short_name = self.tts_engine._detect_language_voice(text)
                
                if detected_lang and voice_short_name:
                    # Get the actual voice name from settings or use a fallback
                    # Check if user has a custom voice mapping for this language
                    language_mappings = self.settings.get("language_voice_mappings", {})
                    custom_voice = language_mappings.get(detected_lang)
                    
                    if custom_voice:
                        # Use custom voice from settings
                        voice_name = custom_voice
                    else:
                        # Use the detected voice short name and get its display name
                        voice_info = self.tts_engine.get_voice_info(voice_short_name)
                        if voice_info:
                            voice_name = f"{voice_info['name']} ({voice_info['locale']})"
                        else:
                            # Fallback to the detected voice short name
                            voice_name = voice_short_name
                    
                    lang_names = {
                        "zh": "Chinese",
                        "ja": "Japanese", 
                        "ko": "Korean",
                        "ru": "Russian",
                        "ar": "Arabic",
                        "hi": "Hindi",
                        "es": "Spanish",
                        "pt": "Portuguese",
                        "fr": "French",
                        "de": "German",
                        "it": "Italian",
                        "en": "English"
                    }
                    
                    detected_lang_name = lang_names.get(detected_lang, detected_lang.title())
                    new_text = f"{voice_name} (Auto: {detected_lang_name})"
                    new_color = "green"
                    
                    # Animate the voice indicator change
                    self._animate_voice_indicator(new_text, new_color)
                else:
                    self.voice_indicator_value.configure(
                        text=f"{voice} (Auto: Unknown)",
                        text_color="orange"
                    )
            else:
                self.voice_indicator_value.configure(
                    text=f"{voice} (Auto: No text)",
                    text_color="gray"
                )
        else:
            self.voice_indicator_value.configure(
                text=voice,
                text_color="gray"
            )
    
    def _animate_voice_indicator(self, new_text: str, new_color: str):
        """Animate the voice indicator with smooth transitions."""
        # Guard: Skip if already animating to prevent orphaned animation chains
        if self._voice_indicator_animating:
            return
        
        current_text = self.voice_indicator_value.cget("text")
        
        # Only animate if the text actually changed
        if current_text != new_text:
            self._voice_indicator_animating = True
            # Fade out current text
            self._fade_out_text(0.15, lambda: self._fade_in_text_safe(new_text, new_color, 0.15))
    
    def _fade_in_text_safe(self, new_text: str, new_color: str, duration: float):
        """Fade in the new text with animation state cleanup."""
        try:
            self._fade_in_text(new_text, new_color, duration)
        finally:
            self._voice_indicator_animating = False
    
    def _fade_out_text(self, duration: float, callback):
        """Fade out the current text (simplified to single-step clear)."""
        # CustomTkinter doesn't support alpha/color interpolation, so just clear and callback
        self.voice_indicator_value.configure(text="")
        if callback:
            callback()
    
    def _fade_in_text(self, new_text: str, new_color: str, duration: float):
        """Fade in the new text."""
        self.voice_indicator_value.configure(text=new_text, text_color=new_color)
        # Simple fade in by changing opacity of the label
        self._pulse_label(self.voice_indicator_value, duration)
    
    def _pulse_label(self, label, duration: float):
        """Create a subtle pulse animation for a label.
        
        Note: CustomTkinter doesn't support alpha/opacity animation directly.
        This method is kept as a placeholder for potential future enhancements.
        """
        # CustomTkinter doesn't support alpha interpolation
        # The label is already visible with the new text/color
        pass


    
    def _on_text_changed(self):
        """Handle text input changes for typing animation."""
        # Debounce voice indicator update to reduce language detection calls
        if self._voice_indicator_timer:
            self.root.after_cancel(self._voice_indicator_timer)
        self._voice_indicator_timer = self.root.after(300, self._update_voice_indicator)
        
        # Handle typing animation if OSC is enabled
        self._handle_typing_animation()
    
    def _handle_typing_animation(self):
        """Handle typing animation for VRChat OSC chatbox."""
        # Guard: Don't restart typing animation while speaking
        # This prevents KeyRelease events (like Enter key release) from restarting
        # the animation that was just stopped by _on_speak()
        if self._speaking:
            return
        
        # Check if OSC is enabled and connected
        if not self.osc_client or not self.settings.get("vrchat_osc_enabled", False):
            return
        
        # Check if typing animation is enabled
        if not self.settings.get("vrchat_osc_typing_animation", False):
            return
        
        # Update last typing time
        self._last_typing_time = time.time()
        
        # If not already typing, start typing animation
        if not self._is_typing_active:
            self._is_typing_active = True
            # Send typing indicator ON
            self.osc_client.send_typing_indicator(True)
            # Start animation timer
            self._animate_typing_indicator()
        
        # Reset debounce timer
        if self._typing_debounce_timer:
            self.root.after_cancel(self._typing_debounce_timer)
        
        # Set new debounce timer to stop typing after timeout
        timeout_seconds = self.settings.get("vrchat_osc_typing_timeout", 2.0)
        self._typing_debounce_timer = self.root.after(int(timeout_seconds * 1000), self._stop_typing_animation)
    
    def _animate_typing_indicator(self):
        """Animate the typing indicator with dots."""
        if not self._is_typing_active:
            return
        
        # Cycle through animation states: "Typing.", "Typing..", "Typing..."
        animation_texts = ["Typing.", "Typing..", "Typing..."]
        current_text = animation_texts[self._typing_animation_state]
        
        # Send current animation text to chatbox (only if OSC is enabled)
        if self.osc_client and self.settings.get("vrchat_osc_enabled", False):
            self.osc_client.send_to_chatbox(
                current_text,
                play_notification_sound=False,
                show_keyboard=True
            )
        
        # Increment animation state
        self._typing_animation_state = (self._typing_animation_state + 1) % 3
        
        # Schedule next animation frame (1500ms interval to match VRChat rate limit)
        self._typing_animation_timer = self.root.after(1500, self._animate_typing_indicator)
    
    def _stop_typing_animation(self, send_clear: bool = True):
        """Stop the typing animation.
        
        Args:
            send_clear: If True, clear the chatbox after stopping. Set to False
                       when the actual message will replace the typing text,
                       avoiding VRChat's rate limit on chatbox messages.
        """
        # Cancel animation timer
        if self._typing_animation_timer:
            self.root.after_cancel(self._typing_animation_timer)
            self._typing_animation_timer = None
        
        # Cancel debounce timer
        if self._typing_debounce_timer:
            self.root.after_cancel(self._typing_debounce_timer)
            self._typing_debounce_timer = None
        
        # Send typing indicator OFF (only if OSC is enabled)
        if self.osc_client and self.settings.get("vrchat_osc_enabled", False):
            self.osc_client.send_typing_indicator(False)
        
        # Clear chatbox (only if OSC is enabled and send_clear is True)
        # Skip clearing when the actual message will replace the typing text,
        # to avoid consuming VRChat's rate limit slot
        if send_clear and self.osc_client and self.settings.get("vrchat_osc_enabled", False):
            self.osc_client.clear_chatbox()
        
        # Reset state
        self._is_typing_active = False
        self._typing_animation_state = 0
    
    def _on_speak(self):
        """Handle speak button click."""
        # Stop typing animation when speaking (skip clear to avoid rate limit)
        if self._is_typing_active:
            self._stop_typing_animation(send_clear=False)
        
        with self._speaking_lock:
            if self._speaking:
                return
            self._speaking = True
        
        speak_mode = self.settings.get("speak_mode", "current_line")
        if speak_mode == "current_line":
            cursor_index = self.text_input.index("insert")
            line_num = cursor_index.split(".")[0]
            text = self.text_input.get(f"{line_num}.0", f"{line_num}.end").strip()
        else:
            text = self.text_input.get("1.0", "end-1c").strip()
        if not text:
            with self._speaking_lock:
                self._speaking = False
            self._update_ui_speaking(False)
            self._show_error("Current line is empty. Please type some text.")
            return
        
        # Get abbreviations from settings and expand text (with cache)
        abbreviations = self.settings.get("abbreviations", {})
        if abbreviations:
            # Use a stable, content-based cache key instead of id()
            cache_key = (text, tuple(sorted(abbreviations.items())))
            if cache_key in self._abbreviation_cache:
                processed_text = self._abbreviation_cache[cache_key]
            else:
                # Cap cache size to prevent unbounded memory growth
                if len(self._abbreviation_cache) > 100:
                    self._abbreviation_cache.clear()
                processed_text = self._text_preprocessor.expand_abbreviations(text, abbreviations)
                self._abbreviation_cache[cache_key] = processed_text
        else:
            processed_text = text
        
        # Send to VRChat chatbox if OSC is enabled and send_on_speak is True
        if self.osc_client and self.settings.get("vrchat_osc_send_on_speak", False):
            try:
                self.osc_client.send_to_chatbox(
                    processed_text,
                    play_notification_sound=self.settings.get("vrchat_osc_play_sound", True),
                    priority=True  # Actual messages have priority over typing animation
                )
            except Exception:
                self._set_status("Failed to send to VRChat chatbox", "⚠️")
        
        # Clear the stop event for new speak action
        self._stop_event.clear()
        
        self._update_ui_speaking(True)
        self._set_status("Generating speech...", "⏳", "speaking")
        
        # Run TTS in background thread to avoid blocking UI
        self._worker_thread = threading.Thread(target=self._speak_async, args=(processed_text,))
        self._worker_thread.daemon = True
        self._worker_thread.start()




    
    def _speak_async(self, text: str):
        """Run TTS generation and playback in async context."""
        loop = None
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Get settings
            voice = self.settings.get("voice", "en-US-AriaNeural")
            rate = self.settings.get("rate", 0)
            volume = self.settings.get("volume", 100)
            pitch = self.settings.get("pitch", 0)
            device_idx = self.settings.get("device_index")

            enable_normalization = self.settings.get("enable_normalization", True)
            normalization_type = self.settings.get("normalization_type", "Peak")
            processing_profile = self.settings.get("processing_profile", "balanced")
            enable_streaming = self.settings.get("enable_streaming_playback", False)

            # Check if stop was requested before generation
            if self._stop_event.is_set():
                return
            
            # Check if streaming is enabled
            if enable_streaming:
                # Use streaming playback for lower latency
                success = loop.run_until_complete(
                    self._speak_streaming_async(text, voice, rate, volume, pitch, device_idx, processing_profile, enable_normalization, normalization_type)
                )
            else:
                # Use traditional non-streaming playback
                # Update status
                self.root.after(0, lambda: self._set_status("Generating speech...", "🔊"))
                
                # Generate speech with stop event
                audio_data, error = loop.run_until_complete(
                    self.tts_engine.generate_speech(text, voice, rate, volume, pitch, self._stop_event)
                )

                
                # Check if stop was requested during generation
                if self._stop_event.is_set():
                    return
                
                if error:
                    self.root.after(0, lambda: self._show_error(f"TTS Error: {error}"))
                    return
                
                if audio_data:
                    self.root.after(0, lambda: self._set_status("Playing audio...", "▶️"))
                    
                    # Check if voice amplitude feature is enabled for VRChat
                    voice_amplitude_enabled = self.settings.get("vrchat_voice_amplitude_enabled", False)
                    
                    # Start viseme animation if enabled
                    if self._viseme_mapper is not None and self.osc_client is not None:
                        amplitude_callback = None
                        if voice_amplitude_enabled and self._amplitude_analyzer is not None:
                            amplitude_callback = self._amplitude_analyzer.get_amplitude
                        # Get audio duration to synchronize viseme animation with playback
                        audio_duration = self.audio_router.get_audio_duration(audio_data)
                        self._viseme_mapper.start_viseme_animation(
                            text, 
                            self.osc_client.send_viseme, 
                            duration=audio_duration,
                            speech_rate=rate, 
                            amplitude_callback=amplitude_callback
                        )
                    
                    # Play audio - use amplitude playback if VRChat voice amplitude is enabled
                    if voice_amplitude_enabled and self._amplitude_analyzer is not None and self.osc_client is not None:
                        # Create amplitude callback that updates analyzer and forwards to VRChat
                        def amplitude_callback_with_osc(amplitude: float):
                            """Update amplitude analyzer and forward to VRChat OSC."""
                            # Update the local amplitude analyzer (for viseme intensity)
                            self._amplitude_analyzer.update_amplitude(amplitude)
                            # Forward amplitude to VRChat
                            if self.osc_client:
                                self.osc_client.send_voice_amplitude(amplitude)
                        
                        success = loop.run_until_complete(
                            self.audio_router.play_audio_with_amplitude(
                                audio_data, 
                                48000, 
                                device_idx,
                                enable_normalization,
                                normalization_type,
                                amplitude_callback=amplitude_callback_with_osc,
                                processing_profile=processing_profile
                            )
                        )
                    else:
                        # Use standard playback without amplitude callback
                        success = loop.run_until_complete(
                            self.audio_router.play_audio_to_device(
                                audio_data, 
                                48000, 
                                device_idx,
                                enable_normalization,
                                normalization_type,
                                processing_profile
                            )
                        )

            # Do not show Finished or success UI when user stopped or playback was interrupted
            if self._stop_event.is_set():
                return
            if not success:
                self.root.after(0, lambda: self._show_error("Failed to play audio to device."))
                return
            self.root.after(0, lambda: self._set_status("Finished", "✅"))
            
        except Exception as e:
            self.root.after(0, lambda: self._show_error(f"Error: {str(e)}"))
        finally:
            if loop:
                loop.close()
            with self._speaking_lock:
                self._speaking = False
            self._worker_thread = None
            self.root.after(0, lambda: self._update_ui_speaking(False))
    
    async def _speak_streaming_async(self, text: str, voice: str, rate: int, volume: int, pitch: int, device_idx, processing_profile: str, enable_normalization: bool = True, normalization_type: str = "Peak") -> bool:
        """
        Stream TTS generation and playback for lower latency.
        
        This method starts playing audio as soon as the first chunks arrive,
        rather than waiting for the entire audio to be generated.
        
        Args:
            text: Text to speak
            voice: Voice identifier
            rate: Speech rate
            volume: Volume level
            pitch: Pitch adjustment
            device_idx: Output device index
            processing_profile: Processing profile name
            enable_normalization: Whether to apply normalization
            normalization_type: Type of normalization ("Peak", "RMS", "LUFS", or "None")
        """
        try:
            # Update status
            self.root.after(0, lambda: self._set_status("Streaming speech...", "🔊"))
            
            # Check if voice amplitude feature is enabled for VRChat
            voice_amplitude_enabled = self.settings.get("vrchat_voice_amplitude_enabled", False)
            
            # Start viseme animation if enabled (use estimated duration for streaming)
            if self._viseme_mapper is not None and self.osc_client is not None:
                # Estimate duration based on text length and speech rate
                # Average speaking rate is ~150 words per minute, ~5 chars per word
                estimated_duration = len(text) / 5 / 150 * 60  # seconds
                # Adjust for speech rate
                if rate != 0:
                    estimated_duration *= (100 - rate) / 100
                
                # Get amplitude callback if enabled
                amplitude_callback = None
                if voice_amplitude_enabled and self._amplitude_analyzer is not None:
                    amplitude_callback = self._amplitude_analyzer.get_amplitude
                
                self._viseme_mapper.start_viseme_animation(
                    text, 
                    self.osc_client.send_viseme, 
                    duration=estimated_duration,
                    speech_rate=rate,
                    amplitude_callback=amplitude_callback
                )
            
            # Create the audio chunk generator
            audio_generator = self.tts_engine.stream_speech(
                text, voice, rate, volume, pitch, self._stop_event
            )
            
            # Create amplitude callback for streaming playback if VRChat voice amplitude is enabled
            streaming_amplitude_callback = None
            if voice_amplitude_enabled and self._amplitude_analyzer is not None and self.osc_client is not None:
                def streaming_amplitude_callback_with_osc(amplitude: float):
                    """Update amplitude analyzer and forward to VRChat OSC during streaming."""
                    # Update the local amplitude analyzer (for viseme intensity)
                    self._amplitude_analyzer.update_amplitude(amplitude)
                    # Forward amplitude to VRChat
                    if self.osc_client:
                        self.osc_client.send_voice_amplitude(amplitude)
                streaming_amplitude_callback = streaming_amplitude_callback_with_osc
            
            # Play streaming audio
            success = await self.audio_router.play_audio_streaming(
                audio_generator,
                48000,
                device_idx,
                processing_profile,
                self._stop_event,
                enable_normalization,
                normalization_type,
                amplitude_callback=streaming_amplitude_callback
            )
            
            return success
            
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Streaming playback error: {e}")
            return False



    
    def _on_stop(self):
        """Handle stop button click."""
        # Stop typing animation when aborting (clear chatbox since no message will replace it)
        if self._is_typing_active:
            self._stop_typing_animation(send_clear=True)
        
        # Set stop event to signal background thread to stop
        self._stop_event.set()
        self.audio_router.stop_playback()
        if self._viseme_mapper is not None:
            self._viseme_mapper.stop_viseme_animation()
        with self._speaking_lock:
            self._speaking = False
        self._update_ui_speaking(False)
        self._set_status("Stopped", "⏹")

    
    def _on_clear(self):
        """Handle clear button click."""
        # Stop typing animation when clearing (clear chatbox since no message will replace it)
        if self._is_typing_active:
            self._stop_typing_animation(send_clear=True)
        
        self.text_input.delete("1.0", "end")
        self.text_input.focus()
    
    def _on_settings(self):
        """Handle settings button click."""
        self.on_open_settings()
    
    def _on_toggle_overlay(self):
        """Handle overlay toggle button click."""
        # Flip visibility state
        self._overlay_visible = not self._overlay_visible
        
        # Persist to settings and save to disk
        self.settings.set("overlay_visible", self._overlay_visible)
        self.settings.save_settings()
        # Update overlay visibility
        if self._overlay_visible:
            self._recording_overlay.show_overlay()
            # Sync current recording state
            self._recording_overlay.set_recording(self._stt_recording)
            # Update button appearance to active
            self.overlay_button.configure(
                fg_color=COLOR_PRIMARY,
                hover_color=COLOR_PRIMARY_HOVER
            )
        else:
            self._recording_overlay.hide_overlay()
            # Update button appearance to inactive
            self.overlay_button.configure(
                fg_color=COLOR_NEUTRAL_MEDIUM,
                hover_color=COLOR_NEUTRAL
            )
    
    def _on_voice_input(self):
        """Handle voice input button click - toggle recording."""
        if not self.stt_engine:
            self._set_status("Voice input not available", "⚠️")
            return
        
        if not self._stt_recording:
            # Start recording
            success = self.stt_engine.start_listening()
            if success:
                self._stt_recording = True
                self.voice_button.configure(
                    text="⏹  Stop Voice",
                    fg_color=COLOR_DANGER,
                    hover_color=COLOR_DANGER_HOVER
                )
                self._set_status("🎙 Listening… click again to stop", "🎙")
                # Sync overlay state
                if self._overlay_visible and self._recording_overlay:
                    self._recording_overlay.set_recording(True)
            else:
                self._set_status("Failed to start voice recording", "⚠️")
        else:
            # Stop recording and transcribe
            self.voice_button.configure(state="disabled")
            self._stt_recording = False
            self._set_status("⏳ Transcribing…", "⏳")
            # Sync overlay state
            if self._overlay_visible and self._recording_overlay:
                self._recording_overlay.set_recording(False)
            self.stt_engine.stop_and_transcribe(
                on_result=self._on_stt_result,
                on_error=self._on_stt_error
            )
    
    def _on_voice_input_toggle(self):
        """Handle voice input toggle keybind - toggle recording based on current state."""
        if not self.stt_engine:
            self._set_status("Voice input not available", "⚠️")
            return
        
        if not self._stt_recording:
            # Start recording
            success = self.stt_engine.start_listening()
            if success:
                self._stt_recording = True
                self.voice_button.configure(
                    text="⏹  Stop Voice",
                    fg_color=COLOR_DANGER,
                    hover_color=COLOR_DANGER_HOVER
                )
                self._set_status("🎙 Listening… press keybind again to stop", "🎙")
                # Sync overlay state
                if self._overlay_visible and self._recording_overlay:
                    self._recording_overlay.set_recording(True)
            else:
                self._set_status("Failed to start voice recording", "⚠️")
        else:
            # Stop recording and transcribe
            self.voice_button.configure(state="disabled")
            self._stt_recording = False
            self._set_status("⏳ Transcribing…", "⏳")
            # Sync overlay state
            if self._overlay_visible and self._recording_overlay:
                self._recording_overlay.set_recording(False)
            self.stt_engine.stop_and_transcribe(
                on_result=self._on_stt_result,
                on_error=self._on_stt_error
            )
    
    def _on_stt_result(self, text: str):
        """Handle successful STT transcription (called from background thread)."""
        # Use root.after to safely update UI from background thread
        self.root.after(0, lambda: self._insert_stt_text(text))
    
    def _insert_stt_text(self, text: str):
        """Insert transcribed text into the text input (called on main thread)."""
        # Apply abbreviation expansion if enabled
        apply_abbreviations = self.settings.get("stt_apply_abbreviations", False)
        if apply_abbreviations:
            abbreviations = self.settings.get("abbreviations", {})
            if abbreviations:
                text = self._text_preprocessor.expand_abbreviations(text, abbreviations)
        
        # Apply word corrections if configured
        corrections = self.settings.get("stt_corrections", {})
        if corrections:
            text = self._text_preprocessor.expand_abbreviations(text, corrections)
        
        # Insert text at current cursor position
        self.text_input.insert("insert", text)
        
        # Restore voice button to idle state
        self._restore_voice_button()
        
        # Update status
        self._set_status("✅ Voice input added", "✅")
        
        # Check if auto-speak is enabled and automatically speak the text
        if self.settings.get("stt_auto_speak", False) and text.strip():
            # Automatically trigger speak after a short delay to let UI update
            self.root.after(100, self._on_speak)
    
    def _on_stt_error(self, exception: Exception):
        """Handle STT error (called from background thread)."""
        # Use root.after to safely update UI from background thread
        self.root.after(0, lambda: self._handle_stt_error(exception))
    
    def _handle_stt_error(self, exception: Exception):
        """Handle STT error on main thread."""
        # Restore voice button to idle state
        self._restore_voice_button()
        
        # Show appropriate error message
        import speech_recognition as sr
        if isinstance(exception, sr.UnknownValueError):
            self._set_status("⚠ Could not understand audio", "⚠️")
        elif isinstance(exception, sr.RequestError):
            self._set_status("⚠ Network error - check connection", "⚠️")
        else:
            self._set_status(f"⚠ Voice input error: {str(exception)}", "⚠️")
    
    def _restore_voice_button(self):
        """Restore voice button to idle state."""
        self.voice_button.configure(
            text="🎙  Voice",
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            state="normal"
        )
        # Sync overlay state
        if self._overlay_visible and self._recording_overlay:
            self._recording_overlay.set_recording(False)
    
    def _update_ui_speaking(self, speaking: bool):
        """Update UI state based on speaking status with smooth animations."""
        if speaking:
            # Animate speak button to disabled/speaking state
            self._animate_button(self.speak_button, "disabled", "▶  Speaking...", COLOR_NEUTRAL_MEDIUM, ANIMATION_NORMAL)
            # Animate stop button to active state
            self._animate_button(self.stop_button, "normal", "⏹  Stop", COLOR_WARNING, ANIMATION_NORMAL)
            # Animate clear button to disabled state
            self._animate_button(self.clear_button, "disabled", "🗑  Clear", COLOR_NEUTRAL, ANIMATION_NORMAL)
        else:
            # Animate speak button back to normal
            self._animate_button(self.speak_button, "normal", "▶  Speak", COLOR_SUCCESS, ANIMATION_NORMAL)
            # Animate stop button back to disabled
            self._animate_button(self.stop_button, "disabled", "⏹  Stop", COLOR_NEUTRAL_MEDIUM, ANIMATION_NORMAL)
            # Animate clear button back to normal
            self._animate_button(self.clear_button, "normal", "🗑  Clear", COLOR_NEUTRAL_MEDIUM, ANIMATION_NORMAL)
    
    def _animate_button(self, button, state: str, text: str, color: str, duration: float):
        """Animate a button with smooth color and text transitions."""
        # Store original color for hover effect
        button._original_color = color
        
        # Animate color change
        self._animate_button_color(button, color, duration)
        
        # Update text and state
        button.configure(text=text, state=state)
    
    def _animate_button_color(self, button, target_color: str, duration: float):
        """Animate button color transition."""
        # CustomTkinter doesn't support direct color interpolation, so we use a pulse effect
        self._pulse_button(button, target_color, duration)
    
    def _pulse_button(self, button, target_color: str, duration: float):
        """Create a pulse effect for button animation."""
        button.configure(fg_color=target_color)
        # Add a subtle scale effect by changing size slightly
        # Use the constant to prevent width accumulation on rapid repeated calls
        button.configure(width=BUTTON_WIDTH_DEFAULT + 2)
        
        def reset_size():
            try:
                button.configure(width=BUTTON_WIDTH_DEFAULT)
            except Exception:
                pass  # Button may have been destroyed or reconfigured
        
        self.root.after(int(duration * 500), reset_size)
    
    def _set_status(self, message: str, icon: str = "", message_type: str = "info"):
        """Update status message with enhanced formatting and visual indicators."""
        # Format message with timestamp for better logging
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        
        # Animate status text change
        self._animate_status_change(f"{icon} {formatted_message}" if icon else formatted_message, message_type)
        
        # Update activity indicator based on message type
        self._animate_activity_indicator(message_type)
    
    def _animate_status_change(self, new_text: str, message_type: str):
        """Animate the status text change with smooth transitions."""
        current_text = self.status_label.cget("text")
        
        # Only animate if text changed
        if current_text != new_text:
            # Fade out current text
            self._fade_out_status(0.1, lambda: self._fade_in_status(new_text, 0.1))
    
    def _fade_out_status(self, duration: float, callback):
        """Fade out the current status text (simplified to single-step clear)."""
        # CustomTkinter doesn't support alpha/color interpolation, so just clear and callback
        self.status_label.configure(text="")
        if callback:
            callback()
    
    def _fade_in_status(self, new_text: str, duration: float):
        """Fade in the new status text."""
        self.status_label.configure(text=new_text)
        # Pulse effect for the new status
        self._pulse_label(self.status_label, duration)
    
    def _animate_activity_indicator(self, message_type: str):
        """Animate the activity indicator based on message type."""
        # Get target color based on message type
        color_map = {
            "speaking": "#2ecc71",  # Green for active
            "error": "#e74c3c",     # Red for error
            "warning": "#f39c12",   # Orange for warning
            "success": "#27ae60",   # Dark green for success
            "info": "gray60"        # Gray for normal
        }
        
        target_color = color_map.get(message_type, "gray60")
        
        # Animate color change
        self._animate_indicator_color(self.activity_indicator, target_color, 0.2)
    
    def _animate_indicator_color(self, indicator, target_color: str, duration: float):
        """Animate indicator color transition."""
        indicator.configure(text_color=target_color)
        # Add a subtle pulse effect
        self._pulse_label(indicator, duration)
    
    def _set_progress(self, message: str):
        """Update progress indicator."""
        self.progress_label.configure(text=message)
        if message:
            self.progress_label.pack(side="right", padx=5)
        else:
            self.progress_label.pack_forget()
    
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
        label.pack(padx=20, pady=20)
        
        ok_button = ctk.CTkButton(
            dialog,
            text="OK",
            command=dialog.destroy
        )
        ok_button.pack(pady=10)
        
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
    
    def refresh_status(self):
        """Refresh status display (called after settings change)."""
        self._abbreviation_cache.clear()
        self._update_status()
        self._setup_viseme_mapper()
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
        
        # Unpack all toggleable buttons AND settings button
        for _, button in toggleable_buttons:
            button.pack_forget()
        self.settings_button.pack_forget()
        
        # Re-pack only visible toggleable buttons in fixed order
        for name, button in toggleable_buttons:
            if name in visible_buttons:
                button.pack(side="left", padx=SPACING_SM, pady=SPACING_SM)
        
        # Always re-pack settings button last
        self.settings_button.pack(side="left", padx=SPACING_SM, pady=SPACING_SM)
    
    def set_text(self, text: str):
        """Set text in the input area."""
        self.text_input.delete("1.0", "end")
        self.text_input.insert("1.0", text)

    
    def get_text(self) -> str:
        """Get text from the input area."""
        return self.text_input.get("1.0", "end-1c")
    
    def _setup_osc_client(self):
        """Setup OSC client for VRChat chatbox integration."""
        # Disconnect existing client if any
        if self.osc_client:
            try:
                self.osc_client.disconnect()
            except Exception:
                pass
            self.osc_client = None
        
        # Check if OSC is enabled
        if not self.settings.get("vrchat_osc_enabled", False):
            # Also clear viseme mapper when OSC is disabled
            self._setup_viseme_mapper()
            return
        
        # Get OSC settings
        ip = self.settings.get("vrchat_osc_ip", "127.0.0.1")
        port = self.settings.get("vrchat_osc_port", 9000)
        
        # Create and connect client
        try:
            self.osc_client = VRChatOSCClient(ip=ip, port=port)
            if self.osc_client.connect():
                self._set_status(f"OSC connected to {ip}:{port}", "✅")
            else:
                self._set_status(f"OSC failed to connect to {ip}:{port}", "⚠️")
                self.osc_client = None
        except Exception:
            self._set_status("OSC setup failed", "⚠️")
            self.osc_client = None
        
        # Setup viseme mapper after OSC client is configured
        self._setup_viseme_mapper()
    
    def _setup_viseme_mapper(self):
        """Setup viseme mapper for VRChat lip-sync integration."""
        # Stop and clear existing viseme mapper if any
        if self._viseme_mapper is not None:
            self._viseme_mapper.stop_viseme_animation()
            self._viseme_mapper = None
        
        self._amplitude_analyzer = None
        
        # Check if viseme is enabled and OSC client is connected
        viseme_enabled = self.settings.get("vrchat_viseme_enabled", False)
        if not viseme_enabled:
            return
        
        if self.osc_client is None:
            return
        
        # Get viseme settings
        smoothing = self.settings.get("vrchat_viseme_smoothing", 0.5)
        amplitude_enabled = self.settings.get("vrchat_voice_amplitude_enabled", False)
        
        # Instantiate viseme mapper
        self._viseme_mapper = VisemeMapper(smoothing=smoothing)
        
        # Instantiate amplitude analyzer if amplitude mode is enabled
        if amplitude_enabled:
            self._amplitude_analyzer = AmplitudeAnalyzer()
    
    def _setup_recording_overlay(self):
        """Setup the recording overlay window."""
        # Create the overlay
        self._recording_overlay = RecordingOverlay(self.root)
        
        # Show or hide based on saved preference
        if self._overlay_visible:
            self._recording_overlay.show_overlay()
        else:
            self._recording_overlay.hide_overlay()
    
    def shutdown(self):
        """Gracefully shutdown the main window and wait for worker threads."""
        # Stop typing animation if active
        if self._is_typing_active:
            self._stop_typing_animation()
        
        # Signal stop to any running TTS operation
        self._stop_event.set()
        
        # Stop audio playback
        self.audio_router.stop_playback()
        
        # Stop viseme animation if active
        if self._viseme_mapper is not None:
            self._viseme_mapper.stop_viseme_animation()
        
        # Disconnect OSC client
        if self.osc_client:
            try:
                self.osc_client.disconnect()
            except Exception:
                pass
            self.osc_client = None
        
        # Shutdown STT engine if available
        if self.stt_engine:
            self.stt_engine.shutdown()
        
        # Destroy recording overlay if it exists
        if self._recording_overlay:
            try:
                self._recording_overlay.destroy()
            except Exception:
                pass
            self._recording_overlay = None
        
        # Wait for worker threads to complete (with timeout)
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
        
        # Unregister all keybinds
        self.keybind_manager.unregister_all(self.root)
