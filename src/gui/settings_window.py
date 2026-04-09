"""
Settings Window GUI Module - Fixed Layout
Modal settings dialog for voice, audio device, and appearance configuration.
"""
import copy
import logging
import customtkinter as ctk
from typing import Optional, Callable, List, Dict

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


def get_settings_tabview_style(mode: Optional[str] = None) -> Dict[str, object]:
    """Return the shared style used by the settings tab chrome."""
    surface_theme = get_settings_surface_theme(mode)
    return {
        "fg_color": surface_theme["pane_fg"],
        "corner_radius": surface_theme["shell_corner_radius"],
        "border_width": 1,
        "border_color": surface_theme["border_color"],
        "segmented_button_fg_color": surface_theme["section_fg"],
        "segmented_button_selected_color": surface_theme["tab_selected_color"],
        "segmented_button_selected_hover_color": surface_theme["tab_selected_hover"],
        "segmented_button_unselected_color": surface_theme["pane_fg"],
        "segmented_button_unselected_hover_color": surface_theme["tab_unselected_hover"],
        "text_color": surface_theme["tab_text_color"],
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
        """Create the settings window with fixed layout."""
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
            **get_settings_tabview_style(appearance_mode),
        )
        self.tabview.grid(row=1, column=0, padx=SPACING_LG, pady=SPACING_LG, sticky="nsew")
         
        # List of tab instances to easily call validate() and get_settings() later
        self.tabs = []

        # Voice Settings Tab
        voice_frame = self.tabview.add("Voice")
        voice_frame.configure(fg_color="transparent")
        self.voice_tab_obj = VoiceTab(voice_frame, self.settings, self.tts_engine, self.audio_router, self._on_change_placeholder, parent_window=self.window)
        self.tabs.append(self.voice_tab_obj)
         
        # Audio Output Tab
        audio_frame = self.tabview.add("Audio Output")
        audio_frame.configure(fg_color="transparent")
        self.audio_tab_obj = AudioOutputTab(audio_frame, self.settings, self.tts_engine, self.audio_router, self._on_change_placeholder)
        self.tabs.append(self.audio_tab_obj)
         
        # Appearance Tab
        appearance_frame = self.tabview.add("Appearance")
        appearance_frame.configure(fg_color="transparent")
        self.appearance_tab_obj = AppearanceTab(appearance_frame, self.settings, self.tts_engine, self.audio_router, self._on_change_placeholder)
        self.tabs.append(self.appearance_tab_obj)
 
        # Abbreviations Tab
        abbrev_frame = self.tabview.add("Abbreviations")
        abbrev_frame.configure(fg_color="transparent")
        self.abbreviations_tab_obj = AbbreviationsTab(abbrev_frame, self.settings, self.tts_engine, self.audio_router, self._on_change_placeholder)
        self.tabs.append(self.abbreviations_tab_obj)
 
        # Keybinds Tab
        keybinds_frame = self.tabview.add("Keybinds")
        keybinds_frame.configure(fg_color="transparent")
        self.keybinds_tab_obj = KeybindsTab(keybinds_frame, self.settings, self.tts_engine, self.audio_router, self._on_change_placeholder)
        self.tabs.append(self.keybinds_tab_obj)
 
        # Behavior Tab
        behavior_frame = self.tabview.add("Behavior")
        behavior_frame.configure(fg_color="transparent")
        self.behavior_tab_obj = BehaviorTab(behavior_frame, self.settings, self.tts_engine, self.audio_router, self._on_change_placeholder)
        self.tabs.append(self.behavior_tab_obj)
 
        # Soundboard Tab
        soundboard_frame = self.tabview.add("Soundboard")
        soundboard_frame.configure(fg_color="transparent")
        self.soundboard_tab_obj = SoundboardTab(soundboard_frame, self.settings, self.tts_engine, self.audio_router, self._on_change_placeholder)
        self.tabs.append(self.soundboard_tab_obj)
 
        # VRChat OSC Tab
        vrchat_frame = self.tabview.add("VRChat OSC")
        vrchat_frame.configure(fg_color="transparent")
        self.vrchat_osc_tab_obj = VRChatOSCTab(
            vrchat_frame,
            self.settings,
            self.tts_engine,
            self.audio_router,
            self._on_change_placeholder,
            parent_window=self.parent
        )
        self.tabs.append(self.vrchat_osc_tab_obj)
         
        # Advanced Tab
        advanced_frame = self.tabview.add("Advanced")
        advanced_frame.configure(fg_color="transparent")
        self.advanced_tab_obj = AdvancedTab(advanced_frame, self.settings, self.tts_engine, self.audio_router, self._on_change_placeholder)
        self.tabs.append(self.advanced_tab_obj)
         
        # TTS Provider Tab
        provider_frame = self.tabview.add("TTS Provider")
        provider_frame.configure(fg_color="transparent")
        self.provider_tab_obj = TTSProviderTab(provider_frame, self.settings, self.tts_engine, self.audio_router, self._on_change_placeholder)
        self.tabs.append(self.provider_tab_obj)

        # Wire up: when provider changes in TTS Provider tab, reload Voice tab options live
        self.provider_tab_obj.set_voice_tab_callback(self.voice_tab_obj.reload_for_provider)
        
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

    def _teardown_tabs(self) -> None:
        """Invalidate async callbacks on every tab before the settings window is destroyed."""
        for tab in getattr(self, "tabs", []):
            invalidate = getattr(tab, "invalidate_async_callbacks", None)
            if callable(invalidate):
                invalidate()

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

    def _schedule_refresh_theme(self) -> None:
        """Defer settings shell rebuilding until the current UI callback frame has finished."""
        window = getattr(self, "window", None)
        if window is None:
            return

        def refresh_if_window_alive() -> None:
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
        # Collect from all tabs first, before touching in-memory state
        all_tab_settings = [tab.get_settings() for tab in self.tabs]

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

        if not close:
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
