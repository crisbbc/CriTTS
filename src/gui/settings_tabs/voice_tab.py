"""
Voice Tab
Settings for voice selection, preview, and voice parameters.
"""
import asyncio
import logging
import threading
import re
import customtkinter as ctk
from typing import Any, Callable, Optional, List, Dict

from .base_tab import BaseTab
from ..theme_constants import (
    FONT_SM, FONT_MD, FONT_LG, FONT_WEIGHT_BOLD,
    BUTTON_HEIGHT,
    COLOR_DANGER, COLOR_DANGER_HOVER,
    COLOR_SUCCESS, COLOR_SUCCESS_HOVER,
    SPACING_MD,
)
from ..utils.scroll_utils import prevent_scroll_propagation

logger = logging.getLogger(__name__)

# Default preview text constant
DEFAULT_PREVIEW_TEXT = "Hello, this is a voice preview."


class VoiceTab(BaseTab):
    """Tab for voice settings."""
    
    def __init__(
        self,
        tab_widget: ctk.CTkFrame,
        settings_manager: Any,
        tts_engine: Any = None,
        audio_router: Any = None,
        on_change: Optional[Callable] = None,
        parent_window: ctk.CTk = None
    ):
        self.parent_window = parent_window
        self._async_callbacks_active = True
        self._voice_load_request_id = 0
        self._voices: List[Dict] = []
        self._filtered_voices: List[Dict] = []
        self._voice_name_to_short_name: Dict[str, str] = {}
        self._preview_playing = False
        self._preview_stop_event = threading.Event()
        self._active_provider_key = settings_manager.get("tts_provider", "edge")
        
        super().__init__(tab_widget, settings_manager, tts_engine, audio_router, on_change)

    def invalidate_async_callbacks(self) -> None:
        """Prevent queued background callbacks from touching a stale tab instance."""
        self._async_callbacks_active = False
        if getattr(self, "_preview_playing", False):
            self._preview_playing = False
            preview_stop_event = getattr(self, "_preview_stop_event", None)
            if preview_stop_event is not None:
                preview_stop_event.set()

            audio_router = getattr(self, "audio_router", None)
            if audio_router is not None:
                try:
                    audio_router.stop_playback()
                except Exception:
                    logger.debug("Ignoring preview stop failure during VoiceTab invalidation", exc_info=True)

    def _is_async_callback_target_alive(self) -> bool:
        """Return True while this tab instance still owns live widgets."""
        if not getattr(self, "_async_callbacks_active", True):
            return False

        tab_widget = getattr(self, "tab", None)
        if tab_widget is not None:
            try:
                tab_winfo_exists = getattr(tab_widget, "winfo_exists", None)
                if callable(tab_winfo_exists) and not tab_winfo_exists():
                    return False
            except Exception:
                return False

        return True

    def _schedule_on_ui_thread(self, callback: Callable[[], None], delay_ms: int = 0) -> bool:
        """Safely queue UI work only while the parent window is still available."""
        parent_window = getattr(self, "parent_window", None)
        if parent_window is None:
            return False

        if not self._is_async_callback_target_alive():
            return False

        try:
            winfo_exists = getattr(parent_window, "winfo_exists", None)
            if callable(winfo_exists) and not winfo_exists():
                return False

            def guarded_callback() -> None:
                if not self._is_async_callback_target_alive():
                    return
                callback()

            parent_window.after(delay_ms, guarded_callback)
            return True
        except RuntimeError:
            return False
        except Exception:
            return False
    
    def _create_content(self):
        """Create the voice tab content."""
        self.setup_layout()
        browser_section, browser_content = self.create_section_surface(
            "Voice Selection",
            parent=self.scroll,
            register_sidebar=False,
        )
        browser_section.pack(fill="x", pady=(0, SPACING_MD))

        # Filters frame
        self._create_filters_section(browser_content)
        
        # Search field
        self._create_search_section(browser_content)
        
        # Voice selection
        self._create_voice_selection_section(browser_content)
        
        # Preview controls
        self._create_preview_section(browser_content)
        
        # Voice info panel
        self._create_voice_info_section(browser_content)
        
        # Favorites section
        favorites_section, favorites_content = self.create_section_surface(
            "★ Favorite Voices",
            parent=self.scroll,
        )
        favorites_section.pack(fill="x", pady=(0, SPACING_MD))
        self._create_favorites_section(favorites_content)
        
        # Recent voices section
        recent_section, recent_content = self.create_section_surface(
            "Recent Voices",
            parent=self.scroll,
        )
        recent_section.pack(fill="x", pady=(0, SPACING_MD))
        self._create_recent_section(recent_content)
        
        # Rate/Volume/Pitch sliders
        controls_section, controls_content = self.create_section_surface(
            "Quick Controls",
            parent=self.scroll,
            register_sidebar=False,
        )
        controls_section.pack(fill="x", pady=(0, SPACING_MD))
        self._create_parameter_sliders(controls_content)
        
        # Load voices asynchronously
        self._load_voices()
    
    def _create_filters_section(self, parent):
        """Create the filters section."""
        self.filters_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.filters_frame.pack(fill="x", pady=5)
        
        # Language filter
        self.language_filter_var = ctk.StringVar(value=self.settings.get("voice_filter_language", "All"))
        self.language_filter = ctk.CTkComboBox(
            self.filters_frame,
            variable=self.language_filter_var,
            values=["All Languages"],
            font=ctk.CTkFont(size=FONT_SM),
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
            font=ctk.CTkFont(size=FONT_SM),
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
            font=ctk.CTkFont(size=FONT_SM),
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
            command=self._clear_filters,
        )
        self.clear_filters_button.pack(side="left", padx=10)
    
    def _create_search_section(self, parent):
        """Create the search section."""
        self.search_label = ctk.CTkLabel(
            parent,
            text="Search Voices:",
            font=ctk.CTkFont(size=FONT_MD)
        )
        self.search_label.pack(anchor="w", pady=(10, 5))
        
        self.search_entry = ctk.CTkEntry(
            parent,
            font=ctk.CTkFont(size=FONT_MD),
            placeholder_text="Type to filter voices..."
        )
        self.search_entry.pack(fill="x", pady=5)
        self.search_entry.bind("<KeyRelease>", self._on_voice_search)
        
        # Voice count label
        surface_theme = self.get_active_surface_theme()
        self.voice_count_label = ctk.CTkLabel(
            parent,
            text="Loading voices...",
            font=ctk.CTkFont(size=FONT_SM),
            text_color=surface_theme["text_secondary"],
        )
        self.voice_count_label.pack(anchor="w", pady=(5, 10))
    
    def _create_voice_selection_section(self, parent):
        """Create the voice selection section."""
        self.create_separator(parent).pack(fill="x", pady=5)
        
        self.voice_selection_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.voice_selection_frame.pack(fill="x", pady=5)
        
        self.voice_label = ctk.CTkLabel(
            self.voice_selection_frame,
            text="Selected Voice:",
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD)
        )
        self.voice_label.pack(side="left", padx=5)
        
        self.voice_var = ctk.StringVar()
        self.voice_dropdown = ctk.CTkComboBox(
            self.voice_selection_frame,
            variable=self.voice_var,
            values=["Loading voices..."],
            font=ctk.CTkFont(size=FONT_MD),
            dropdown_font=ctk.CTkFont(size=FONT_SM),
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
            width=BUTTON_HEIGHT,
            height=BUTTON_HEIGHT,
            **self.get_subtle_button_style(),
        )
        self.favorite_button.pack(side="left", padx=5)
    
    def _create_preview_section(self, parent):
        """Create the preview section."""
        self.create_separator(parent).pack(fill="x", pady=10)
        
        self.preview_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.preview_frame.pack(fill="x", pady=10)
        
        # Preview text entry
        preview_text_value = self.settings.get("voice_preview_text", DEFAULT_PREVIEW_TEXT)
        if not self._validate_preview_text(preview_text_value):
            preview_text_value = DEFAULT_PREVIEW_TEXT
        
        self.preview_text_var = ctk.StringVar(value=preview_text_value)
        self.preview_text_entry = ctk.CTkEntry(
            self.preview_frame,
            textvariable=self.preview_text_var,
            font=ctk.CTkFont(size=FONT_MD),
            placeholder_text="Enter preview text..."
        )
        self.preview_text_entry.pack(side="left", fill="x", expand=True, padx=5)
        
        # Reset preview text button
        self.reset_preview_button = ctk.CTkButton(
            self.preview_frame,
            text="↻",
            font=ctk.CTkFont(size=14),
            command=self._reset_preview_text,
            width=BUTTON_HEIGHT,
            height=BUTTON_HEIGHT,
            **self.get_subtle_button_style(),
        )
        self.reset_preview_button.pack(side="left", padx=2)
        
        # Preview button
        self.preview_button = ctk.CTkButton(
            self.preview_frame,
            text="▶ Preview",
            font=ctk.CTkFont(size=FONT_MD),
            command=self._on_voice_preview,
            width=100,
            height=BUTTON_HEIGHT,
            fg_color=COLOR_SUCCESS,
            hover_color=COLOR_SUCCESS_HOVER,
        )
        self.preview_button.pack(side="left", padx=5)
        
        # Stop preview button
        self.stop_preview_button = ctk.CTkButton(
            self.preview_frame,
            text="⏹ Stop",
            font=ctk.CTkFont(size=FONT_MD),
            command=self._stop_voice_preview,
            width=100,
            height=BUTTON_HEIGHT,
            fg_color=COLOR_DANGER,
            hover_color=COLOR_DANGER_HOVER,
        )
        
        # Loading indicator
        self.preview_loading_label = ctk.CTkLabel(
            self.preview_frame,
            text="",
            font=ctk.CTkFont(size=FONT_SM),
            text_color=self.get_surface_status_text_color(),
        )
        self.preview_loading_label.pack(side="left", padx=10)
    
    def _create_voice_info_section(self, parent):
        """Create the voice info panel."""
        surface_theme = self.get_active_surface_theme()
        self.voice_info_frame = ctk.CTkFrame(
            parent,
            fg_color=surface_theme["pane_fg"],
            corner_radius=self.get_section_surface_style()["corner_radius"],
            border_width=1,
            border_color=surface_theme["border_color"],
        )
        self.voice_info_frame.pack(fill="x", pady=15)
        
        self.voice_info_title = ctk.CTkLabel(
            self.voice_info_frame,
            text="Selected Voice Information",
            font=ctk.CTkFont(size=FONT_MD, weight=FONT_WEIGHT_BOLD),
            text_color=surface_theme["text_primary"],
        )
        self.voice_info_title.pack(anchor="w", padx=10, pady=(10, 5))
        
        self.voice_info_grid = ctk.CTkFrame(self.voice_info_frame, fg_color="transparent")
        self.voice_info_grid.pack(fill="x", padx=10, pady=5)
        
        # Name
        ctk.CTkLabel(
            self.voice_info_grid,
            text="Name:",
            font=ctk.CTkFont(size=FONT_SM, weight=FONT_WEIGHT_BOLD),
            width=80,
            anchor="w"
        ).grid(row=0, column=0, sticky="w", pady=2)
        
        self.voice_info_name_value = ctk.CTkLabel(
            self.voice_info_grid,
            text="-",
            font=ctk.CTkFont(size=FONT_SM),
            anchor="w"
        )
        self.voice_info_name_value.grid(row=0, column=1, sticky="w", pady=2, padx=5)
        
        # Gender
        ctk.CTkLabel(
            self.voice_info_grid,
            text="Gender:",
            font=ctk.CTkFont(size=FONT_SM, weight=FONT_WEIGHT_BOLD),
            width=80,
            anchor="w"
        ).grid(row=1, column=0, sticky="w", pady=2)
        
        self.voice_info_gender_value = ctk.CTkLabel(
            self.voice_info_grid,
            text="-",
            font=ctk.CTkFont(size=FONT_SM),
            anchor="w"
        )
        self.voice_info_gender_value.grid(row=1, column=1, sticky="w", pady=2, padx=5)
        
        # Locale
        ctk.CTkLabel(
            self.voice_info_grid,
            text="Locale:",
            font=ctk.CTkFont(size=FONT_SM, weight=FONT_WEIGHT_BOLD),
            width=80,
            anchor="w"
        ).grid(row=2, column=0, sticky="w", pady=2)
        
        self.voice_info_locale_value = ctk.CTkLabel(
            self.voice_info_grid,
            text="-",
            font=ctk.CTkFont(size=FONT_SM),
            anchor="w"
        )
        self.voice_info_locale_value.grid(row=2, column=1, sticky="w", pady=2, padx=5)
        
        # Short Name
        ctk.CTkLabel(
            self.voice_info_grid,
            text="Short Name:",
            font=ctk.CTkFont(size=FONT_SM, weight=FONT_WEIGHT_BOLD),
            width=80,
            anchor="w"
        ).grid(row=3, column=0, sticky="w", pady=2)
        
        self.voice_info_short_value = ctk.CTkLabel(
            self.voice_info_grid,
            text="-",
            font=ctk.CTkFont(size=FONT_SM),
            anchor="w"
        )
        self.voice_info_short_value.grid(row=3, column=1, sticky="w", pady=2, padx=5)
    
    def _create_favorites_section(self, parent):
        """Create the favorites section."""
        surface_theme = self.get_active_surface_theme()
        self.favorites_frame = ctk.CTkScrollableFrame(
            parent,
            height=100,
            fg_color=surface_theme["pane_fg"],
        )
        self.favorites_frame.pack(fill="x", pady=5)
        prevent_scroll_propagation(self.favorites_frame)
        
        self.favorites_empty_label = ctk.CTkLabel(
            self.favorites_frame,
            text="No favorite voices yet. Click the star button to add favorites!",
            font=ctk.CTkFont(size=FONT_SM),
            text_color=surface_theme["text_secondary"],
        )
        self.favorites_empty_label.pack(pady=20)
    
    def _create_recent_section(self, parent):
        """Create the recent voices section."""
        surface_theme = self.get_active_surface_theme()
        self.recent_frame = ctk.CTkScrollableFrame(
            parent,
            height=80,
            fg_color=surface_theme["pane_fg"],
        )
        self.recent_frame.pack(fill="x", pady=5)
        prevent_scroll_propagation(self.recent_frame)
        
        self.recent_empty_label = ctk.CTkLabel(
            self.recent_frame,
            text="No recent voices yet.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color=surface_theme["text_secondary"],
        )
        self.recent_empty_label.pack(pady=20)
    
    def _create_parameter_sliders(self, parent):
        """Initialise parameter variables; the actual sliders live in Quick Controls."""
        # Keep IntVar members so voice preview and get_settings() still work.
        # Quick Controls (main window) saves these values to settings on every change,
        # so the vars below always reflect the most-recently saved values.
        self.rate_var = ctk.IntVar(value=self.settings.get("rate", 0))
        self.volume_var = ctk.IntVar(value=self.settings.get("volume", 100))
        self.pitch_var = ctk.IntVar(value=self.settings.get("pitch", 0))

        self.create_helper_text(
            text=(
                "🎚  Speed, Volume, Pitch, and Expressiveness sliders are available in the\n"
                "Quick Controls panel — click the  🎚 Controls  button in the main window."
            ),
            parent=parent,
            font_size=FONT_MD,
            justify="left",
        ).pack(anchor="w", pady=(10, 5), padx=5)

    def _apply_provider_slider_visibility(self, provider_key: str):
        """No-op: provider-specific sliders live in the Quick Controls panel."""

    def reload_for_provider(self, provider_key: str):
        """Reload voices for the selected provider and show loading feedback."""
        self._active_provider_key = provider_key
        self.voice_dropdown.configure(values=["Loading..."])
        self.voice_var.set("Loading...")
        self._load_voices(provider_override=provider_key)

    def _next_voice_load_request_id(self) -> int:
        """Return a monotonically increasing request id for async voice loads."""
        request_id = getattr(self, "_voice_load_request_id", 0) + 1
        self._voice_load_request_id = request_id
        return request_id

    def _is_latest_voice_load_request(self, request_id: int) -> bool:
        """Return True only for the most recently requested async voice load."""
        return (
            self._is_async_callback_target_alive()
            and getattr(self, "_voice_load_request_id", 0) == request_id
        )

    def _apply_voices_ui_if_latest(self, voices: List[Dict], request_id: int) -> None:
        """Ignore stale async voice loads once a newer request has started."""
        if not self._is_latest_voice_load_request(request_id):
            return
        self._apply_voices_ui(voices)

    
    def _load_voices(self, provider_override: Optional[str] = None):
        """Load available voices asynchronously."""
        request_id = self._next_voice_load_request_id()

        def do_load():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                voices = loop.run_until_complete(
                    self.tts_engine.get_available_voices(provider_override=provider_override)
                )
                self._schedule_on_ui_thread(
                    lambda: self._apply_voices_ui_if_latest(voices, request_id)
                )
            finally:
                loop.close()
        
        threading.Thread(target=do_load, daemon=True).start()
    
    def _apply_voices_ui(self, voices: List[Dict]):
        """Apply loaded voices to UI."""
        self._voices = voices
        self._voice_name_to_short_name.clear()
        friendly_names = []
        
        for v in voices:
            name = v.get("name", "")
            short = v.get("short_name", "")
            if name and short:
                self._voice_name_to_short_name[name] = short
                friendly_names.append(name)
        
        # Store mapping in settings manager
        self.settings.set_voices_mapping(self._voice_name_to_short_name)
        
        self._filtered_voices = list(self._voices)
        
        # Populate filter dropdowns
        unique_locales = sorted({v.get("locale") for v in self._voices if v.get("locale")})
        unique_langs = sorted({(v.get("locale") or "").split("-")[0] for v in self._voices if v.get("locale")})
        
        self.language_filter.configure(values=["All Languages"] + unique_langs)
        self.region_filter.configure(values=["All Regions"] + unique_locales)
        
        # Populate voice dropdown
        self.voice_dropdown.configure(values=friendly_names if friendly_names else ["No voices available"])
        
        # Select saved voice
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
        self._refresh_favorites_ui()
        self._refresh_recent_ui()
    
    def _update_voice_info(self):
        """Update voice info panel."""
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
        """Apply language/gender/region filters."""
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
    
    def _on_voice_search(self, event=None):
        """Handle voice search."""
        self._apply_voice_filters()
    
    def _clear_filters(self):
        """Clear all filters."""
        self.language_filter_var.set("All Languages")
        self.gender_filter_var.set("All")
        self.region_filter_var.set("All Regions")
        self.search_entry.delete(0, "end")
        self._apply_voice_filters()
    
    def _on_voice_selection_change(self, choice):
        """Handle voice selection change."""
        self._update_voice_info()
        self._update_favorite_button()
        
        short = self._voice_name_to_short_name.get(self.voice_var.get())
        if short:
            recents = list(self.settings.get("recent_voices", []))
            if short in recents:
                recents.remove(short)
            recents.insert(0, short)
            recents = recents[:20]
            self.settings.set("recent_voices", recents)
            self._refresh_recent_ui()
    
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
        """Update favorite button state."""
        short = self._voice_name_to_short_name.get(self.voice_var.get())
        favs = self.settings.get("favorite_voices", [])
        self.favorite_button.configure(text="★" if short and short in favs else "☆")
    
    def _display_name_for_short(self, short_name: str) -> Optional[str]:
        """Return display name for a voice short_name."""
        for v in self._voices:
            if v.get("short_name") == short_name:
                return v.get("name")
        return None
    
    def _refresh_favorites_ui(self):
        """Refresh favorites UI."""
        for c in self.favorites_frame.winfo_children():
            c.destroy()
        
        favs = self.settings.get("favorite_voices", [])
        if not favs:
            ctk.CTkLabel(
                self.favorites_frame,
                text="No favorite voices yet. Click the star button to add favorites!",
                font=ctk.CTkFont(size=FONT_SM),
                text_color=self.get_active_surface_theme()["text_secondary"],
            ).pack(pady=20)
            return
        
        for short in favs:
            display = self._display_name_for_short(short)
            if not display:
                continue
            
            ctk.CTkButton(
                self.favorites_frame,
                text=display,
                font=ctk.CTkFont(size=FONT_SM),
                command=lambda s=short: self._select_voice_by_short_name(s),
                width=200,
                height=BUTTON_HEIGHT,
                anchor="w",
                **self.get_subtle_button_style(),
            ).pack(anchor="w", pady=2, padx=2)
    
    def _refresh_recent_ui(self):
        """Refresh recent voices UI."""
        for c in self.recent_frame.winfo_children():
            c.destroy()
        
        recents = self.settings.get("recent_voices", [])
        if not recents:
            ctk.CTkLabel(
                self.recent_frame,
                text="No recent voices yet.",
                font=ctk.CTkFont(size=FONT_SM),
                text_color=self.get_active_surface_theme()["text_secondary"],
            ).pack(pady=20)
            return
        
        for short in recents:
            display = self._display_name_for_short(short)
            if not display:
                continue
            
            ctk.CTkButton(
                self.recent_frame,
                text=display,
                font=ctk.CTkFont(size=FONT_SM),
                command=lambda s=short: self._select_voice_by_short_name(s),
                width=200,
                height=BUTTON_HEIGHT,
                anchor="w",
                **self.get_subtle_button_style(),
            ).pack(anchor="w", pady=2, padx=2)
    
    def _select_voice_by_short_name(self, short_name: str):
        """Select a voice by its short_name."""
        display = self._display_name_for_short(short_name)
        if not display:
            return
        
        self.voice_var.set(display)
        self._update_voice_info()
        self._update_favorite_button()
        
        recents = list(self.settings.get("recent_voices", []))
        if short_name in recents:
            recents.remove(short_name)
        recents.insert(0, short_name)
        recents = recents[:20]
        self.settings.set("recent_voices", recents)
        self._refresh_recent_ui()
    
    def _validate_preview_text(self, text: str) -> bool:
        """Validate preview text."""
        if not text or not isinstance(text, str):
            return False
        
        param_patterns = [r'^rate\s*=', r'^volume\s*=', r'^pitch\s*=', r'^voice\s*=', r'^speed\s*=']
        for pattern in param_patterns:
            if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
                return False
        
        if not all(c.isprintable() or c.isspace() for c in text):
            return False
        
        stripped = text.strip()
        if len(stripped) < 1 or len(stripped) > 5000:
            return False
        
        return True
    
    def _reset_preview_text(self):
        """Reset preview text to default."""
        self.preview_text_var.set(DEFAULT_PREVIEW_TEXT)
    
    def _on_voice_preview(self):
        """Start voice preview."""
        if self._preview_playing:
            return
        
        short = self._voice_name_to_short_name.get(self.voice_var.get())
        if not short:
            self.preview_loading_label.configure(
                text=self.format_surface_status_text("Select a voice first.", "warning"),
                text_color=self.get_surface_status_text_color(),
            )
            return
        
        raw_text = str(self.preview_text_var.get()).strip()
        if not self._validate_preview_text(raw_text):
            raw_text = DEFAULT_PREVIEW_TEXT
            self.preview_text_var.set(DEFAULT_PREVIEW_TEXT)
        
        text = raw_text if raw_text else DEFAULT_PREVIEW_TEXT
        
        self._preview_stop_event.clear()
        self._preview_playing = True
        self._set_preview_ui_loading(True)

        # Show a hint for offline providers that may need to download a model
        provider_name = getattr(self, "_active_provider_key", self.settings.get("tts_provider", "edge"))
        if provider_name == "coqui":
            self.configure_surface_status_label(
                self.preview_loading_label,
                "Generating... (first use downloads ~1.8 GB)",
                "idle",
            )
        elif provider_name == "piper":
            self.configure_surface_status_label(
                self.preview_loading_label,
                "Generating... (first use may download a Piper voice model)",
                "idle",
            )
        else:
            self.configure_surface_status_label(self.preview_loading_label, "Generating...", "idle")
        
        def run():
            loop = None
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                audio_data, err = loop.run_until_complete(
                    self.tts_engine.generate_speech(
                        text, short,
                        self.rate_var.get(),
                        self.volume_var.get(),
                        self.pitch_var.get(),
                        self._preview_stop_event,
                        provider_override=provider_name,
                    )
                )
                
                if self._preview_stop_event.is_set():
                    self._schedule_on_ui_thread(lambda: self._preview_done(None))
                    return
                
                if err:
                    self._schedule_on_ui_thread(lambda: self._preview_done(err))
                    return
                
                if not audio_data:
                    self._schedule_on_ui_thread(lambda: self._preview_done("No audio generated."))
                    return
                
                self._schedule_on_ui_thread(lambda: self._preview_loading_playing())
                
                if self._preview_stop_event.is_set():
                    self._schedule_on_ui_thread(lambda: self._preview_done(None))
                    return
                
                enable_norm = self.settings.get("enable_normalization", True)
                norm_type = self.settings.get("normalization_type", "Peak")
                
                success = loop.run_until_complete(
                    self.audio_router.play_audio_to_device(
                        audio_data, 48000, None, enable_norm, norm_type
                    )
                )
                
                if not self._preview_stop_event.is_set():
                    if success:
                        self._schedule_on_ui_thread(lambda: self._preview_done(None))
                    else:
                        self._schedule_on_ui_thread(lambda: self._preview_done("Playback failed."))
            
            except Exception as e:
                logger.error("Preview exception: %s", e)
                self._schedule_on_ui_thread(lambda: self._preview_done(str(e)))
            finally:
                if loop:
                    loop.close()
        
        threading.Thread(target=run, daemon=True).start()
    
    def _set_preview_ui_loading(self, loading: bool):
        """Set preview UI loading state."""
        if loading:
            self.preview_button.pack_forget()
            self.stop_preview_button.pack(side="left", padx=5)
            self.preview_text_entry.configure(state="disabled")
        else:
            self.stop_preview_button.pack_forget()
            self.preview_button.pack(side="left", padx=5)
            self.preview_text_entry.configure(state="normal")
    
    def _preview_loading_playing(self):
        """Update loading label to Playing."""
        self.configure_surface_status_label(self.preview_loading_label, "Playing...", "success")
    
    def _preview_done(self, error: Optional[str]):
        """Handle preview completion."""
        self._preview_playing = False
        self._set_preview_ui_loading(False)
        
        if error:
            self.configure_surface_status_label(self.preview_loading_label, error, "error")
            self._schedule_on_ui_thread(
                lambda: self.configure_surface_status_label(self.preview_loading_label, "", "idle"),
                delay_ms=3000,
            )
        else:
            self.configure_surface_status_label(self.preview_loading_label, "", "idle")
    
    def _stop_voice_preview(self):
        """Stop voice preview."""
        self._preview_stop_event.set()
        if self.audio_router:
            self.audio_router.stop_playback()
    
    def _on_rate_change(self, value):
        """No-op: sliders moved to Quick Controls panel."""

    def _on_volume_change(self, value):
        """No-op: sliders moved to Quick Controls panel."""

    def _on_pitch_change(self, value):
        """No-op: sliders moved to Quick Controls panel."""

    def _on_noise_scale_change(self, value):
        """No-op: sliders moved to Quick Controls panel."""

    def _on_noise_w_scale_change(self, value):
        """No-op: sliders moved to Quick Controls panel."""
    
    def get_settings(self) -> Dict[str, Any]:
        """Get current settings from the tab UI."""
        settings = {
            "rate": self.rate_var.get(),
            "volume": self.volume_var.get(),
            "pitch": self.pitch_var.get(),
            "voice_preview_text": self.preview_text_var.get(),
            "voice_filter_language": self.language_filter_var.get(),
            "voice_filter_gender": self.gender_filter_var.get(),
            "voice_filter_region": self.region_filter_var.get(),
        }
        
        short = self._voice_name_to_short_name.get(self.voice_var.get())
        if short:
            settings["voice"] = short
        
        return settings
    
    def validate(self) -> List[str]:
        """Validate the tab's settings."""
        errors = []
        
        # Validate rate
        rate = self.rate_var.get()
        if not (-100 <= rate <= 100):
            errors.append(f"Rate out of range (-100 to 100): {rate}")
        
        # Validate volume
        volume = self.volume_var.get()
        if not (0 <= volume <= 100):
            errors.append(f"Volume out of range (0 to 100): {volume}")
        
        # Validate pitch
        pitch = self.pitch_var.get()
        if not (-100 <= pitch <= 100):
            errors.append(f"Pitch out of range (-100 to 100): {pitch}")
        
        return errors
