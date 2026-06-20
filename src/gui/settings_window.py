"""
Settings Window GUI Module
Modal settings dialog for voice, audio device, and appearance configuration.
"""
import copy
import logging
import customtkinter as ctk
from typing import Optional, Callable, List, Dict, Any

from .settings_tabs import (
    VoiceTab, AudioOutputTab, AppearanceTab, AbbreviationsTab,
    KeybindsTab, BehaviorTab, SoundboardTab, VRChatOSCTab, AdvancedTab, TTSProviderTab
)
from .utils.scroll_utils import prevent_scroll_propagation
from .theme_constants import (
    SPACING_XS, SPACING_SM, SPACING_MD, SPACING_LG, SPACING_XL, SPACING_2XL,
    COLOR_SUCCESS, COLOR_SUCCESS_HOVER, COLOR_SUCCESS_LIGHT,
    COLOR_DANGER, COLOR_DANGER_HOVER, COLOR_DANGER_LIGHT,
    COLOR_PRIMARY, COLOR_PRIMARY_HOVER, COLOR_PRIMARY_LIGHT,
    COLOR_ACCENT, COLOR_ACCENT_HOVER,
    COLOR_INFO, COLOR_WARNING,
    COLOR_NEUTRAL_DARKEST, COLOR_NEUTRAL_DARK, COLOR_NEUTRAL_MEDIUM, COLOR_NEUTRAL_LIGHT, COLOR_NEUTRAL_LIGHTER,
    COLOR_BG_PRIMARY, COLOR_BG_SECONDARY, COLOR_BG_TERTIARY,
    FONT_XS, FONT_SM, FONT_MD, FONT_LG, FONT_XL, FONT_2XL, FONT_WEIGHT_BOLD,
    BUTTON_HEIGHT, BUTTON_HEIGHT_SM, BUTTON_HEIGHT_LG, BUTTON_MIN_WIDTH, BUTTON_WIDTH_DEFAULT,
    FRAME_BUTTONS_HEIGHT, INPUT_HEIGHT, INPUT_HEIGHT_SM,
    RADIUS_SM, RADIUS_MD, RADIUS_LG, RADIUS_XL,
    ANIMATION_FAST, ANIMATION_NORMAL, ANIMATION_SLOW,
    WINDOW_SETTINGS_WIDTH, WINDOW_SETTINGS_HEIGHT,
    WINDOW_SETTINGS_MIN_WIDTH, WINDOW_SETTINGS_MIN_HEIGHT,
    SETTINGS_TAB_SELECTED_COLOR, SETTINGS_TAB_SELECTED_HOVER,
    SETTINGS_TAB_UNSELECTED_HOVER, SETTINGS_TAB_TEXT_COLOR,
    get_settings_surface_theme,
)

logger = logging.getLogger(__name__)

SETTINGS_TAB_ORDER = (
    "Voice",
    "Audio Output",
    "Appearance",
    "Abbreviations",
    "Keybinds",
    "Behavior",
    "Soundboard",
    "VRChat OSC",
    "Advanced",
    "TTS Provider",
)

SETTINGS_TAB_OBJECT_ATTRIBUTES = {
    "Voice": "voice_tab_obj",
    "Audio Output": "audio_tab_obj",
    "Appearance": "appearance_tab_obj",
    "Abbreviations": "abbreviations_tab_obj",
    "Keybinds": "keybinds_tab_obj",
    "Behavior": "behavior_tab_obj",
    "Soundboard": "soundboard_tab_obj",
    "VRChat OSC": "vrchat_osc_tab_obj",
    "Advanced": "advanced_tab_obj",
    "TTS Provider": "provider_tab_obj",
}

EAGER_SETTINGS_TABS = frozenset(("Voice", "Advanced", "TTS Provider"))


