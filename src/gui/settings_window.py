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
        
        self._create_window()
        self._load_data()

    
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
        
        # Voice Settings Tab
        self.voice_tab = self.tabview.add("Voice")
        self._create_voice_tab()
        
        # Audio Output Tab
        self.audio_tab = self.tabview.add("Audio Output")
        self._create_audio_tab()
        
        # Appearance Tab
        self.appearance_tab = self.tabview.add("Appearance")
        self._create_appearance_tab()

        # Abbreviations Tab
        self.abbreviations_tab = self.tabview.add("Abbreviations")
        self._create_abbreviations_tab()

        # Keybinds Tab
        self.keybinds_tab = self.tabview.add("Keybinds")
        self._create_keybinds_tab()

        # Behavior Tab
        self.behavior_tab = self.tabview.add("Behavior")
        self._create_behavior_tab()

        # VRChat OSC Tab
        self.vrchat_osc_tab = self.tabview.add("VRChat OSC")
        self._create_vrchat_osc_tab()
        
        # Advanced Tab
        self.advanced_tab = self.tabview.add("Advanced")
        self._create_advanced_tab()
        
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
        
        # Bind resize handler for dynamic wraplength
        self.window.bind("<Configure>", self._on_settings_resize)
    
    def _create_voice_tab(self):
        """Create voice settings tab content with scrollable frame."""
        # Create scrollable frame for voice tab
        self.voice_scroll = ctk.CTkScrollableFrame(self.voice_tab)
        self.voice_scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Filters frame
        self.filters_frame = ctk.CTkFrame(self.voice_scroll, fg_color="transparent")
        self.filters_frame.pack(fill="x", pady=5)
        
        # Language filter
        self.language_filter_var = ctk.StringVar(value=self.settings.get("voice_filter_language", "All"))
        self.language_filter = ctk.CTkComboBox(
            self.filters_frame,
            variable=self.language_filter_var,
            values=["All Languages"],
            font=ctk.CTkFont(size=11),
            dropdown_font=ctk.CTkFont(size=10),
            width=150,
            state="readonly"
        )
        self.language_filter.pack(side="left", padx=5)
        self.language_filter.configure(command=lambda _: self._apply_voice_filters())
        
        # Gender filter
        self.gender_filter_var = ctk.StringVar(value=self.settings.get("voice_filter_gender", "All"))
        self.gender_filter = ctk.CTkComboBox(
            self.filters_frame,
            variable=self.gender_filter_var,
            values=["All", "Male", "Female"],
            font=ctk.CTkFont(size=11),
            dropdown_font=ctk.CTkFont(size=10),
            width=150,
            state="readonly"
        )
        self.gender_filter.pack(side="left", padx=5)
        self.gender_filter.configure(command=lambda _: self._apply_voice_filters())
        
        # Region filter
        self.region_filter_var = ctk.StringVar(value=self.settings.get("voice_filter_region", "All"))
        self.region_filter = ctk.CTkComboBox(
            self.filters_frame,
            variable=self.region_filter_var,
            values=["All Regions"],
            font=ctk.CTkFont(size=11),
            dropdown_font=ctk.CTkFont(size=10),
            width=150,
            state="readonly"
        )
        self.region_filter.pack(side="left", padx=5)
        self.region_filter.configure(command=lambda _: self._apply_voice_filters())
        
        # Clear filters button
        self.clear_filters_button = ctk.CTkButton(
            self.filters_frame,
            text="Clear Filters",
            font=ctk.CTkFont(size=10),
            width=150,
            state="readonly",
            command=self._clear_filters,
        )
        self.clear_filters_button.pack(side="left", padx=10)
        
        # Search field
        self.search_label = ctk.CTkLabel(
            self.voice_scroll,
            text="Search Voices:",
            font=ctk.CTkFont(size=12)
        )
        self.search_label.pack(anchor="w", pady=(10, 5))
        
        self.search_entry = ctk.CTkEntry(
            self.voice_scroll,
            font=ctk.CTkFont(size=12),
            placeholder_text="Type to filter voices..."
        )
        self.search_entry.pack(fill="x", pady=5)
        self.search_entry.bind("<KeyRelease>", self._on_voice_search)
        
        # Voice count label
        self.voice_count_label = ctk.CTkLabel(
            self.voice_scroll,
            text="Loading voices...",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.voice_count_label.pack(anchor="w", pady=(5, 10))
        
        # Separator
        ctk.CTkFrame(self.voice_scroll, height=2, fg_color="gray").pack(fill="x", pady=5)
        self.search_entry.bind("<KeyRelease>", self._on_voice_search)
        
        # Voice selection with controls
        self.voice_selection_frame = ctk.CTkFrame(self.voice_scroll, fg_color="transparent")
        self.voice_selection_frame.pack(fill="x", pady=5)
        
        self.voice_label = ctk.CTkLabel(
            self.voice_selection_frame,
            text="Selected Voice:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.voice_label.pack(side="left", padx=5)
        
        # Separator
        ctk.CTkFrame(self.voice_scroll, height=2, fg_color="gray").pack(fill="x", pady=10)
        
        # Voice dropdown
        self.voice_var = ctk.StringVar()
        self.voice_dropdown = ctk.CTkComboBox(
            self.voice_selection_frame,
            variable=self.voice_var,
            values=["Loading voices..."],
            font=ctk.CTkFont(size=12),
            dropdown_font=ctk.CTkFont(size=11),
            width=400,
            state="readonly"
        )
        self.voice_dropdown.pack(side="left", fill="x", expand=True, padx=5)
        self.voice_dropdown.configure(command=self._on_voice_selection_change)
        
        # Favorite button
        self.favorite_button = ctk.CTkButton(
            self.voice_selection_frame,
            text="☆",
            font=ctk.CTkFont(size=16),
            command=self._toggle_favorite_voice,
            width=40,
            height=32
        )
        self.favorite_button.pack(side="left", padx=5)
        self._update_favorite_button()
        
        # Preview controls frame
        self.preview_frame = ctk.CTkFrame(self.voice_scroll, fg_color="transparent")
        self.preview_frame.pack(fill="x", pady=10)
        
        # Preview text entry - validate loaded setting for corruption
        preview_text_value = self.settings.get("voice_preview_text", DEFAULT_PREVIEW_TEXT)
        if not self._validate_preview_text(preview_text_value):
            logger.warning("Preview text setting appears corrupted, resetting to default: '%s'", preview_text_value)
            preview_text_value = DEFAULT_PREVIEW_TEXT
            self.settings.set("voice_preview_text", DEFAULT_PREVIEW_TEXT)
        self.preview_text_var = ctk.StringVar(value=preview_text_value)
        self.preview_text_entry = ctk.CTkEntry(
            self.preview_frame,
            textvariable=self.preview_text_var,
            font=ctk.CTkFont(size=12),
            placeholder_text="Enter preview text..."
        )
        self.preview_text_entry.pack(side="left", fill="x", expand=True, padx=5)
        
        # Reset preview text button
        self.reset_preview_button = ctk.CTkButton(
            self.preview_frame,
            text="↻",
            font=ctk.CTkFont(size=14),
            command=self._reset_preview_text,
            width=32,
            height=32,
            fg_color="transparent",
            hover_color=("gray75", "gray25")
        )
        self.reset_preview_button.pack(side="left", padx=2)
        
        # Preview button
        self.preview_button = ctk.CTkButton(
            self.preview_frame,
            text="▶ Preview",
            font=ctk.CTkFont(size=12),
            command=self._on_voice_preview,
            width=100,
            height=32,
            fg_color="#2ecc71",
            hover_color="#27ae60"
        )
        self.preview_button.pack(side="left", padx=5)
        
        # Stop preview button (initially hidden)
        self.stop_preview_button = ctk.CTkButton(
            self.preview_frame,
            text="⏹ Stop",
            font=ctk.CTkFont(size=12),
            command=self._stop_voice_preview,
            width=100,
            height=32,
            fg_color="#e74c3c",
            hover_color="#c0392b"
        )
        
        # Loading indicator
        self.preview_loading_label = ctk.CTkLabel(
            self.preview_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.preview_loading_label.pack(side="left", padx=10)
        
        # Voice Information Panel
        self.voice_info_frame = ctk.CTkFrame(self.voice_scroll, fg_color=("gray90", "gray20"))
        self.voice_info_frame.pack(fill="x", pady=15, padx=5)
        
        self.voice_info_title = ctk.CTkLabel(
            self.voice_info_frame,
            text="Selected Voice Information",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.voice_info_title.pack(anchor="w", padx=10, pady=(10, 5))
        
        # Voice info grid
        self.voice_info_grid = ctk.CTkFrame(self.voice_info_frame, fg_color="transparent")
        self.voice_info_grid.pack(fill="x", padx=10, pady=5)
        
        # Name
        self.voice_info_name_label = ctk.CTkLabel(
            self.voice_info_grid,
            text="Name:",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=80,
            anchor="w"
        )
        self.voice_info_name_label.grid(row=0, column=0, sticky="w", pady=2)
        
        self.voice_info_name_value = ctk.CTkLabel(
            self.voice_info_grid,
            text="-",
            font=ctk.CTkFont(size=11),
            anchor="w"
        )
        self.voice_info_name_value.grid(row=0, column=1, sticky="w", pady=2, padx=5)
        
        # Gender
        self.voice_info_gender_label = ctk.CTkLabel(
            self.voice_info_grid,
            text="Gender:",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=80,
            anchor="w"
        )
        self.voice_info_gender_label.grid(row=1, column=0, sticky="w", pady=2)
        
        self.voice_info_gender_value = ctk.CTkLabel(
            self.voice_info_grid,
            text="-",
            font=ctk.CTkFont(size=11),
            anchor="w"
        )
        self.voice_info_gender_value.grid(row=1, column=1, sticky="w", pady=2, padx=5)
        
        # Locale
        self.voice_info_locale_label = ctk.CTkLabel(
            self.voice_info_grid,
            text="Locale:",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=80,
            anchor="w"
        )
        self.voice_info_locale_label.grid(row=2, column=0, sticky="w", pady=2)
        
        self.voice_info_locale_value = ctk.CTkLabel(
            self.voice_info_grid,
            text="-",
            font=ctk.CTkFont(size=11),
            anchor="w"
        )
        self.voice_info_locale_value.grid(row=2, column=1, sticky="w", pady=2, padx=5)
        
        # Short Name
        self.voice_info_short_label = ctk.CTkLabel(
            self.voice_info_grid,
            text="Short Name:",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=80,
            anchor="w"
        )
        self.voice_info_short_label.grid(row=3, column=0, sticky="w", pady=2)
        
        self.voice_info_short_value = ctk.CTkLabel(
            self.voice_info_grid,
            text="-",
            font=ctk.CTkFont(size=11),
            anchor="w"
        )
        self.voice_info_short_value.grid(row=3, column=1, sticky="w", pady=2, padx=5)
        
        # Separator
        ctk.CTkFrame(self.voice_scroll, height=2, fg_color="gray").pack(fill="x", pady=10)
        
        # Favorites Section
        self.favorites_label = ctk.CTkLabel(
            self.voice_scroll,
            text="★ Favorite Voices",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.favorites_label.pack(anchor="w", pady=(10, 5))
        
        self.favorites_frame = ctk.CTkScrollableFrame(self.voice_scroll, height=100)
        self.favorites_frame.pack(fill="x", pady=5)
        
        self.favorites_empty_label = ctk.CTkLabel(
            self.favorites_frame,
            text="No favorite voices yet. Click the star button to add favorites!",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.favorites_empty_label.pack(pady=20)
        
        # Recent Voices Section
        self.recent_label = ctk.CTkLabel(
            self.voice_scroll,
            text="• Recent Voices",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.recent_label.pack(anchor="w", pady=(15, 5))
        
        self.recent_frame = ctk.CTkScrollableFrame(self.voice_scroll, height=80)
        self.recent_frame.pack(fill="x", pady=5)
        
        self.recent_empty_label = ctk.CTkLabel(
            self.recent_frame,
            text="No recent voices yet.",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.recent_empty_label.pack(pady=20)
        
        # Separator
        ctk.CTkFrame(self.voice_scroll, height=2, fg_color="gray").pack(fill="x", pady=15)

        
        # Rate slider
        self.rate_label = ctk.CTkLabel(
            self.voice_scroll,
            text="Speech Rate (Speed):",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.rate_label.pack(anchor="w", pady=(10, 5))
        
        self.rate_frame = ctk.CTkFrame(self.voice_scroll, fg_color="transparent")
        self.rate_frame.pack(fill="x", pady=5)
        
        self.rate_var = ctk.IntVar(value=self.settings.get("rate", 0))
        self.rate_slider = ctk.CTkSlider(
            self.rate_frame,
            from_=-100,
            to=100,
            number_of_steps=200,
            variable=self.rate_var,
            command=self._on_rate_change,
            width=400
        )
        self.rate_slider.pack(side="left", fill="x", expand=True, padx=5)
        
        self.rate_value_label = ctk.CTkLabel(
            self.rate_frame,
            text=f"{self.rate_var.get()}%",
            font=ctk.CTkFont(size=12),
            width=50
        )
        self.rate_value_label.pack(side="right", padx=5)
        
        # Volume slider
        self.volume_label = ctk.CTkLabel(
            self.voice_scroll,
            text="Volume:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.volume_label.pack(anchor="w", pady=(10, 5))
        
        self.volume_frame = ctk.CTkFrame(self.voice_scroll, fg_color="transparent")
        self.volume_frame.pack(fill="x", pady=5)
        
        self.volume_var = ctk.IntVar(value=self.settings.get("volume", 100))
        self.volume_slider = ctk.CTkSlider(
            self.volume_frame,
            from_=0,
            to=100,
            number_of_steps=100,
            variable=self.volume_var,
            command=self._on_volume_change,
            width=400
        )
        self.volume_slider.pack(side="left", fill="x", expand=True, padx=5)
        
        self.volume_value_label = ctk.CTkLabel(
            self.volume_frame,
            text=f"{self.volume_var.get()}%",
            font=ctk.CTkFont(size=12),
            width=50
        )
        self.volume_value_label.pack(side="right", padx=5)
        
        # Pitch slider
        self.pitch_label = ctk.CTkLabel(
            self.voice_scroll,
            text="Pitch:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.pitch_label.pack(anchor="w", pady=(10, 5))
        
        self.pitch_frame = ctk.CTkFrame(self.voice_scroll, fg_color="transparent")
        self.pitch_frame.pack(fill="x", pady=5)
        
        self.pitch_var = ctk.IntVar(value=self.settings.get("pitch", 0))
        self.pitch_slider = ctk.CTkSlider(
            self.pitch_frame,
            from_=-100,
            to=100,
            number_of_steps=200,
            variable=self.pitch_var,
            command=self._on_pitch_change,
            width=400
        )
        self.pitch_slider.pack(side="left", fill="x", expand=True, padx=5)
        
        self.pitch_value_label = ctk.CTkLabel(
            self.pitch_frame,
            text=f"{self.pitch_var.get()}%",
            font=ctk.CTkFont(size=12),
            width=50
        )
        self.pitch_value_label.pack(side="right", padx=5)
        
        # Bind keyboard shortcut for preview (Ctrl+P)
        self.window.bind("<Control-p>", lambda e: self._on_voice_preview())

    
    def _create_audio_tab(self):
        """Create audio output settings tab content."""
        # Create scrollable frame
        self.audio_scroll = ctk.CTkScrollableFrame(self.audio_tab)
        self.audio_scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Device selection
        self.device_label = ctk.CTkLabel(
            self.audio_scroll,
            text="Output Device:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.device_label.pack(anchor="w", pady=(10, 5))
        
        self.device_info_label = ctk.CTkLabel(
            self.audio_scroll,
            text="Only VB-Cable virtual audio devices are shown. TTS audio must pass through VB-Cable to appear as a microphone in VRChat/Discord.",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.device_info_label.pack(anchor="w", pady=(0, 5))
        
        # Device dropdown
        self.device_var = ctk.StringVar()
        self.device_dropdown = ctk.CTkComboBox(
            self.audio_scroll,
            variable=self.device_var,
            values=["Loading devices..."],
            font=ctk.CTkFont(size=12),
            dropdown_font=ctk.CTkFont(size=11),
            width=500,
            state="readonly"
        )
        self.device_dropdown.pack(fill="x", pady=5)
        self.device_dropdown.configure(command=lambda _: self._update_device_info())
        
        # VB-Cable warning label (shown when no VB-Cable device is found)
        self.vbcable_warning_label = ctk.CTkLabel(
            self.audio_scroll,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="orange",
            wraplength=550
        )
        self.vbcable_warning_label.pack(anchor="w", pady=(5, 0))
        self._wraplength_labels.append(self.vbcable_warning_label)
        
        # Refresh devices button
        self.refresh_devices_button = ctk.CTkButton(
            self.audio_scroll,
            text="Refresh Device List",
            font=ctk.CTkFont(size=12),
            command=self._load_devices,
            height=35
        )
        self.refresh_devices_button.pack(anchor="w", pady=15)
        
        # Separator
        ctk.CTkFrame(self.audio_scroll, height=2, fg_color="gray").pack(fill="x", pady=10)
        
        # Device info
        self.device_details_label = ctk.CTkLabel(
            self.audio_scroll,
            text="Device Information",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.device_details_label.pack(anchor="w", pady=(10, 5))
        
        self.device_info_text = ctk.CTkTextbox(
            self.audio_scroll,
            font=ctk.CTkFont(size=11),
            height=150,
            wrap="word",
            state="disabled"
        )
        self.device_info_text.pack(fill="x", pady=5)
        
        # Separator
        ctk.CTkFrame(self.audio_scroll, height=2, fg_color="gray").pack(fill="x", pady=15)
        
        # Audio Normalization Section
        self.normalization_label = ctk.CTkLabel(
            self.audio_scroll,
            text="Audio Normalization",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.normalization_label.pack(anchor="w", pady=(10, 5))
        
        self.normalization_info = ctk.CTkLabel(
            self.audio_scroll,
            text="Normalization helps maintain consistent audio levels and prevents clipping.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            wraplength=550
        )
        self.normalization_info.pack(anchor="w", pady=(0, 10))
        self._wraplength_labels.append(self.normalization_info)
        
        # Normalization type
        self.norm_type_label = ctk.CTkLabel(
            self.audio_scroll,
            text="Normalization Type:",
            font=ctk.CTkFont(size=12)
        )
        self.norm_type_label.pack(anchor="w", pady=(5, 5))
        
        self.norm_var = ctk.StringVar(value=self.settings.get("normalization_type", "Peak"))
        self.norm_dropdown = ctk.CTkComboBox(
            self.audio_scroll,
            variable=self.norm_var,
            values=["Peak", "RMS", "LUFS", "None"],
            font=ctk.CTkFont(size=12),
            state="readonly",
            width=200
        )
        self.norm_dropdown.pack(anchor="w", pady=5)
        
        self.norm_desc_label = ctk.CTkLabel(
            self.audio_scroll,
            text="Peak: Prevents clipping | RMS: Consistent loudness | LUFS: Professional standard | None: No processing",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        self.norm_desc_label.pack(anchor="w", pady=(0, 10))
        
        # Enable normalization checkbox
        self.enable_norm_var = ctk.BooleanVar(value=self.settings.get("enable_normalization", True))
        self.enable_norm_check = ctk.CTkCheckBox(
            self.audio_scroll,
            text="Enable audio normalization",
            variable=self.enable_norm_var,
            font=ctk.CTkFont(size=12)
        )
        self.enable_norm_check.pack(anchor="w", pady=5)
    
    def _create_appearance_tab(self):
        """Create appearance settings tab content."""
        # Create scrollable frame
        self.appearance_scroll = ctk.CTkScrollableFrame(self.appearance_tab)
        self.appearance_scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Appearance mode
        self.appearance_label = ctk.CTkLabel(
            self.appearance_scroll,
            text="Appearance Mode:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.appearance_label.pack(anchor="w", pady=(10, 5))
        
        self.appearance_var = ctk.StringVar(value=self.settings.get("appearance_mode", "Dark"))
        self.appearance_dropdown = ctk.CTkComboBox(
            self.appearance_scroll,
            variable=self.appearance_var,
            values=["Dark", "Light", "System"],
            font=ctk.CTkFont(size=12),
            state="readonly",
            width=200
        )
        self.appearance_dropdown.pack(anchor="w", pady=5)
        
        # Preview
        self.preview_label = ctk.CTkLabel(
            self.appearance_scroll,
            text="Preview will apply on save",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.preview_label.pack(anchor="w", pady=5)

    def _create_abbreviations_tab(self):
        """Create abbreviations tab content."""
        self.abbrev_scroll = ctk.CTkScrollableFrame(self.abbreviations_tab)
        self.abbrev_scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.abbrev_title_label = ctk.CTkLabel(
            self.abbrev_scroll,
            text="Abbreviations",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.abbrev_title_label.pack(anchor="w", pady=(10, 5))
        
        self.abbrev_info_label = ctk.CTkLabel(
            self.abbrev_scroll,
            text="Enter one abbreviation per line in format: key=expansion",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            wraplength=550
        )
        self.abbrev_info_label.pack(anchor="w", pady=(0, 10))
        self._wraplength_labels.append(self.abbrev_info_label)
        
        self.abbrev_example_label = ctk.CTkLabel(
            self.abbrev_scroll,
            text="Example: brb=be right back  |  omg=oh my god",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            wraplength=550
        )
        self.abbrev_example_label.pack(anchor="w", pady=(0, 5))
        self._wraplength_labels.append(self.abbrev_example_label)
        
        ctk.CTkFrame(self.abbrev_scroll, height=2, fg_color="gray").pack(fill="x", pady=15)
        
        self.abbrev_text = ctk.CTkTextbox(
            self.abbrev_scroll,
            wrap="word",
            font=ctk.CTkFont(size=12)
        )
        self.abbrev_text.pack(fill="both", expand=True, pady=5)
        
        abbrev_dict = self.settings.get("abbreviations", {})
        formatted_lines = [f"{k}={v}" for k, v in sorted(abbrev_dict.items())]
        self.abbrev_text.insert("1.0", "\n".join(formatted_lines))
        
        self.abbrev_validate_btn = ctk.CTkButton(
            self.abbrev_scroll,
            text="Validate Format",
            command=self._validate_abbreviations,
            width=140,
            height=32
        )
        self.abbrev_validate_btn.pack(anchor="w", pady=10)
        
        self.abbrev_status_label = ctk.CTkLabel(
            self.abbrev_scroll,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            wraplength=550
        )
        self.abbrev_status_label.pack(anchor="w", pady=5)
        self._wraplength_labels.append(self.abbrev_status_label)
        
        ctk.CTkFrame(self.abbrev_scroll, height=2, fg_color="gray").pack(fill="x", pady=15)
        
        self.abbrev_usage_label = ctk.CTkLabel(
            self.abbrev_scroll,
            text="Usage Tips",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.abbrev_usage_label.pack(anchor="w", pady=(10, 5))
        
        self.abbrev_usage_text = ctk.CTkTextbox(
            self.abbrev_scroll,
            font=ctk.CTkFont(size=11),
            height=180,
            wrap="word"
        )
        self.abbrev_usage_text.pack(fill="x", pady=5)
        self.abbrev_usage_text.insert("1.0", """Format: one abbreviation per line as key=expansion

Examples:
  brb=be right back
  omg=oh my god
  idk=I don't know

• Matching is case-insensitive in the main window.
• Use # at the start of a line for comments (e.g. # optional abbreviations).
• After saving, abbreviations are expanded when you speak in the main window.""")
        self.abbrev_usage_text.configure(state="disabled")
    
    def _create_behavior_tab(self):
        """Create Behavior tab content with speak mode and auto language detection options."""
        self.behavior_scroll = ctk.CTkScrollableFrame(self.behavior_tab)
        self.behavior_scroll.pack(fill="both", expand=True, padx=10, pady=10)
        ctk.CTkLabel(
            self.behavior_scroll,
            text="Behavior",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", pady=(10, 5))
        self.behavior_desc_label = ctk.CTkLabel(
            self.behavior_scroll,
            text="Choose which text is sent to TTS when you press Speak.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            wraplength=550
        )
        self.behavior_desc_label.pack(anchor="w", pady=(0, 10))
        self._wraplength_labels.append(self.behavior_desc_label)
        speak_mode = self.settings.get("speak_mode", "current_line")
        self.speak_mode_current_line_var = ctk.BooleanVar(value=(speak_mode == "current_line"))
        self.speak_mode_check = ctk.CTkCheckBox(
            self.behavior_scroll,
            text="Speak current line only (cursor line); when unchecked, speak all text",
            variable=self.speak_mode_current_line_var,
            font=ctk.CTkFont(size=12)
        )
        self.speak_mode_check.pack(anchor="w", pady=5)
        self.behavior_speak_mode_hint_label = ctk.CTkLabel(
            self.behavior_scroll,
            text="Current line: only the line where the cursor is will be spoken. All text: entire textbox.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            wraplength=550
        )
        self.behavior_speak_mode_hint_label.pack(anchor="w", pady=(5, 10))
        self._wraplength_labels.append(self.behavior_speak_mode_hint_label)
        
        # Auto language detection checkbox
        self.auto_language_var = ctk.BooleanVar(value=self.settings.get("auto_language_detection", False))
        self.auto_language_check = ctk.CTkCheckBox(
            self.behavior_scroll,
            text="Auto-select voice based on text language",
            variable=self.auto_language_var,
            font=ctk.CTkFont(size=12)
        )
        self.auto_language_check.pack(anchor="w", pady=5)
        self.behavior_auto_lang_desc_label = ctk.CTkLabel(
            self.behavior_scroll,
            text="When enabled, the system will automatically detect the language of your text and select the most appropriate voice.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            wraplength=550
        )
        self.behavior_auto_lang_desc_label.pack(anchor="w", pady=(0, 10))
        self._wraplength_labels.append(self.behavior_auto_lang_desc_label)
        
        # Language-specific voice mapping section
        self.language_mapping_label = ctk.CTkLabel(
            self.behavior_scroll,
            text="Language-Specific Voice Mapping:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.language_mapping_label.pack(anchor="w", pady=(10, 5))
        
        self.language_mapping_info = ctk.CTkLabel(
            self.behavior_scroll,
            text="Select custom voices for specific languages. Use 'Auto' to use the default detection.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            wraplength=550
        )
        self.language_mapping_info.pack(anchor="w", pady=(0, 10))
        
        # Language mapping frame
        self.language_mapping_frame = ctk.CTkScrollableFrame(self.behavior_scroll, height=200)
        self.language_mapping_frame.pack(fill="x", pady=5)
        
        # Note: Language mapping controls will be created after voices are loaded
        self.language_mapping_controls_created = False
    
    def _create_language_mapping_controls(self):
        """Create language-specific voice mapping controls."""
        # Create mapping entries for common languages
        common_languages = ["en", "es", "fr", "de", "it", "pt", "ru", "zh", "ja", "ko", "ar", "hi"]
        
        self.language_mapping_entries = {}
        
        for lang_code in common_languages:
            # Get all voices for this language
            lang_voices = self._get_voices_by_language(lang_code)
            if not lang_voices:
                continue
                
            lang_frame = ctk.CTkFrame(self.language_mapping_frame, fg_color="transparent")
            lang_frame.pack(fill="x", pady=5)
            
            # Language label
            lang_label = ctk.CTkLabel(
                lang_frame,
                text=self._get_language_name(lang_code),
                font=ctk.CTkFont(size=12, weight="bold"),
                width=120,
                anchor="w"
            )
            lang_label.pack(side="left", padx=5)
            
            # Voice selection dropdown - use friendly names with locale info
            voice_options = ["Auto (default detection)"]
            voice_options.extend([f"{v['name']} ({v['locale']}, {v['gender']})" for v in lang_voices])
            
            voice_var = ctk.StringVar()
            voice_dropdown = ctk.CTkComboBox(
                lang_frame,
                variable=voice_var,
                values=voice_options,
                font=ctk.CTkFont(size=11),
                width=400,
                state="readonly"
            )
            voice_dropdown.pack(side="left", fill="x", expand=True, padx=10)
            
            # Store reference for saving
            self.language_mapping_entries[lang_code] = {
                'var': voice_var,
                'dropdown': voice_dropdown,
                'voices': lang_voices
            }
        
        # Load current mappings
        self._load_language_mappings()
    
    def _get_available_languages(self):
        """Get list of available languages from loaded voices."""
        if not self._voices:
            return []
        
        languages = set()
        for voice in self._voices:
            locale = voice.get('locale', '')
            if locale and '-' in locale:
                lang = locale.split('-')[0]
                languages.add(lang)
        
        return sorted(list(languages))
    
    def _get_available_locales(self):
        """Get list of available locales from loaded voices."""
        if not self._voices:
            return []
        
        locales = set()
        for voice in self._voices:
            locale = voice.get('locale', '')
            if locale:
                locales.add(locale)
        
        return sorted(list(locales))
    
    def _get_language_name(self, lang_code):
        """Get display name for language code."""
        language_names = {
            'en': 'English',
            'es': 'Spanish',
            'fr': 'French',
            'de': 'German',
            'it': 'Italian',
            'pt': 'Portuguese',
            'ru': 'Russian',
            'zh': 'Chinese',
            'ja': 'Japanese',
            'ko': 'Korean',
            'ar': 'Arabic',
            'hi': 'Hindi'
        }
        return language_names.get(lang_code, lang_code.upper())
    
    def _get_voices_by_language(self, lang_code):
        """Get all voices for a specific language."""
        if not self._voices:
            return []
        
        lang_voices = []
        for voice in self._voices:
            locale = voice.get('locale', '')
            if locale and locale.startswith(lang_code + '-'):
                lang_voices.append(voice)
        
        return sorted(lang_voices, key=lambda v: v.get('name', ''))
    
    def _load_language_mappings(self):
        """Load current language voice mappings from settings."""
        language_mappings = self.settings.get("language_voice_mappings", {})
        
        for lang_code, controls in self.language_mapping_entries.items():
            current_mapping = language_mappings.get(lang_code, "Auto (default detection)")
            controls['var'].set(current_mapping)
    
    def _save_language_mappings(self):
        """Save language voice mappings to settings."""
        language_mappings = {}
        
        for lang_code, controls in self.language_mapping_entries.items():
            selected = controls['var'].get()
            if selected != "Auto (default detection)":
                language_mappings[lang_code] = selected
        
        self.settings.set("language_voice_mappings", language_mappings)

    def _create_keybinds_tab(self):
        """Create keybinds tab content with editable keybinds for each action."""
        self.keybinds_scroll = ctk.CTkScrollableFrame(self.keybinds_tab)
        self.keybinds_scroll.pack(fill="both", expand=True, padx=10, pady=10)
        ctk.CTkLabel(
            self.keybinds_scroll,
            text="Keybinds",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", pady=(10, 5))
        self.keybinds_info_label = ctk.CTkLabel(
            self.keybinds_scroll,
            text="Keybinds work application-wide regardless of focus. Click 'Set' to capture key combinations.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            wraplength=550
        )
        self.keybinds_info_label.pack(anchor="w", pady=(0, 5))
        self._wraplength_labels.append(self.keybinds_info_label)
        self.keybinds_warning_label = ctk.CTkLabel(
            self.keybinds_scroll,
            text="⚠️ Avoid system shortcuts (Alt+F4, Windows key). Leave empty to disable an action.",
            font=ctk.CTkFont(size=11),
            text_color="orange",
            wraplength=550
        )
        self.keybinds_warning_label.pack(anchor="w", pady=(0, 15))
        self._wraplength_labels.append(self.keybinds_warning_label)
        
        keybinds = self.settings.get("keybinds", {})
        defaults = {
            "stop": "Escape",
            "clear": "Ctrl+T",
            "open_settings": "Ctrl+Comma"
        }
        self.keybind_vars = {}
        self.keybind_validation_labels = {}  # Store validation labels for updates
        self.keybind_capture_buttons = {}  # Store capture buttons for state management
        self._capturing_keybind = None  # Track which action is being captured
        
        labels = {
            "stop": "Stop playback",
            "clear": "Clear text",
            "open_settings": "Open Settings"
        }
        
        # Add info label explaining that Speak is triggered by Enter
        self.keybinds_speak_info_label = ctk.CTkLabel(
            self.keybinds_scroll,
            text="💡 Speak is triggered by pressing Enter in the text box. The keybinds below control other actions.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            wraplength=550
        )
        self.keybinds_speak_info_label.pack(anchor="w", pady=(0, 10))
        self._wraplength_labels.append(self.keybinds_speak_info_label)
        
        for action in ("stop", "clear", "open_settings"):
            row = ctk.CTkFrame(self.keybinds_scroll, fg_color="transparent")
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(row, text=labels[action], font=ctk.CTkFont(size=12), width=160, anchor="w").pack(side="left", padx=(0, 10))
            var = ctk.StringVar(value=keybinds.get(action, defaults.get(action, "")))
            self.keybind_vars[action] = var
            entry = ctk.CTkEntry(row, textvariable=var, width=200, font=ctk.CTkFont(size=12))
            entry.pack(side="left", padx=5)
            
            # Capture button
            capture_btn = ctk.CTkButton(
                row,
                text="Set",
                font=ctk.CTkFont(size=11),
                command=lambda a=action: self._start_keybind_capture(a),
                width=60,
                height=28
            )
            capture_btn.pack(side="left", padx=5)
            self.keybind_capture_buttons[action] = capture_btn
            
            # Add validation indicator label
            validation_label = ctk.CTkLabel(
                row, 
                text="", 
                font=ctk.CTkFont(size=12),
                width=20
            )
            validation_label.pack(side="left", padx=5)
            self.keybind_validation_labels[action] = validation_label
            
            # Bind real-time validation
            entry.bind("<KeyRelease>", lambda e, a=action: self._validate_keybind_entry(a))
    
    def _create_vrchat_osc_tab(self):
        """Create VRChat OSC settings tab."""
        self.osc_scroll = ctk.CTkScrollableFrame(self.vrchat_osc_tab)
        self.osc_scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        # OSC Chatbox Section
        ctk.CTkLabel(self.osc_scroll, text="VRChat OSC Chatbox", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(10, 5))
        
        self.osc_enabled_var = ctk.BooleanVar(value=self.settings.get("vrchat_osc_enabled", False))
        self.osc_enabled_check = ctk.CTkCheckBox(
            self.osc_scroll, 
            text="Enable OSC (send to VRChat chatbox)", 
            variable=self.osc_enabled_var, 
            font=ctk.CTkFont(size=12),
            command=self._on_osc_enabled_toggle
        )
        self.osc_enabled_check.pack(anchor="w", pady=5)
        
        ctk.CTkLabel(self.osc_scroll, text="IP:", font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(10, 2))
        self.osc_ip_var = ctk.StringVar(value=self.settings.get("vrchat_osc_ip", "127.0.0.1"))
        self.osc_ip_entry = ctk.CTkEntry(self.osc_scroll, textvariable=self.osc_ip_var, width=200)
        self.osc_ip_entry.pack(anchor="w", pady=2)
        
        ctk.CTkLabel(self.osc_scroll, text="Port (default 9000):", font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(10, 2))
        self.osc_port_var = ctk.StringVar(value=str(self.settings.get("vrchat_osc_port", 9000)))
        self.osc_port_entry = ctk.CTkEntry(self.osc_scroll, textvariable=self.osc_port_var, width=120)
        self.osc_port_entry.pack(anchor="w", pady=2)
        
        self.osc_play_sound_var = ctk.BooleanVar(value=self.settings.get("vrchat_osc_play_sound", True))
        self.osc_play_sound_check = ctk.CTkCheckBox(
            self.osc_scroll, 
            text="Play notification sound when sending", 
            variable=self.osc_play_sound_var, 
            font=ctk.CTkFont(size=12)
        )
        self.osc_play_sound_check.pack(anchor="w", pady=5)
        
        osc_sound_info_label = ctk.CTkLabel(
            self.osc_scroll,
            text="Notification sound uses VRChat's built-in chatbox sound. Requires OSC to be enabled and may not work in all VRChat versions.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            wraplength=500
        )
        osc_sound_info_label.pack(anchor="w", pady=(0, 5))
        self._wraplength_labels.append(osc_sound_info_label)
        
        self.osc_send_on_speak_var = ctk.BooleanVar(value=self.settings.get("vrchat_osc_send_on_speak", False))
        self.osc_send_on_speak_check = ctk.CTkCheckBox(
            self.osc_scroll, 
            text="Send to chatbox when speaking (main window)", 
            variable=self.osc_send_on_speak_var, 
            font=ctk.CTkFont(size=12)
        )
        self.osc_send_on_speak_check.pack(anchor="w", pady=5)
        
        ctk.CTkButton(self.osc_scroll, text="Test connection", command=self._test_osc_connection, width=140, height=32).pack(anchor="w", pady=15)
        
        self.osc_status_label = ctk.CTkLabel(self.osc_scroll, text="", font=ctk.CTkFont(size=11), text_color="gray", wraplength=500)
        self.osc_status_label.pack(anchor="w", pady=5)
        
        # Separator
        ctk.CTkFrame(self.osc_scroll, height=2, fg_color="gray").pack(fill="x", pady=15)
        
        # ========== VRChat Viseme Lip-Sync Section ==========
        ctk.CTkLabel(
            self.osc_scroll, 
            text="VRChat Viseme Lip-Sync", 
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", pady=(10, 5))
        
        osc_viseme_info_label = ctk.CTkLabel(
            self.osc_scroll,
            text="Viseme mapping enables realistic lip-sync animation in VRChat via OSC. Requires OSC to be enabled.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            wraplength=500
        )
        osc_viseme_info_label.pack(anchor="w", pady=(0, 10))
        self._wraplength_labels.append(osc_viseme_info_label)
        
        # Enable viseme mapping checkbox
        self.viseme_enabled_var = ctk.BooleanVar(value=self.settings.get("vrchat_viseme_enabled", False))
        self.viseme_enabled_check = ctk.CTkCheckBox(
            self.osc_scroll,
            text="Enable Viseme Lip-Sync",
            variable=self.viseme_enabled_var,
            font=ctk.CTkFont(size=12)
        )
        self.viseme_enabled_check.pack(anchor="w", pady=5)
        
        osc_viseme_enabled_label = ctk.CTkLabel(
            self.osc_scroll,
            text="When enabled, sends viseme parameters to VRChat for lip-sync animation during TTS playback.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            wraplength=500
        )
        osc_viseme_enabled_label.pack(anchor="w", pady=(0, 10))
        self._wraplength_labels.append(osc_viseme_enabled_label)
        
        # Viseme smoothing slider
        ctk.CTkLabel(
            self.osc_scroll,
            text="Viseme Smoothing:",
            font=ctk.CTkFont(size=12)
        ).pack(anchor="w", pady=(10, 5))
        
        viseme_smoothing_frame = ctk.CTkFrame(self.osc_scroll, fg_color="transparent")
        viseme_smoothing_frame.pack(fill="x", pady=5)
        
        # Convert 0.0-1.0 smoothing to 0-100 for slider
        current_smoothing = int(self.settings.get("vrchat_viseme_smoothing", 0.1) * 100)
        self.viseme_smoothing_var = ctk.IntVar(value=current_smoothing)
        self.viseme_smoothing_slider = ctk.CTkSlider(
            viseme_smoothing_frame,
            from_=0,
            to=100,
            number_of_steps=100,
            variable=self.viseme_smoothing_var,
            command=self._on_viseme_smoothing_change,
            width=400
        )
        self.viseme_smoothing_slider.pack(side="left", fill="x", expand=True, padx=5)
        
        self.viseme_smoothing_value_label = ctk.CTkLabel(
            viseme_smoothing_frame,
            text=f"{current_smoothing}%",
            font=ctk.CTkFont(size=12),
            width=50
        )
        self.viseme_smoothing_value_label.pack(side="right", padx=5)
        
        ctk.CTkLabel(
            self.osc_scroll,
            text="Higher values create smoother transitions between mouth shapes.",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        ).pack(anchor="w", pady=(0, 10))
        
        # Voice amplitude checkbox
        self.viseme_amplitude_var = ctk.BooleanVar(value=self.settings.get("vrchat_voice_amplitude_enabled", False))
        self.viseme_amplitude_check = ctk.CTkCheckBox(
            self.osc_scroll,
            text="Use Voice Amplitude for Mouth Movement",
            variable=self.viseme_amplitude_var,
            font=ctk.CTkFont(size=12)
        )
        self.viseme_amplitude_check.pack(anchor="w", pady=5)
        
        osc_amplitude_label = ctk.CTkLabel(
            self.osc_scroll,
            text="When enabled, mouth opening intensity is based on actual audio amplitude.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            wraplength=500
        )
        osc_amplitude_label.pack(anchor="w", pady=(0, 10))
        self._wraplength_labels.append(osc_amplitude_label)
        
        # Store viseme-related widgets for enabling/disabling based on OSC state
        self._viseme_widgets = [
            self.viseme_enabled_check,
            self.viseme_smoothing_slider,
            self.viseme_amplitude_check,
        ]
        
        # Initialize OSC enabled state
        self._on_osc_enabled_toggle()
    
    def _on_osc_enabled_toggle(self):
        """Toggle viseme options based on OSC enabled state."""
        osc_enabled = self.osc_enabled_var.get()
        
        # Enable/disable viseme-related widgets based on OSC state
        for widget in self._viseme_widgets:
            try:
                widget.configure(state="normal" if osc_enabled else "disabled")
            except Exception:
                pass
        
        # If OSC is disabled, also disable viseme
        if not osc_enabled:
            self.viseme_enabled_var.set(False)
    
    def _create_advanced_tab(self):
        """Create Advanced settings tab with cache management, performance, and experimental features."""
        self.advanced_scroll = ctk.CTkScrollableFrame(self.advanced_tab)
        self.advanced_scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Main title
        ctk.CTkLabel(
            self.advanced_scroll,
            text="Advanced Settings",
            font=ctk.CTkFont(size=FONT_XL, weight=FONT_WEIGHT_BOLD)
        ).pack(anchor="w", pady=(10, 5))
        
        advanced_desc_label = ctk.CTkLabel(
            self.advanced_scroll,
            text="Configure cache, performance, and experimental features. Changes take effect after saving.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550
        )
        advanced_desc_label.pack(anchor="w", pady=(0, 15))
        self._wraplength_labels.append(advanced_desc_label)
        
        # ========== Cache Management Section ==========
        ctk.CTkLabel(
            self.advanced_scroll,
            text="Cache Management",
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD)
        ).pack(anchor="w", pady=(10, 5))
        
        cache_desc_label = ctk.CTkLabel(
            self.advanced_scroll,
            text="Audio cache stores generated speech to improve response times for repeated phrases.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550
        )
        cache_desc_label.pack(anchor="w", pady=(0, 10))
        self._wraplength_labels.append(cache_desc_label)
        
        # Cache statistics display
        self.cache_stats_text = ctk.CTkTextbox(
            self.advanced_scroll,
            font=ctk.CTkFont(size=FONT_SM),
            height=120,
            wrap="word",
            state="disabled"
        )
        self.cache_stats_text.pack(fill="x", pady=5)
        
        # Cache buttons frame
        cache_buttons_frame = ctk.CTkFrame(self.advanced_scroll, fg_color="transparent")
        cache_buttons_frame.pack(fill="x", pady=10)
        
        self.clear_cache_button = ctk.CTkButton(
            cache_buttons_frame,
            text="Clear Audio Cache",
            font=ctk.CTkFont(size=FONT_SM),
            command=self._on_clear_cache,
            width=140,
            height=BUTTON_HEIGHT_SM,
            fg_color=COLOR_DANGER,
            hover_color=COLOR_DANGER_HOVER
        )
        self.clear_cache_button.pack(side="left", padx=5)
        
        self.refresh_stats_button = ctk.CTkButton(
            cache_buttons_frame,
            text="Refresh Statistics",
            font=ctk.CTkFont(size=FONT_SM),
            command=self._on_refresh_cache_stats,
            width=140,
            height=BUTTON_HEIGHT_SM
        )
        self.refresh_stats_button.pack(side="left", padx=5)
        
        # Cache enabled checkbox
        self.cache_enabled_var = ctk.BooleanVar(value=self.settings.get("audio_cache_enabled", True))
        self.cache_enabled_check = ctk.CTkCheckBox(
            self.advanced_scroll,
            text="Enable audio cache",
            variable=self.cache_enabled_var,
            font=ctk.CTkFont(size=FONT_MD)
        )
        self.cache_enabled_check.pack(anchor="w", pady=5)
        
        # Max cache size slider
        ctk.CTkLabel(
            self.advanced_scroll,
            text="Maximum Cache Size:",
            font=ctk.CTkFont(size=FONT_MD)
        ).pack(anchor="w", pady=(10, 5))
        
        cache_size_frame = ctk.CTkFrame(self.advanced_scroll, fg_color="transparent")
        cache_size_frame.pack(fill="x", pady=5)
        
        self.cache_max_size_var = ctk.IntVar(value=self.settings.get("audio_cache_max_size_mb", 500))
        self.cache_size_slider = ctk.CTkSlider(
            cache_size_frame,
            from_=10,
            to=2000,
            number_of_steps=199,
            variable=self.cache_max_size_var,
            command=self._on_cache_size_change,
            width=400
        )
        self.cache_size_slider.pack(side="left", fill="x", expand=True, padx=5)
        
        self.cache_size_value_label = ctk.CTkLabel(
            cache_size_frame,
            text=f"{self.cache_max_size_var.get()} MB",
            font=ctk.CTkFont(size=FONT_MD),
            width=80
        )
        self.cache_size_value_label.pack(side="right", padx=5)
        
        # Separator
        ctk.CTkFrame(self.advanced_scroll, height=2, fg_color="gray").pack(fill="x", pady=15)
        
        # ========== Performance Settings Section ==========
        ctk.CTkLabel(
            self.advanced_scroll,
            text="Performance Settings",
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD)
        ).pack(anchor="w", pady=(10, 5))
        
        # Processing profile dropdown
        ctk.CTkLabel(
            self.advanced_scroll,
            text="Processing Profile:",
            font=ctk.CTkFont(size=FONT_MD)
        ).pack(anchor="w", pady=(10, 5))
        
        self.processing_profile_var = ctk.StringVar(value=self.settings.get("processing_profile", "balanced"))
        self.processing_profile_dropdown = ctk.CTkComboBox(
            self.advanced_scroll,
            variable=self.processing_profile_var,
            values=["fast_preview", "balanced", "high_quality"],
            font=ctk.CTkFont(size=FONT_SM),
            state="readonly",
            width=200
        )
        self.processing_profile_dropdown.pack(anchor="w", pady=5)
        
        ctk.CTkLabel(
            self.advanced_scroll,
            text="Fast Preview: No resampling, no normalization | Balanced: 48 kHz, Peak normalization | High Quality: 48 kHz, LUFS normalization",
            font=ctk.CTkFont(size=FONT_XS),
            text_color="gray"
        ).pack(anchor="w", pady=(0, 10))
        
        # Text cache size
        ctk.CTkLabel(
            self.advanced_scroll,
            text="Text Cache Size:",
            font=ctk.CTkFont(size=FONT_MD)
        ).pack(anchor="w", pady=(10, 5))
        
        text_cache_frame = ctk.CTkFrame(self.advanced_scroll, fg_color="transparent")
        text_cache_frame.pack(fill="x", pady=5)
        
        self.text_cache_size_var = ctk.StringVar(value=str(self.settings.get("text_cache_size", 1000)))
        self.text_cache_entry = ctk.CTkEntry(
            text_cache_frame,
            textvariable=self.text_cache_size_var,
            font=ctk.CTkFont(size=FONT_MD),
            width=100
        )
        self.text_cache_entry.pack(side="left", padx=5)
        
        ctk.CTkLabel(
            text_cache_frame,
            text="Number of processed text entries to cache (100-10000)",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray"
        ).pack(side="left", padx=5)
        
        # Separator
        ctk.CTkFrame(self.advanced_scroll, height=2, fg_color="gray").pack(fill="x", pady=15)
        
        # ========== Experimental Features Section ==========
        ctk.CTkLabel(
            self.advanced_scroll,
            text="Experimental Features",
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD)
        ).pack(anchor="w", pady=(10, 5))
        
        # Warning label
        experimental_warning_label = ctk.CTkLabel(
            self.advanced_scroll,
            text="⚠️ Experimental features may be unstable or change in future versions.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="orange",
            wraplength=550
        )
        experimental_warning_label.pack(anchor="w", pady=(0, 10))
        self._wraplength_labels.append(experimental_warning_label)
        
        # Streaming playback checkbox
        self.streaming_playback_var = ctk.BooleanVar(value=self.settings.get("enable_streaming", False))
        self.streaming_playback_check = ctk.CTkCheckBox(
            self.advanced_scroll,
            text="Enable Streaming Playback (Experimental)",
            variable=self.streaming_playback_var,
            font=ctk.CTkFont(size=FONT_MD)
        )
        self.streaming_playback_check.pack(anchor="w", pady=5)
        
        streaming_desc_label = ctk.CTkLabel(
            self.advanced_scroll,
            text="Starts playing audio as soon as the first chunks arrive from Edge TTS, reducing the delay before you hear speech. Best for longer text. Note: Audio normalization and viseme sync use estimated timing in streaming mode.",
            font=ctk.CTkFont(size=FONT_XS),
            text_color="gray",
            wraplength=550
        )
        streaming_desc_label.pack(anchor="w", pady=(0, 10))
        self._wraplength_labels.append(streaming_desc_label)
    
    def _on_clear_cache(self):
        """Clear the audio cache with user confirmation."""
        # Create confirmation dialog
        confirm_dialog = ctk.CTkToplevel(self.window)
        confirm_dialog.title("Confirm Clear Cache")
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
            text="Clear Audio Cache?",
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD)
        ).pack(pady=(20, 10))
        
        ctk.CTkLabel(
            confirm_dialog,
            text="This will delete all cached audio files. The cache will be rebuilt as you use TTS.",
            font=ctk.CTkFont(size=FONT_SM),
            wraplength=350
        ).pack(pady=10)
        
        def do_clear():
            try:
                if self.tts_engine and self.tts_engine.clear_audio_cache():
                    logger.info("Audio cache cleared successfully")
                    self._on_refresh_cache_stats()
                    confirm_dialog.destroy()
                else:
                    logger.warning("Failed to clear audio cache")
                    ctk.CTkLabel(
                        confirm_dialog,
                        text="Failed to clear cache. Check logs for details.",
                        font=ctk.CTkFont(size=FONT_SM),
                        text_color="red"
                    ).pack(pady=5)
            except Exception as e:
                logger.error(f"Error clearing cache: {e}")
        
        buttons_frame = ctk.CTkFrame(confirm_dialog, fg_color="transparent")
        buttons_frame.pack(pady=20)
        
        ctk.CTkButton(
            buttons_frame,
            text="Clear Cache",
            font=ctk.CTkFont(size=FONT_MD),
            command=do_clear,
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
    
    def _on_refresh_cache_stats(self):
        """Refresh and display cache statistics."""
        self.cache_stats_text.configure(state="normal")
        self.cache_stats_text.delete("1.0", "end")
        
        try:
            if self.tts_engine:
                stats = self.tts_engine.get_audio_cache_statistics()
                
                # Format statistics
                lines = [
                    f"Cache Enabled: {'Yes' if stats.get('enabled', False) else 'No'}",
                    f"Cached Entries: {stats.get('entries', 0)}",
                    f"Current Size: {stats.get('size_mb', 0):.2f} MB / {self.cache_max_size_var.get()} MB",
                ]
                
                # Add hit rate if available (already returned as percentage from audio_cache)
                if 'hit_rate' in stats:
                    hit_rate = stats['hit_rate']
                    hit_rate_color = "green" if hit_rate >= 50 else "orange" if hit_rate >= 25 else "gray"
                    lines.append(f"Hit Rate: {hit_rate:.1f}%")
                
                # Add time saved if available
                if 'total_saved_time' in stats:
                    lines.append(f"Time Saved: {stats['total_saved_time']:.1f}s")
                
                # Add cache directory if available
                if 'cache_dir' in stats:
                    lines.append(f"Cache Path: {stats['cache_dir']}")
                
                self.cache_stats_text.insert("1.0", "\n".join(lines))
            else:
                self.cache_stats_text.insert("1.0", "TTS engine not available.")
        except Exception as e:
            logger.error(f"Error getting cache statistics: {e}")
            self.cache_stats_text.insert("1.0", f"Error retrieving cache statistics: {e}")
        
        self.cache_stats_text.configure(state="disabled")
    
    def _on_cache_size_change(self, value):
        """Update cache size label when slider changes."""
        self.cache_size_value_label.configure(text=f"{int(value)} MB")
    
    def _test_osc_connection(self):
        """Test OSC configuration and show honest UDP-limited result."""
        self.osc_status_label.configure(text="Testing...", text_color="gray")
        self.window.update()
        try:
            port_val = self.osc_port_var.get().strip()
            port = int(port_val) if port_val else 9000
        except ValueError:
            self.osc_status_label.configure(text="Invalid port. Use a number (e.g. 9000).", text_color="orange")
            return
        ip = self.osc_ip_var.get().strip() or "127.0.0.1"
        if not VRChatOSCClient:
            self.osc_status_label.configure(text="OSC client not available.", text_color="orange")
            return
        client = VRChatOSCClient(ip=ip, port=port)
        success, message = client.test_connection()
        if success:
            self.osc_status_label.configure(text="OSC configured correctly. Messages will be sent to VRChat if it's running with OSC enabled.", text_color="green")
        else:
            self.osc_status_label.configure(text=message + " Ensure VRChat is running and OSC is enabled in VRChat settings. UDP is connectionless so this test cannot guarantee VRChat is receiving.", text_color="orange")

    def _parse_abbreviations(self, text: str) -> tuple[dict, list[str]]:
        """Parse abbreviation text into a dictionary. Returns (parsed_dict, error_messages)."""
        parsed = {}
        errors = []
        for line_num, line in enumerate(text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                continue
            if "=" not in line:
                errors.append(f"Line {line_num}: missing '=' (use key=expansion)")
                continue
            parts = line.split("=", 1)
            if len(parts) != 2:
                errors.append(f"Line {line_num}: invalid format")
                continue
            key = parts[0].strip()
            value = parts[1].strip()
            if not key:
                errors.append(f"Line {line_num}: empty key")
                continue
            if not value:
                errors.append(f"Line {line_num}: empty expansion for key '{key}'")
                continue
            parsed[key] = value
        return parsed, errors

    def _validate_abbreviations(self):
        """Validate abbreviation text and update status label."""
        text = self.abbrev_text.get("1.0", "end-1c")
        parsed, errors = self._parse_abbreviations(text)
        count = len(parsed)
        if not errors:
            self.abbrev_status_label.configure(
                text=f"✓ Format valid - {count} abbreviation(s) found",
                text_color="green"
            )
        elif parsed:
            self.abbrev_status_label.configure(
                text=f"⚠ Warning: {count} abbreviation(s) found. Issues: " + "; ".join(errors[:3]) + ("..." if len(errors) > 3 else ""),
                text_color="orange"
            )
        else:
            self.abbrev_status_label.configure(
                text="✗ Error: " + "; ".join(errors[:5]) + ("..." if len(errors) > 5 else ""),
                text_color="red"
            )
    
    def _load_data(self):
        """Load voices and devices asynchronously."""
        self._load_voices()
        self._load_devices()
        # Initialize cache statistics display
        self._on_refresh_cache_stats()
    
    def _load_voices(self):
        """Load available voices and populate dropdown; store friendly name -> short_name mapping."""
        def do_load():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                voices = loop.run_until_complete(self.tts_engine.get_available_voices())
                self.window.after(0, lambda: self._apply_voices_ui(voices))
            finally:
                loop.close()
        threading.Thread(target=do_load, daemon=True).start()
    
    def _apply_voices_ui(self, voices: List[Dict]):
        """Apply loaded voices to UI: build mapping, show friendly names, set current from saved short_name."""
        self._voices = voices
        self._voice_name_to_short_name.clear()
        friendly_names = []
        for v in voices:
            name = v.get("name", "")
            short = v.get("short_name", "")
            if name and short:
                self._voice_name_to_short_name[name] = short
                friendly_names.append(name)
        
        # Store the mapping in settings manager for voice migration
        self.settings.set_voices_mapping(self._voice_name_to_short_name)
        
        # Check if current stored voice needs migration and rewrite it if needed
        current_voice = self.settings.get("voice", "en-US-AriaNeural")
        if current_voice and current_voice in self._voice_name_to_short_name:
            # Current voice is a friendly name, migrate to short name
            short_name = self._voice_name_to_short_name[current_voice]
            self.settings.set("voice", short_name)
            logger.info("Migrated voice setting from '%s' to '%s'", current_voice, short_name)
        
        self._filtered_voices = list(self._voices)
        # Populate language and region filter dropdowns from loaded voice data
        unique_locales = sorted({v.get("locale") for v in self._voices if v.get("locale")})
        unique_langs = sorted({(v.get("locale") or "").split("-")[0] for v in self._voices if v.get("locale")})
        languages_list = ["All Languages"] + unique_langs
        regions_list = ["All Regions"] + unique_locales
        self.language_filter.configure(values=languages_list)
        self.region_filter.configure(values=regions_list)
        # Preserve current filter selections if still valid, otherwise reset to All
        if self.language_filter_var.get() not in languages_list:
            self.language_filter_var.set("All Languages")
        if self.region_filter_var.get() not in regions_list:
            self.region_filter_var.set("All Regions")
        self.voice_dropdown.configure(values=friendly_names if friendly_names else ["No voices available"])
        saved_voice = self.settings.get("voice", "en-US-AriaNeural")
        display_name = None
        for v in self._voices:
            if v.get("short_name") == saved_voice:
                display_name = v.get("name")
                break
        if display_name and display_name in self._voice_name_to_short_name:
            self.voice_var.set(display_name)
        elif friendly_names:
            self.voice_var.set(friendly_names[0])
        self._update_voice_info()
        self._apply_voice_filters()
        count = len(self._filtered_voices)
        self.voice_count_label.configure(text=f"{count} voice(s) available")
        self._refresh_favorites_ui()
        self._refresh_recent_ui()
        
        # Create language mapping controls after voices are loaded
        if not getattr(self, 'language_mapping_controls_created', False):
            self._create_language_mapping_controls()
            self.language_mapping_controls_created = True
    
    def _update_voice_info(self):
        """Update voice info panel from current selection; support both friendly name and short_name."""
        current = self.voice_var.get()
        voice = None
        for v in self._filtered_voices:
            if v.get("name") == current or v.get("short_name") == current:
                voice = v
                break
        if not voice and current:
            for v in self._voices:
                if v.get("name") == current or v.get("short_name") == current:
                    voice = v
                    break
        if voice:
            self.voice_info_name_value.configure(text=voice.get("name", "-"))
            self.voice_info_gender_value.configure(text=voice.get("gender", "-"))
            self.voice_info_locale_value.configure(text=voice.get("locale", "-"))
            self.voice_info_short_value.configure(text=voice.get("short_name", "-"))
        else:
            self.voice_info_name_value.configure(text="-")
            self.voice_info_gender_value.configure(text="-")
            self.voice_info_locale_value.configure(text="-")
            self.voice_info_short_value.configure(text="-")
    
    def _apply_voice_filters(self):
        """Apply language/gender/region filters to voice list."""
        lang = self.language_filter_var.get()
        gender = self.gender_filter_var.get()
        region = self.region_filter_var.get()
        search = self.search_entry.get().strip().lower()
        filtered = self._voices
        if lang and lang != "All" and lang != "All Languages":
            filtered = [v for v in filtered if v.get("locale", "").startswith(lang.split("-")[0] + "-") or v.get("locale") == lang]
        if gender and gender != "All":
            filtered = [v for v in filtered if (v.get("gender") or "").lower() == gender.lower()]
        if region and region != "All" and region != "All Regions":
            filtered = [v for v in filtered if (v.get("locale") or "") == region or (v.get("locale") or "").startswith(region)]
        if search:
            filtered = [v for v in filtered if search in (v.get("name") or "").lower() or search in (v.get("short_name") or "").lower() or search in (v.get("locale") or "").lower()]
        self._filtered_voices = filtered
        names = [v.get("name", "") for v in filtered if v.get("name")]
        self.voice_dropdown.configure(values=names if names else ["No matching voices"])
        if names and self.voice_var.get() not in names:
            self.voice_var.set(names[0])
        self._update_voice_info()
        self.voice_count_label.configure(text=f"{len(filtered)} voice(s)")
    
    def _on_voice_selection_change(self, choice):
        """Handle voice dropdown change."""
        self._update_voice_info()
        self._update_favorite_button()
        # Add selected voice to recent list
        short = self._voice_name_to_short_name.get(self.voice_var.get())
        if short:
            recents = list(self.settings.get("recent_voices", []))
            if short in recents:
                recents.remove(short)
            recents.insert(0, short)
            recents = recents[:20]
            self.settings.set("recent_voices", recents)
            self._refresh_recent_ui()
    
    def _on_voice_search(self, event=None):
        """Handle voice search key release."""
        self._apply_voice_filters()
    
    def _clear_filters(self):
        """Reset filters to All."""
        self.language_filter_var.set("All Languages")
        self.gender_filter_var.set("All")
        self.region_filter_var.set("All Regions")
        self.search_entry.delete(0, "end")
        self._apply_voice_filters()
    
    def _toggle_favorite_voice(self):
        """Toggle current voice as favorite."""
        short = self._voice_name_to_short_name.get(self.voice_var.get())
        if not short:
            return
        favs = list(self.settings.get("favorite_voices", []))
        if short in favs:
            favs.remove(short)
        else:
            favs.append(short)
        self.settings.set("favorite_voices", favs)
        self._update_favorite_button()
        self._refresh_favorites_ui()
    
    def _update_favorite_button(self):
        """Update favorite star button state."""
        short = self._voice_name_to_short_name.get(self.voice_var.get())
        favs = self.settings.get("favorite_voices", [])
        self.favorite_button.configure(text="★" if short and short in favs else "☆")
    
    def _display_name_for_short(self, short_name: str) -> Optional[str]:
        """Return display (friendly) name for a voice short_name, or None if not found."""
        for v in self._voices:
            if v.get("short_name") == short_name:
                return v.get("name")
        return None
    
    def _refresh_favorites_ui(self):
        """Populate Favorite Voices section with clickable buttons."""
        for c in list(self.favorites_frame.winfo_children()):
            c.destroy()
        favs = self.settings.get("favorite_voices", [])
        if not favs:
            lbl = ctk.CTkLabel(
                self.favorites_frame,
                text="No favorite voices yet. Click the star button to add favorites!",
                font=ctk.CTkFont(size=11),
                text_color="gray"
            )
            lbl.pack(pady=20)
            return
        for short in favs:
            display = self._display_name_for_short(short)
            if not display:
                continue
            btn = ctk.CTkButton(
                self.favorites_frame,
                text=display,
                font=ctk.CTkFont(size=11),
                command=lambda s=short: self._select_voice_by_short_name(s),
                width=200,
                anchor="w",
                fg_color="transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray75", "gray25")
            )
            btn.pack(anchor="w", pady=2, padx=2)
    
    def _refresh_recent_ui(self):
        """Populate Recent Voices section with clickable buttons."""
        for c in list(self.recent_frame.winfo_children()):
            c.destroy()
        recents = self.settings.get("recent_voices", [])
        if not recents:
            lbl = ctk.CTkLabel(
                self.recent_frame,
                text="No recent voices yet.",
                font=ctk.CTkFont(size=11),
                text_color="gray"
            )
            lbl.pack(pady=20)
            return
        for short in recents:
            display = self._display_name_for_short(short)
            if not display:
                continue
            btn = ctk.CTkButton(
                self.recent_frame,
                text=display,
                font=ctk.CTkFont(size=11),
                command=lambda s=short: self._select_voice_by_short_name(s),
                width=200,
                anchor="w",
                fg_color="transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray75", "gray25")
            )
            btn.pack(anchor="w", pady=2, padx=2)
    
    def _select_voice_by_short_name(self, short_name: str):
        """Set the voice dropdown to the voice with the given short_name (used by favorites/recent clicks)."""
        display = self._display_name_for_short(short_name)
        if not display:
            return
        self.voice_var.set(display)
        self._update_voice_info()
        self._update_favorite_button()
        # Add to recent (dedupe, move to front, cap at 20)
        recents = list(self.settings.get("recent_voices", []))
        if short_name in recents:
            recents.remove(short_name)
        recents.insert(0, short_name)
        recents = recents[:20]
        self.settings.set("recent_voices", recents)
        self._refresh_recent_ui()
    
    def _validate_preview_text(self, text: str) -> bool:
        """
        Validate preview text to ensure it doesn't contain parameter-like patterns
        or other suspicious content that might indicate corruption.
        
        Args:
            text: The text to validate
            
        Returns:
            True if text is valid, False if it appears corrupted
        """
        if not text or not isinstance(text, str):
            return False
        
        # Check for parameter-like patterns that shouldn't be in preview text
        # Use anchored patterns to catch corrupted TTS parameter strings while
        # allowing normal sentences that contain these words mid-sentence
        param_patterns = [
            r'^rate\s*=',      # Matches "rate=" at start of string or line
            r'^volume\s*=',
            r'^pitch\s*=',
            r'^voice\s*=',
            r'^speed\s*=',
        ]
        
        for pattern in param_patterns:
            if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
                logger.warning("Preview text contains suspicious parameter pattern: %s", pattern)
                return False
        
        # Check if text contains only printable characters
        if not all(c.isprintable() or c.isspace() for c in text):
            logger.warning("Preview text contains non-printable characters")
            return False
        
        # Check for reasonable length (not too long or too short after stripping)
        # Upper bound raised to 5000 to allow longer preview passages
        stripped = text.strip()
        if len(stripped) < 1 or len(stripped) > 5000:
            logger.warning("Preview text length out of bounds: %d", len(stripped))
            return False
        
        return True
    
    def _reset_preview_text(self):
        """Reset preview text to the default value."""
        self.preview_text_var.set(DEFAULT_PREVIEW_TEXT)
        logger.debug("Preview text reset to default")
    
    def _on_voice_preview(self):
        """Start voice preview: non-blocking TTS generation and playback to default (local) device."""
        if self._preview_playing:
            return
        short = self._voice_name_to_short_name.get(self.voice_var.get())
        if not short:
            self.preview_loading_label.configure(text="Select a voice first.")
            return
        
        # Get and validate preview text - create local copy immediately for isolation
        raw_text = str(self.preview_text_var.get()).strip()
        
        # Validate the text doesn't contain suspicious patterns
        if not self._validate_preview_text(raw_text):
            logger.warning("Preview text validation failed, using default. Original: '%s'", raw_text)
            raw_text = DEFAULT_PREVIEW_TEXT
            self.preview_text_var.set(DEFAULT_PREVIEW_TEXT)
        
        text = raw_text if raw_text else DEFAULT_PREVIEW_TEXT
        
        # Log preview parameters for debugging
        logger.debug("Preview starting - voice: %s, rate: %d, volume: %d, pitch: %d", 
                     short, self.rate_var.get(), self.volume_var.get(), self.pitch_var.get())
        logger.debug("Preview text: '%s'", text)
        
        self._preview_stop_event.clear()
        self._preview_playing = True
        self._set_preview_ui_loading(True)
        self.preview_loading_label.configure(text="Generating...", text_color="gray")

        def run():
            loop = None
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # Log the exact text being sent to TTS for debugging
                logger.debug("Preview TTS request - text: '%s', voice: %s", text, short)
                
                audio_data, err = loop.run_until_complete(
                    self.tts_engine.generate_speech(
                        text, short,
                        self.rate_var.get(),
                        self.volume_var.get(),
                        self.pitch_var.get(),
                        self._preview_stop_event,
                    )
                )
                if self._preview_stop_event.is_set():
                    self.window.after(0, lambda: self._preview_done(None))
                    return
                if err:
                    # Include the text that was attempted in error for debugging
                    error_msg = f"TTS error: {err} (text: '{text[:50]}...')" if len(text) > 50 else f"TTS error: {err} (text: '{text}')"
                    logger.warning("Preview generation failed: %s", error_msg)
                    self.window.after(0, lambda: self._preview_done(err))
                    return
                if not audio_data:
                    self.window.after(0, lambda: self._preview_done("No audio generated."))
                    return
                
                # Validate audio_data has reasonable size
                if len(audio_data) < 100:
                    logger.warning("Preview audio data too small: %d bytes", len(audio_data))
                    self.window.after(0, lambda: self._preview_done("Audio data too small."))
                    return
                
                logger.debug("Preview audio generated: %d bytes", len(audio_data))
                
                self.window.after(0, lambda: self._preview_loading_playing())
                if self._preview_stop_event.is_set():
                    self.window.after(0, lambda: self._preview_done(None))
                    return
                enable_norm = self.settings.get("enable_normalization", True)
                norm_type = self.settings.get("normalization_type", "Peak")
                # Play to default (local) device so user hears preview on headphones/speakers
                success = loop.run_until_complete(
                    self.audio_router.play_audio_to_device(
                        audio_data, 48000, None, enable_norm, norm_type
                    )
                )
                if self._preview_stop_event.is_set():
                    pass
                elif not success:
                    self.window.after(0, lambda: self._preview_done("Playback failed."))
                    return
                self.window.after(0, lambda: self._preview_done(None))
            except Exception as e:
                logger.error("Preview exception: %s", str(e), exc_info=True)
                self.window.after(0, lambda: self._preview_done(str(e)))
            finally:
                if loop:
                    loop.close()

        threading.Thread(target=run, daemon=True).start()

    def _set_preview_ui_loading(self, loading: bool):
        """Enable/disable preview controls during generation or playback to prevent freezes and double actions."""
        if loading:
            self.preview_button.pack_forget()
            self.stop_preview_button.pack(side="left", padx=5)
            self.preview_text_entry.configure(state="disabled")
        else:
            self.stop_preview_button.pack_forget()
            self.preview_button.pack(side="left", padx=5)
            self.preview_text_entry.configure(state="normal")

    def _preview_loading_playing(self):
        """Update loading label to Playing... (called from worker via after(0))."""
        self.preview_loading_label.configure(text="Playing...")

    def _preview_done(self, error: Optional[str]):
        """Called on main thread when preview generation and playback finish."""
        self._preview_playing = False
        self._set_preview_ui_loading(False)
        if error:
            self.preview_loading_label.configure(text=error, text_color="#e74c3c")
            def clear_error():
                self.preview_loading_label.configure(text="", text_color="gray")
            self.window.after(3000, clear_error)
        else:
            self.preview_loading_label.configure(text="", text_color="gray")

    def _stop_voice_preview(self):
        """Stop voice preview (generation or playback)."""
        self._preview_stop_event.set()
        if self.audio_router:
            self.audio_router.stop_playback()
    
    def _update_device_info(self):
        """Update the Device Information textbox with the currently selected device."""
        device_name = self.device_var.get()
        device = None
        for d in self._devices:
            if d.get("name") == device_name:
                device = d
                break
        self.device_info_text.configure(state="normal")
        self.device_info_text.delete("1.0", "end")
        if device:
            lines = [
                f"Name: {device.get('name', '—')}",
                f"Index: {device.get('index', '—')}",
                f"Channels: {device.get('channels', '—')}",
                f"Sample rate: {device.get('sample_rate', '—')} Hz",
            ]
            self.device_info_text.insert("1.0", "\n".join(lines))
        else:
            self.device_info_text.insert("1.0", "No device selected or devices not loaded.")
        self.device_info_text.configure(state="disabled")
    
    def _load_devices(self):
        """Load audio output devices, filtering for VB-Cable virtual audio devices only."""
        all_devices = self.audio_router.get_audio_devices() if self.audio_router else []
        
        # Filter for VB-Cable/CABLE devices only (case-insensitive)
        # These are virtual audio devices used to route audio to VRChat/Discord
        vbcable_keywords = ["cable", "vb-audio", "vbaudio", "vb cable"]
        self._devices = [
            d for d in all_devices 
            if any(kw in d.get("name", "").lower() for kw in vbcable_keywords)
        ]
        
        # Update warning label based on whether VB-Cable devices were found
        if not self._devices:
            self.vbcable_warning_label.configure(
                text="⚠️ No VB-Cable devices found. Please install VB-Cable from vb-audio.com to route TTS audio to VRChat/Discord."
            )
            self.device_dropdown.configure(values=["No VB-Cable devices found"])
            self.device_var.set("No VB-Cable devices found")
        else:
            self.vbcable_warning_label.configure(text="")
            names = [d.get("name", "Unknown") for d in self._devices]
            self.device_dropdown.configure(values=names)
            
            # Try to select the previously saved device
            idx = self.settings.get("device_index")
            found_saved = False
            for d in self._devices:
                if d.get("index") == idx:
                    self.device_var.set(d.get("name", "Unknown"))
                    found_saved = True
                    break
            
            # If saved device not found or not set, select first VB-Cable device
            if not found_saved and names:
                self.device_var.set(names[0])
        
        self._update_device_info()
    
    def _on_rate_change(self, value):
        self.rate_value_label.configure(text=f"{int(value)}%")
    
    def _on_volume_change(self, value):
        self.volume_value_label.configure(text=f"{int(value)}%")
    
    def _on_pitch_change(self, value):
        self.pitch_value_label.configure(text=f"{int(value)}%")
    
    def _on_viseme_smoothing_change(self, value):
        """Update viseme smoothing label when slider changes."""
        self.viseme_smoothing_value_label.configure(text=f"{int(value)}%")
    
    def _validate_keybind_entry(self, action_name: str):
        """Validate a keybind entry in real-time and update the visual indicator."""
        if not hasattr(self, 'keybind_vars') or action_name not in self.keybind_vars:
            return
        
        keybind_string = self.keybind_vars[action_name].get().strip()
        validation_label = self.keybind_validation_labels.get(action_name)
        
        if not validation_label:
            return
        
        # Empty keybind - valid (disabled)
        if not keybind_string:
            validation_label.configure(text="", text_color="gray")
            return
        
        # Check format validity
        is_valid = self._keybind_manager.validate_keybind(keybind_string)
        
        if not is_valid:
            validation_label.configure(text="✗", text_color="#e74c3c")  # Red
            return
        
        # Check for duplicates within the current settings
        duplicates = []
        for other_action, other_var in self.keybind_vars.items():
            if other_action != action_name:
                other_value = other_var.get().strip()
                if other_value and other_value.lower() == keybind_string.lower():
                    duplicates.append(other_action)
        
        if duplicates:
            validation_label.configure(text="⚠", text_color="#f39c12")  # Orange
        else:
            validation_label.configure(text="✓", text_color="#2ecc71")  # Green
    
    def _on_save(self):
        """Save settings; store voice as short_name."""
        # First, populate settings with current UI values so validation checks the pending data
        
        # Save voice setting
        short = self._voice_name_to_short_name.get(self.voice_var.get())
        if short:
            self.settings.set("voice", short)
        
        # Save device setting
        device_name = self.device_var.get()
        for d in self._devices:
            if d.get("name") == device_name:
                self.settings.set("device_index", d.get("index"))
                break
        
        # Save basic audio settings
        self.settings.set("rate", self.rate_var.get())
        self.settings.set("volume", self.volume_var.get())
        self.settings.set("pitch", self.pitch_var.get())
        self.settings.set("appearance_mode", self.appearance_var.get())
        
        # Save voice settings
        self.settings.set("voice_preview_text", self.preview_text_var.get())
        self.settings.set("voice_filter_language", self.language_filter_var.get())
        self.settings.set("voice_filter_gender", self.gender_filter_var.get())
        self.settings.set("voice_filter_region", self.region_filter_var.get())
        
        # Save audio processing settings
        self.settings.set("normalization_type", self.norm_var.get())
        self.settings.set("enable_normalization", self.enable_norm_var.get())
        
        # Save VRChat OSC settings
        self.settings.set("vrchat_osc_enabled", self.osc_enabled_var.get())
        self.settings.set("vrchat_osc_ip", self.osc_ip_var.get().strip() or "127.0.0.1")
        try:
            self.settings.set("vrchat_osc_port", int(self.osc_port_var.get().strip()) if self.osc_port_var.get().strip() else 9000)
        except ValueError:
            self.settings.set("vrchat_osc_port", 9000)
        self.settings.set("vrchat_osc_play_sound", self.osc_play_sound_var.get())
        self.settings.set("vrchat_osc_send_on_speak", self.osc_send_on_speak_var.get())
        
        # Save auto language detection setting
        self.settings.set("auto_language_detection", self.auto_language_var.get())
        
        # Save language voice mappings
        self._save_language_mappings()
        
        # Save advanced settings
        self.settings.set("audio_cache_enabled", self.cache_enabled_var.get())
        self.settings.set("audio_cache_max_size_mb", self.cache_max_size_var.get())
        self.settings.set("processing_profile", self.processing_profile_var.get())
        
        # Validate and save text cache size
        try:
            text_cache_size = int(self.text_cache_size_var.get())
            if 100 <= text_cache_size <= 10000:
                self.settings.set("text_cache_size", text_cache_size)
            else:
                logger.warning("Text cache size out of range: %d, using default", text_cache_size)
                self.settings.set("text_cache_size", 1000)
        except ValueError:
            logger.warning("Invalid text cache size: %s, using default", self.text_cache_size_var.get())
            self.settings.set("text_cache_size", 1000)
        
        # Save experimental features
        self.settings.set("enable_streaming", self.streaming_playback_var.get())
        
        # Save VRChat viseme settings
        self.settings.set("vrchat_viseme_enabled", self.viseme_enabled_var.get())
        self.settings.set("vrchat_viseme_smoothing", self.viseme_smoothing_var.get() / 100.0)
        self.settings.set("vrchat_voice_amplitude_enabled", self.viseme_amplitude_var.get())
        
        # Save abbreviations
        abbrev_raw = self.abbrev_text.get("1.0", "end-1c")
        parsed_abbrev, abbrev_errors = self._parse_abbreviations(abbrev_raw)
        if abbrev_errors:
            self.abbrev_status_label.configure(
                text="Saved with warnings: " + "; ".join(abbrev_errors[:3]) + ("..." if len(abbrev_errors) > 3 else ""),
                text_color="orange",
                wraplength=550
            )
        self.settings.set("abbreviations", parsed_abbrev)
        
        # Now validate all settings after UI values have been applied
        validation_issues = self.settings.validate_settings()
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
            
            ctk.CTkLabel(
                error_dialog,
                text="Settings Validation Failed",
                font=ctk.CTkFont(size=16, weight="bold")
            ).pack(pady=(20, 10))
            
            ctk.CTkLabel(
                error_dialog,
                text=error_msg,
                font=ctk.CTkFont(size=11),
                wraplength=400
            ).pack(pady=10)
            
            ctk.CTkButton(
                error_dialog,
                text="OK",
                command=error_dialog.destroy,
                width=100
            ).pack(pady=20)
            
            return
        
        # Apply appearance mode change
        ctk.set_appearance_mode(self.appearance_var.get())
        
        # Validate and save keybinds
        keybinds_saved = {}
        invalid_keybinds = []
        empty_keybinds = []
        
        for action, var in getattr(self, "keybind_vars", {}).items():
            keybind_value = (var.get() or "").strip()
            
            # Empty keybind means disabled - skip validation but don't save
            if not keybind_value:
                empty_keybinds.append(action)
                continue
            
            # Validate the keybind
            if self._keybind_manager.validate_keybind(keybind_value):
                keybinds_saved[action] = keybind_value
            else:
                invalid_keybinds.append((action, keybind_value))
        
        # Show error if there are invalid keybinds
        if invalid_keybinds:
            error_msg = "Invalid keybinds detected:\n"
            for action, value in invalid_keybinds:
                error_msg += f"  - {action}: '{value}'\n"
            error_msg += "\nValid format examples: Ctrl+Enter, Alt+Shift+A, Escape, F1"
            
            # Show error dialog
            error_dialog = ctk.CTkToplevel(self.window)
            error_dialog.title("Invalid Keybinds")
            error_dialog.geometry("400x250")
            error_dialog.transient(self.window)
            error_dialog.grab_set()
            
            ctk.CTkLabel(
                error_dialog,
                text="Invalid Keybinds",
                font=ctk.CTkFont(size=16, weight="bold")
            ).pack(pady=(20, 10))
            
            ctk.CTkLabel(
                error_dialog,
                text=error_msg,
                font=ctk.CTkFont(size=11),
                wraplength=350
            ).pack(pady=10)
            
            ctk.CTkButton(
                error_dialog,
                text="OK",
                command=error_dialog.destroy,
                width=100
            ).pack(pady=20)
            
            # Don't save settings if invalid keybinds exist
            return
        
        # Check for duplicate keybinds across all actions being saved
        keybind_to_actions = {}
        for action, keybind in keybinds_saved.items():
            normalized = keybind.lower()
            if normalized not in keybind_to_actions:
                keybind_to_actions[normalized] = []
            keybind_to_actions[normalized].append(action)
        
        # Find duplicates (keybinds used by multiple actions)
        duplicates = {k: v for k, v in keybind_to_actions.items() if len(v) > 1}
        
        if duplicates:
            error_msg = "Duplicate keybinds detected:\n\n"
            for keybind, actions in duplicates.items():
                action_names = [a.replace("_", " ").title() for a in actions]
                error_msg += f"Keybind '{keybind}' is used by:\n"
                for name in action_names:
                    error_msg += f"  - {name}\n"
                error_msg += "\n"
            error_msg += "Please assign unique keybinds to each action."
            
            # Show error dialog
            error_dialog = ctk.CTkToplevel(self.window)
            error_dialog.title("Duplicate Keybinds")
            error_dialog.geometry("450x300")
            error_dialog.transient(self.window)
            error_dialog.grab_set()
            
            ctk.CTkLabel(
                error_dialog,
                text="Duplicate Keybinds",
                font=ctk.CTkFont(size=16, weight="bold")
            ).pack(pady=(20, 10))
            
            ctk.CTkLabel(
                error_dialog,
                text=error_msg,
                font=ctk.CTkFont(size=11),
                wraplength=400
            ).pack(pady=10)
            
            ctk.CTkButton(
                error_dialog,
                text="OK",
                command=error_dialog.destroy,
                width=100
            ).pack(pady=20)
            
            # Don't save settings if duplicates exist
            return
        
        # Log disabled keybinds
        if empty_keybinds:
            logger.info(f"Keybinds disabled (empty): {', '.join(empty_keybinds)}")
        
        self.settings.set("keybinds", keybinds_saved)
        speak_mode = "current_line" if (getattr(self, "speak_mode_current_line_var", None) and self.speak_mode_current_line_var.get()) else "all_text"
        self.settings.set("speak_mode", speak_mode)
        
        # Save all settings
        if not self.settings.save_settings():
            # Show save error dialog
            error_dialog = ctk.CTkToplevel(self.window)
            error_dialog.title("Save Error")
            error_dialog.geometry("400x200")
            error_dialog.transient(self.window)
            error_dialog.grab_set()
            
            ctk.CTkLabel(
                error_dialog,
                text="Failed to Save Settings",
                font=ctk.CTkFont(size=16, weight="bold")
            ).pack(pady=(20, 10))
            
            ctk.CTkLabel(
                error_dialog,
                text="There was an error saving your settings to disk.\nPlease check file permissions and try again.",
                font=ctk.CTkFont(size=11),
                wraplength=350
            ).pack(pady=10)
            
            ctk.CTkButton(
                error_dialog,
                text="OK",
                command=error_dialog.destroy,
                width=100
            ).pack(pady=20)
            
            return
        
        # Notify parent window of successful save
        if self.on_save:
            self.on_save()
        
        self.window.destroy()
    
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
    
    def _on_refresh(self):
        self._load_data()
    
    def _start_keybind_capture(self, action_name: str):
        """Start capturing keybind for the specified action."""
        # Disable all capture buttons and change the current one to "Press keys..."
        for action, btn in self.keybind_capture_buttons.items():
            if action == action_name:
                btn.configure(text="Press keys...", fg_color="#e67e22", hover_color="#d35400")
            else:
                btn.configure(state="disabled")
        
        # Store which action is being captured
        self._capturing_keybind = action_name
        
        # Set up key listener
        self.window.bind("<KeyPress>", self._on_key_capture_press)
        self.window.bind("<KeyRelease>", self._on_key_capture_release)
        
        # Show capture instructions
        self.keybind_validation_labels[action_name].configure(text="Capturing...", text_color="blue")
        
        # Set focus to window to ensure key events are captured
        self.window.focus_force()
    
    def _on_key_capture_press(self, event):
        """Handle key press during keybind capture."""
        if not self._capturing_keybind:
            return
        
        # Ignore modifier-only key presses
        if event.keysym in ['Control_L', 'Control_R', 'Shift_L', 'Shift_R', 'Alt_L', 'Alt_R', 'Super_L', 'Super_R']:
            return
        
        # Build keybind string from modifiers and key
        modifiers = []
        if event.state & 0x4:  # Control key
            modifiers.append('Ctrl')
        if event.state & 0x1:  # Shift key
            modifiers.append('Shift')
        if event.state & 0x8:  # Alt key
            modifiers.append('Alt')
        
        # Get the key
        key = event.keysym
        if key in ['Return', 'Escape', 'Tab', 'BackSpace', 'Delete', 'Insert', 'Home', 'End', 'Prior', 'Next']:
            pass  # Use as-is
        elif len(key) == 1 and key.isalnum():
            key = key.upper()
        else:
            # For special keys, try to map to common names
            key_mapping = {
                'space': 'Space',
                'comma': ',',
                'period': '.',
                'slash': '/',
                'semicolon': ';',
                'quote': "'",
                'backslash': '\\',
                'bracketleft': '[',
                'bracketright': ']',
                'minus': '-',
                'equal': '=',
                'grave': '`'
            }
            key = key_mapping.get(key.lower(), key)
        
        # Build the keybind string
        if modifiers:
            keybind_string = "+".join(modifiers + [key])
        else:
            keybind_string = key
        
        # Update the entry
        self.keybind_vars[self._capturing_keybind].set(keybind_string)
        
        # Validate the keybind
        self._validate_keybind_entry(self._capturing_keybind)
        
        # Stop capturing
        self._stop_keybind_capture()
    
    def _on_key_capture_release(self, event):
        """Handle key release during keybind capture."""
        # This is mainly for cleanup, but we handle the capture in press
        pass
    
    def _stop_keybind_capture(self):
        """Stop keybind capture and reset UI."""
        if not self._capturing_keybind:
            return
        
        # Unbind key events
        self.window.unbind("<KeyPress>")
        self.window.unbind("<KeyRelease>")
        
        # Reset button states
        for action, btn in self.keybind_capture_buttons.items():
            if action == self._capturing_keybind:
                btn.configure(text="Set", fg_color="#3498db", hover_color="#2980b9")
            else:
                btn.configure(state="normal")
        
        # Clear capturing state
        self._capturing_keybind = None
    
    def _on_settings_resize(self, event):
        """Handle window resize to dynamically update wraplength for labels.
        
        This ensures text wraps properly when the window is resized,
        preventing text overflow and maintaining readability.
        """
        # Only process if this is a resize event for our window
        if event.widget != self.window:
            return
        
        # Calculate available width for text wrapping
        # Account for window borders, padding, and tab margins
        # Typical padding: ~40px total (20px each side), tab margins: ~20px
        available_width = max(100, event.width - 80)
        
        # Update wraplength for all registered labels
        for label in self._wraplength_labels:
            try:
                if label.winfo_exists():
                    label.configure(wraplength=available_width)
            except Exception:
                # Widget may have been destroyed, ignore
                pass
