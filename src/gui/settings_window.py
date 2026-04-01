"""
Settings Window GUI Module - Fixed Layout
Modal settings dialog for voice, audio device, and appearance configuration.
"""
import logging
import customtkinter as ctk
import asyncio
import threading
from typing import Optional, Callable, List, Dict
import time
import re
import os
from tkinter import filedialog

try:
    from ..vrchat import VRChatOSCClient
except Exception:
    VRChatOSCClient = None

from .keybind_manager import KeybindManager
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
    WINDOW_SETTINGS_MIN_WIDTH, WINDOW_SETTINGS_MIN_HEIGHT
)

logger = logging.getLogger(__name__)


# Default preview text constant
DEFAULT_PREVIEW_TEXT = "Hello, this is a voice preview."


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
        
        self._voices: List[Dict] = []
        self._devices: List[Dict] = []
        
        # Voice preview state
        self._preview_playing = False
        self._preview_stop_event = threading.Event()
        self._filtered_voices: List[Dict] = []
        
        # Voice name mapping: friendly name -> short_name
        self._voice_name_to_short_name: Dict[str, str] = {}
        
        # Keybind manager for validation
        self._keybind_manager = KeybindManager()
        
        # Alt key tracking for keybind capture (Windows fix)
        self._capture_alt_held = False
        
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
        
        # Configure grid
        self.window.grid_columnconfigure(0, weight=1)
        self.window.grid_rowconfigure(0, weight=1)  # Content expands
        self.window.grid_rowconfigure(1, weight=0)  # Buttons fixed
        
        # Main container with standardized padding
        self.main_frame = ctk.CTkFrame(self.window)
        self.main_frame.grid(row=0, column=0, padx=0, pady=0, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=1)  # Tabview expands
        
        # Title with theme font
        self.title_label = ctk.CTkLabel(
            self.main_frame,
            text="Settings",
            font=ctk.CTkFont(size=FONT_XL, weight=FONT_WEIGHT_BOLD)
        )
        self.title_label.grid(row=0, column=0, padx=SPACING_MD, pady=(SPACING_MD, SPACING_LG), sticky="w")
        
        # Initialize wraplength tracking list for dynamic resize
        self._wraplength_labels = []
        
        # Create tabbed interface with consistent padding
        self.tabview = ctk.CTkTabview(self.main_frame)
        self.tabview.grid(row=1, column=0, padx=SPACING_LG, pady=SPACING_LG, sticky="nsew")
        
        # List of tab instances to easily call validate() and get_settings() later
        self.tabs = []

        # Voice Settings Tab
        voice_frame = self.tabview.add("Voice")
        self.voice_tab_obj = VoiceTab(voice_frame, self.settings, self.tts_engine, self.audio_router, self._on_change_placeholder, parent_window=self.window)
        self.tabs.append(self.voice_tab_obj)
        
        # Audio Output Tab
        audio_frame = self.tabview.add("Audio Output")
        self.audio_tab_obj = AudioOutputTab(audio_frame, self.settings, self.tts_engine, self.audio_router, self._on_change_placeholder)
        self.tabs.append(self.audio_tab_obj)
        
        # Appearance Tab
        appearance_frame = self.tabview.add("Appearance")
        self.appearance_tab_obj = AppearanceTab(appearance_frame, self.settings, self.tts_engine, self.audio_router, self._on_change_placeholder)
        self.tabs.append(self.appearance_tab_obj)

        # Abbreviations Tab
        abbrev_frame = self.tabview.add("Abbreviations")
        self.abbreviations_tab_obj = AbbreviationsTab(abbrev_frame, self.settings, self.tts_engine, self.audio_router, self._on_change_placeholder)
        self.tabs.append(self.abbreviations_tab_obj)

        # Keybinds Tab
        keybinds_frame = self.tabview.add("Keybinds")
        self.keybinds_tab_obj = KeybindsTab(keybinds_frame, self.settings, self.tts_engine, self.audio_router, self._on_change_placeholder)
        self.tabs.append(self.keybinds_tab_obj)

        # Behavior Tab
        behavior_frame = self.tabview.add("Behavior")
        self.behavior_tab_obj = BehaviorTab(behavior_frame, self.settings, self.tts_engine, self.audio_router, self._on_change_placeholder)
        self.tabs.append(self.behavior_tab_obj)

        # Soundboard Tab
        soundboard_frame = self.tabview.add("Soundboard")
        self.soundboard_tab_obj = SoundboardTab(soundboard_frame, self.settings, self.tts_engine, self.audio_router, self._on_change_placeholder)
        self.tabs.append(self.soundboard_tab_obj)

        # VRChat OSC Tab
        vrchat_frame = self.tabview.add("VRChat OSC")
        self.vrchat_osc_tab_obj = VRChatOSCTab(vrchat_frame, self.settings, self.tts_engine, self.audio_router, self._on_change_placeholder)
        self.tabs.append(self.vrchat_osc_tab_obj)
        
        # Advanced Tab
        advanced_frame = self.tabview.add("Advanced")
        self.advanced_tab_obj = AdvancedTab(advanced_frame, self.settings, self.tts_engine, self.audio_router, self._on_change_placeholder)
        self.tabs.append(self.advanced_tab_obj)
        
        # TTS Provider Tab
        provider_frame = self.tabview.add("TTS Provider")
        self.provider_tab_obj = TTSProviderTab(provider_frame, self.settings, self.tts_engine, self.audio_router, self._on_change_placeholder)
        self.tabs.append(self.provider_tab_obj)

        # Wire up: when provider changes in TTS Provider tab, update Voice tab sliders live
        self.provider_tab_obj.set_voice_tab_callback(self.voice_tab_obj.update_provider_sliders)
        
        # Buttons frame - fixed at bottom with standardized padding
        self.buttons_frame = ctk.CTkFrame(self.window, fg_color="transparent")
        self.buttons_frame.grid(row=1, column=0, padx=0, pady=(SPACING_SM, SPACING_SM), sticky="ew")
        
        # Save button with theme colors
        self.save_button = ctk.CTkButton(
            self.buttons_frame,
            text="Save",
            font=ctk.CTkFont(size=FONT_MD, weight=FONT_WEIGHT_BOLD),
            command=self._on_save,
            fg_color=COLOR_SUCCESS,
            hover_color=COLOR_SUCCESS_HOVER,
            width=BUTTON_WIDTH_DEFAULT,
            height=BUTTON_HEIGHT
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
            height=BUTTON_HEIGHT
        )
        self.apply_button.pack(side="right", padx=SPACING_SM, pady=SPACING_SM)

        # Cancel button
        self.cancel_button = ctk.CTkButton(
            self.buttons_frame,
            text="Cancel",
            font=ctk.CTkFont(size=FONT_MD),
            command=self._on_cancel,
            width=BUTTON_WIDTH_DEFAULT,
            height=BUTTON_HEIGHT
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
            height=BUTTON_HEIGHT
        )
        self.reset_button.pack(side="left", padx=SPACING_SM, pady=SPACING_SM)
        
        # Refresh button
        self.refresh_button = ctk.CTkButton(
            self.buttons_frame,
            text="Refresh",
            font=ctk.CTkFont(size=FONT_MD),
            command=self._on_refresh,
            width=BUTTON_WIDTH_DEFAULT,
            height=BUTTON_HEIGHT
        )
        self.refresh_button.pack(side="left", padx=SPACING_SM, pady=SPACING_SM)
        
        # Bind X-button to cancel handler so it doesn't leak dirty in-memory state
        self.window.protocol("WM_DELETE_WINDOW", self._on_cancel)


    def _on_refresh(self):
        """Reload data for all tabs."""
        for tab in self.tabs:
            if hasattr(tab, '_load_data') and callable(tab._load_data):
                tab._load_data()

    def _on_change_placeholder(self, *args, **kwargs):
        pass

    def _collect_and_save(self, close: bool):
        """Collect settings from all tabs, validate, then save. Closes window only if close=True."""
        # Collect from all tabs first, before touching in-memory state
        all_tab_settings = [tab.get_settings() for tab in self.tabs]

        # Validate BEFORE mutating in-memory state
        validation_issues = []
        for tab in self.tabs:
            validation_issues.extend(tab.validate())

        system_issues = self.settings.validate_settings()
        if system_issues:
            validation_issues.extend(system_issues)

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

        # Validation passed — now mutate in-memory state and persist
        for tab_settings in all_tab_settings:
            for k, v in tab_settings.items():
                self.settings.set(k, v)

        self.settings.save_settings()
        if self.on_save:
            self.on_save()

        if close:
            self.window.destroy()

    def _on_save(self):
        """Save settings and close the window."""
        self._collect_and_save(close=True)

    def _on_apply(self):
        """Save settings without closing the window."""
        self._collect_and_save(close=False)

    def _on_cancel(self):
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
                self.settings.reset_to_defaults()
                logger.info("Settings reset to defaults")
                confirm_dialog.destroy()
                # Close settings window - parent will reload
                self.window.destroy()
            except Exception as e:
                logger.error(f"Error resetting settings: {e}")
        
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