def get_settings_tabview_style(
    mode: Optional[str] = None,
    *,
    surface_theme: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    """Return the shared style used by the settings tab chrome."""
    resolved_surface_theme = (
        surface_theme
        if surface_theme is not None
        else get_settings_surface_theme(mode)
    )
    return {
        "fg_color": resolved_surface_theme["pane_fg"],
        "corner_radius": resolved_surface_theme["shell_corner_radius"],
        "border_width": 1,
        "border_color": resolved_surface_theme["border_color"],
        "segmented_button_fg_color": resolved_surface_theme["section_fg"],
        "segmented_button_selected_color": resolved_surface_theme["tab_selected_color"],
        "segmented_button_selected_hover_color": resolved_surface_theme["tab_selected_hover"],
        "segmented_button_unselected_color": resolved_surface_theme["pane_fg"],
        "segmented_button_unselected_hover_color": resolved_surface_theme["tab_unselected_hover"],
        "text_color": resolved_surface_theme["tab_text_color"],
    }


class SettingsWindow:
    """Settings dialog window for CriTTS Recoded."""
    
    def __init__(
        self,
        parent: ctk.CTk,
        settings_manager,
        tts_engine,
        audio_router,
        on_save: Optional[Callable] = None
    ):
        self.parent = parent
        self.settings = settings_manager
        self.tts_engine = tts_engine
        self.audio_router = audio_router
        self.on_save = on_save
        
        self._create_window()
        self._on_refresh()


    
    def _create_window(self):
        """Create the settings window with a minimum safe layout size."""
        self.window = ctk.CTkToplevel(self.parent)
        self.window.title("Settings - CriTTS Recoded")
        self.window.geometry(f"{WINDOW_SETTINGS_WIDTH}x{WINDOW_SETTINGS_HEIGHT}")
        self.window.minsize(WINDOW_SETTINGS_MIN_WIDTH, WINDOW_SETTINGS_MIN_HEIGHT)
        self.window.transient(self.parent)
        self.window.grab_set()
        
        # Center window
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() // 2) - (WINDOW_SETTINGS_WIDTH // 2)
        y = (self.window.winfo_screenheight() // 2) - (WINDOW_SETTINGS_HEIGHT // 2)
        self.window.geometry(f"+{x}+{y}")

        self._build_window_content()

    def _build_window_content(self, selected_tab: Optional[str] = None):
        """Build the settings shell using the current appearance mode."""
        try:
            appearance_mode = ctk.get_appearance_mode()
        except Exception:
            appearance_mode = "Dark"
        surface_theme = get_settings_surface_theme(appearance_mode)
        self.window.configure(fg_color=surface_theme["window_fg"])

        # Configure grid
        self.window.grid_columnconfigure(0, weight=1)
        self.window.grid_rowconfigure(0, weight=1)  # Content expands
        self.window.grid_rowconfigure(1, weight=0)  # Buttons fixed
        
        # Main container with standardized padding
        self.main_frame = ctk.CTkFrame(self.window, fg_color=surface_theme["window_fg"])
        self.main_frame.grid(row=0, column=0, padx=0, pady=0, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=1)  # Tabview expands
        self.window.bind("<Configure>", self._on_settings_resize)
        
        # Title with theme font
        self.title_label = ctk.CTkLabel(
            self.main_frame,
            text="Settings",
            font=ctk.CTkFont(size=FONT_XL, weight=FONT_WEIGHT_BOLD),
            text_color=surface_theme["text_primary"],
        )
        self.title_label.grid(row=0, column=0, padx=SPACING_MD, pady=(SPACING_MD, SPACING_LG), sticky="w")
         
        # Create tabbed interface with consistent padding
        self.tabview = ctk.CTkTabview(
            self.main_frame,
            command=self._on_tab_selected,
            **get_settings_tabview_style(
                appearance_mode,
                surface_theme=surface_theme,
            ),
        )
        self.tabview.grid(row=1, column=0, padx=SPACING_LG, pady=SPACING_LG, sticky="nsew")
        
        self._initialize_tab_hydration_state()
        self._register_tab_factory(
            "Voice",
            VoiceTab,
            parent_window=self.window,
        )
        self._register_tab_factory("Audio Output", AudioOutputTab)
        self._register_tab_factory("Appearance", AppearanceTab)
        self._register_tab_factory("Abbreviations", AbbreviationsTab)
        self._register_tab_factory("Keybinds", KeybindsTab)
        self._register_tab_factory("Behavior", BehaviorTab)
        self._register_tab_factory("Soundboard", SoundboardTab)
        self._register_tab_factory(
            "VRChat OSC",
            VRChatOSCTab,
            parent_window=self.parent,
        )
        self._register_tab_factory("Advanced", AdvancedTab)
        self._register_tab_factory("TTS Provider", TTSProviderTab)
        self._hydrate_initial_tabs(selected_tab)
        
        # Buttons frame - fixed at bottom with standardized padding
        self.buttons_frame = ctk.CTkFrame(
            self.window,
            fg_color=surface_theme["pane_fg"],
            corner_radius=RADIUS_LG,
            border_width=1,
            border_color=surface_theme["border_color"],
        )
        self.buttons_frame.grid(row=1, column=0, padx=SPACING_LG, pady=(0, SPACING_MD), sticky="ew")
        
        # Save button with theme colors
        self.save_button = ctk.CTkButton(
            self.buttons_frame,
            text="Save",
            font=ctk.CTkFont(size=FONT_MD, weight=FONT_WEIGHT_BOLD),
            command=self._on_save,
            fg_color=COLOR_SUCCESS,
            hover_color=COLOR_SUCCESS_HOVER,
            width=BUTTON_WIDTH_DEFAULT,
            height=BUTTON_HEIGHT,
            corner_radius=RADIUS_MD,
        )
        self.save_button.pack(side="right", padx=SPACING_SM, pady=SPACING_SM)

        # Apply button (saves without closing)
        self.apply_button = ctk.CTkButton(
            self.buttons_frame,
            text="Apply",
            font=ctk.CTkFont(size=FONT_MD, weight=FONT_WEIGHT_BOLD),
            command=self._on_apply,
            fg_color=COLOR_SUCCESS,
            hover_color=COLOR_SUCCESS_HOVER,
            width=BUTTON_WIDTH_DEFAULT,
            height=BUTTON_HEIGHT,
            corner_radius=RADIUS_MD,
        )
        self.apply_button.pack(side="right", padx=SPACING_SM, pady=SPACING_SM)

        # Cancel button
        self.cancel_button = ctk.CTkButton(
            self.buttons_frame,
            text="Cancel",
            font=ctk.CTkFont(size=FONT_MD),
            command=self._on_cancel,
            fg_color=surface_theme["button_neutral"],
            hover_color=surface_theme["button_neutral_hover"],
            width=BUTTON_WIDTH_DEFAULT,
            height=BUTTON_HEIGHT,
            corner_radius=RADIUS_MD,
        )
        self.cancel_button.pack(side="right", padx=SPACING_SM, pady=SPACING_SM)
        
        # Reset to Defaults button
        self.reset_button = ctk.CTkButton(
            self.buttons_frame,
            text="Reset to Defaults",
            font=ctk.CTkFont(size=FONT_MD),
            command=self._on_reset_to_defaults,
            fg_color=COLOR_DANGER,
            hover_color=COLOR_DANGER_HOVER,
            width=BUTTON_WIDTH_DEFAULT,
            height=BUTTON_HEIGHT,
            corner_radius=RADIUS_MD,
        )
        self.reset_button.pack(side="left", padx=SPACING_SM, pady=SPACING_SM)
        
        # Refresh button
        self.refresh_button = ctk.CTkButton(
            self.buttons_frame,
            text="Refresh",
            font=ctk.CTkFont(size=FONT_MD),
            command=self._on_refresh,
            fg_color=surface_theme["button_neutral"],
            hover_color=surface_theme["button_neutral_hover"],
            width=BUTTON_WIDTH_DEFAULT,
            height=BUTTON_HEIGHT,
            corner_radius=RADIUS_MD,
        )
        self.refresh_button.pack(side="left", padx=SPACING_SM, pady=SPACING_SM)
        
        # Bind X-button to cancel handler so it doesn't leak dirty in-memory state
        self.window.protocol("WM_DELETE_WINDOW", self._on_cancel)

        if selected_tab in SETTINGS_TAB_ORDER:
            self.tabview.set(selected_tab)

    def refresh_theme(self):
        """Rebuild the settings shell so explicit surface colors follow the active mode."""
        selected_tab = None
        if hasattr(self, "tabview"):
            try:
                selected_tab = self.tabview.get()
            except Exception:
                selected_tab = None

        for tab in getattr(self, "tabs", []):
            invalidate_async_callbacks = getattr(tab, "invalidate_async_callbacks", None)
            if callable(invalidate_async_callbacks):
                invalidate_async_callbacks()

        for child in self.window.winfo_children():
            child.destroy()

        self._build_window_content(selected_tab=selected_tab)
        self._on_refresh()

    def _on_settings_resize(self, event):
        """Broadcast window resize to all hydrated tabs."""
        if event.widget != self.window:
            return
        for tab in getattr(self, 'tabs', []):
            scaler = getattr(tab, 'update_scale', None)
            if callable(scaler):
                scaler(event.width)

    def _teardown_tabs(self) -> None:
        """Invalidate async callbacks on every tab before the settings window is destroyed."""
        for tab in getattr(self, "tabs", []):
            invalidate = getattr(tab, "invalidate_async_callbacks", None)
            if callable(invalidate):
                invalidate()

    def _initialize_tab_hydration_state(self) -> None:
        """Reset tab bookkeeping before registering the current shell's tab factories."""
        self.tabs = []
        self._tab_objects: Dict[str, Any] = {}
        self._tab_factories: Dict[str, Callable[[], Any]] = {}

        for tab_name in SETTINGS_TAB_ORDER:
            setattr(self, SETTINGS_TAB_OBJECT_ATTRIBUTES[tab_name], None)

    def _register_tab_factory(
        self,
        tab_name: str,
        tab_class: Any,
        *,
        parent_window: Optional[ctk.CTk] = None,
    ) -> None:
        """Create a tab container immediately but defer tab-object construction until needed."""
        tab_frame = self.tabview.add(tab_name)
        tab_frame.configure(fg_color="transparent")

        def build_tab() -> Any:
            init_kwargs = {}
            if parent_window is not None:
                init_kwargs["parent_window"] = parent_window

            return tab_class(
                tab_frame,
                self.settings,
                self.tts_engine,
                self.audio_router,
                self._on_change_placeholder,
                **init_kwargs,
            )

        self._tab_factories[tab_name] = build_tab

    def _sync_tabs_in_display_order(self) -> None:
        """Keep the hydrated-tab list aligned with SETTINGS_TAB_ORDER."""
        self.tabs = [
            self._tab_objects[tab_name]
            for tab_name in SETTINGS_TAB_ORDER
            if tab_name in self._tab_objects
        ]

    def _wire_provider_voice_callback(self) -> None:
        """Reconnect provider -> voice live updates once both tabs exist."""
        provider_tab = self._tab_objects.get("TTS Provider")
        voice_tab = self._tab_objects.get("Voice")
        if provider_tab is None or voice_tab is None:
            return

        set_voice_tab_callback = getattr(provider_tab, "set_voice_tab_callback", None)
        reload_for_provider = getattr(voice_tab, "reload_for_provider", None)
        if callable(set_voice_tab_callback) and callable(reload_for_provider):
            set_voice_tab_callback(reload_for_provider)

    def _ensure_tab_hydrated(self, tab_name: str) -> Optional[Any]:
        """Instantiate a tab object once, keeping tab order and callbacks intact."""
        if tab_name not in SETTINGS_TAB_ORDER:
            return None

        if tab_name in self._tab_objects:
            return self._tab_objects[tab_name]

        tab_factory = self._tab_factories.get(tab_name)
        if tab_factory is None:
            return None

        tab_object = tab_factory()
        self._tab_objects[tab_name] = tab_object
        setattr(self, SETTINGS_TAB_OBJECT_ATTRIBUTES[tab_name], tab_object)
        self._sync_tabs_in_display_order()
        self._wire_provider_voice_callback()
        return tab_object

    def _hydrate_initial_tabs(self, selected_tab: Optional[str]) -> None:
        """Eagerly build dependency-critical tabs plus the visible tab."""
        initial_tab = selected_tab if selected_tab in SETTINGS_TAB_ORDER else SETTINGS_TAB_ORDER[0]
        for tab_name in SETTINGS_TAB_ORDER:
            if tab_name in EAGER_SETTINGS_TABS or tab_name == initial_tab:
                self._ensure_tab_hydrated(tab_name)

    def _ensure_all_tabs_hydrated(self) -> None:
        """Materialize all tabs before save/validate paths that require full parity."""
        if not hasattr(self, "_tab_factories") or not hasattr(self, "_tab_objects"):
            return

        for tab_name in SETTINGS_TAB_ORDER:
            self._ensure_tab_hydrated(tab_name)

    def _on_tab_selected(self) -> None:
        """Hydrate tabs lazily the first time users navigate to them."""
        tabview = getattr(self, "tabview", None)
        if tabview is None:
            return

        try:
            selected_tab = tabview.get()
        except Exception:
            return

        if selected_tab in SETTINGS_TAB_ORDER:
            self._ensure_tab_hydrated(selected_tab)

    def _on_refresh(self):
        """Reload data for all tabs."""
        for tab in self.tabs:
            if hasattr(tab, '_load_data') and callable(tab._load_data):
                tab._load_data()

    def _on_change_placeholder(self, *args, **kwargs):
        return

    def _notify_settings_saved(self):
        """Run the shared live-apply callback used by save/apply/reset flows."""
        if self.on_save:
            self.on_save()

    def _tab_settings_change_current_state(self, all_tab_settings: List[Dict[str, object]]) -> bool:
        """Return True when Apply would change the current in-memory settings state."""
        get_all_settings = getattr(self.settings, "get_all", None)
        if not callable(get_all_settings):
            return True

        current_settings = get_all_settings()
        if not isinstance(current_settings, dict):
            return True

        for tab_settings in all_tab_settings:
            for key, value in tab_settings.items():
                if current_settings.get(key) != value:
                    return True

        return False

    def _schedule_refresh_theme(self) -> None:
        """Defer settings shell rebuilding until the current UI callback frame has finished."""
        window = getattr(self, "window", None)
        if window is None:
            return

        if getattr(self, "_refresh_theme_scheduled", False):
            return

        self._refresh_theme_scheduled = True

        def refresh_if_window_alive() -> None:
            self._refresh_theme_scheduled = False
            try:
                winfo_exists = getattr(window, "winfo_exists", None)
                if callable(winfo_exists) and not winfo_exists():
                    return
            except Exception:
                return

            self.refresh_theme()

        try:
            window.after(0, refresh_if_window_alive)
        except Exception:
            self._refresh_theme_scheduled = False
            logger.debug("Unable to schedule deferred settings refresh", exc_info=True)

    def _restore_last_persisted_settings(self, fallback_settings: Optional[Dict[str, object]] = None) -> None:
        """Restore runtime settings to the last snapshot known to match the persisted file."""
        restore_last_persisted = getattr(self.settings, "restore_last_persisted_settings", None)
        if callable(restore_last_persisted):
            restore_last_persisted()
            return

        persisted_settings = None
        get_persisted_settings = getattr(self.settings, "get_persisted_settings", None)
        if callable(get_persisted_settings):
            persisted_settings = copy.deepcopy(get_persisted_settings())
        elif fallback_settings is not None:
            persisted_settings = copy.deepcopy(fallback_settings)

        if persisted_settings is None:
            return

        if hasattr(self.settings, "update"):
            self.settings.update(persisted_settings)
            return

        for key, value in persisted_settings.items():
            self.settings.set(key, value)

    def _show_settings_error_dialog(self, title: str, heading: str, message: str) -> None:
        """Display a modal error dialog for settings persistence failures."""
        error_dialog = ctk.CTkToplevel(self.window)
        error_dialog.title(title)
        error_dialog.geometry("450x220")
        error_dialog.transient(self.window)
        error_dialog.grab_set()

        ctk.CTkLabel(
            error_dialog,
            text=heading,
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD),
            text_color=COLOR_DANGER,
        ).pack(pady=(SPACING_LG, SPACING_SM))

        ctk.CTkLabel(
            error_dialog,
            text=message,
            font=ctk.CTkFont(size=FONT_MD),
            wraplength=400,
            justify="left",
        ).pack(fill="both", expand=True, padx=SPACING_LG, pady=SPACING_SM)

        ctk.CTkButton(error_dialog, text="OK", command=error_dialog.destroy).pack(pady=SPACING_LG)

    def _collect_and_save(self, close: bool):
        """Collect settings from all tabs, validate, then save. Closes window only if close=True."""
        self._ensure_all_tabs_hydrated()

        # Collect from all tabs first, before touching in-memory state
        all_tab_settings = [tab.get_settings() for tab in self.tabs]
        apply_changes_current_state = self._tab_settings_change_current_state(all_tab_settings)

        # Validate BEFORE mutating in-memory state
        validation_issues = []
        for tab in self.tabs:
            validation_issues.extend(tab.validate())

        if validation_issues:
            error_msg = "Settings validation failed:\n\n"
            for issue in validation_issues:
                error_msg += f"• {issue}\n"
            error_msg += "\nPlease fix these issues before saving."

            error_dialog = ctk.CTkToplevel(self.window)
            error_dialog.title("Validation Error")
            error_dialog.geometry("450x300")
            error_dialog.transient(self.window)
            error_dialog.grab_set()

            ctk.CTkLabel(error_dialog, text="⚠ Invalid Settings",
                         font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD),
                         text_color="orange").pack(pady=(SPACING_LG, SPACING_SM))

            error_text = ctk.CTkTextbox(error_dialog, wrap="word", state="normal")
            error_text.pack(fill="both", expand=True, padx=SPACING_LG, pady=SPACING_SM)
            error_text.insert("1.0", error_msg)
            error_text.configure(state="disabled")

            ctk.CTkButton(error_dialog, text="OK", command=error_dialog.destroy).pack(pady=SPACING_LG)
            return

        previous_settings = None
        get_persisted_settings = getattr(self.settings, "get_persisted_settings", None)
        if callable(get_persisted_settings):
            previous_settings = copy.deepcopy(get_persisted_settings())
        elif hasattr(self.settings, "get_all"):
            previous_settings = copy.deepcopy(self.settings.get_all())

        # Validation passed — now mutate in-memory state and persist
        for tab_settings in all_tab_settings:
            for k, v in tab_settings.items():
                self.settings.set(k, v)

        if not self.settings.save_settings():
            if previous_settings is not None:
                self._restore_last_persisted_settings(previous_settings)
            logger.warning("Settings persistence failed during save/apply")
            self._show_settings_error_dialog(
                "Save Error",
                "❌ Settings Not Saved",
                "CriTTS could not persist your settings. Please try again and verify the configuration file is writable.",
            )
            return

        self._notify_settings_saved()

        if not close and apply_changes_current_state:
            self._schedule_refresh_theme()

        if close:
            self._teardown_tabs()
            self.window.destroy()

    def _on_save(self):
        """Save settings and close the window."""
        self._collect_and_save(close=True)

    def _on_apply(self):
        """Save settings without closing the window."""
        self._collect_and_save(close=False)

    def _on_cancel(self):
        if hasattr(self, "settings"):
            self._restore_last_persisted_settings()
        self._teardown_tabs()
        self.window.destroy()
    
    def _on_reset_to_defaults(self):
        """Reset all settings to their default values."""
        # Create confirmation dialog
        confirm_dialog = ctk.CTkToplevel(self.window)
        confirm_dialog.title("Reset to Defaults")
        confirm_dialog.geometry("400x180")
        confirm_dialog.transient(self.window)
        confirm_dialog.grab_set()
        
        # Center dialog
        confirm_dialog.update_idletasks()
        x = (confirm_dialog.winfo_screenwidth() // 2) - (400 // 2)
        y = (confirm_dialog.winfo_screenheight() // 2) - (180 // 2)
        confirm_dialog.geometry(f"+{x}+{y}")
        
        ctk.CTkLabel(
            confirm_dialog,
            text="Reset All Settings?",
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD)
        ).pack(pady=(20, 10))
        
        ctk.CTkLabel(
            confirm_dialog,
            text="This will reset all settings to their default values. This action cannot be undone.",
            font=ctk.CTkFont(size=FONT_SM),
            wraplength=350
        ).pack(pady=10)
        
        def do_reset():
            try:
                # Reset settings to defaults
                reset_succeeded = self.settings.reset_to_defaults()
                if reset_succeeded is False:
                    logger.warning("Settings persistence failed during reset to defaults")
                    self._show_settings_error_dialog(
                        "Reset Error",
                        "❌ Settings Not Reset",
                        "CriTTS could not persist the default settings. Please try again and verify the configuration file is writable.",
                    )
                    return

                self._notify_settings_saved()
                logger.info("Settings reset to defaults")
                confirm_dialog.destroy()
                # Invalidate any in-flight async work before destroying
                self._teardown_tabs()
                # Close settings window - parent will reload
                self.window.destroy()
            except Exception as e:
                logger.error(f"Error resetting settings: {e}")
                self._show_settings_error_dialog(
                    "Reset Error",
                    "❌ Settings Not Reset",
                    "CriTTS hit an unexpected error while resetting settings to defaults.",
                )
        
        buttons_frame = ctk.CTkFrame(confirm_dialog, fg_color="transparent")
        buttons_frame.pack(pady=20)
        
        ctk.CTkButton(
            buttons_frame,
            text="Reset",
            font=ctk.CTkFont(size=FONT_MD),
            command=do_reset,
            width=100,
            fg_color=COLOR_DANGER,
            hover_color=COLOR_DANGER_HOVER
        ).pack(side="left", padx=10)
        
        ctk.CTkButton(
            buttons_frame,
            text="Cancel",
            font=ctk.CTkFont(size=FONT_MD),
            command=confirm_dialog.destroy,
            width=100
        ).pack(side="left", padx=10)
