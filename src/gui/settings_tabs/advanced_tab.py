"""
Advanced Tab
Settings for cache management, performance, and experimental features.
"""
import logging
import customtkinter as ctk
from typing import Any, Callable, Optional, List, Dict

from .base_tab import BaseTab
from ..theme_constants import (
    FONT_XS, FONT_SM, FONT_MD, FONT_LG, FONT_XL, FONT_WEIGHT_BOLD,
    BUTTON_HEIGHT_SM, BUTTON_WIDTH_DEFAULT,
    COLOR_DANGER, COLOR_DANGER_HOVER,
)

logger = logging.getLogger(__name__)


class AdvancedTab(BaseTab):
    """Tab for advanced settings."""
    
    def _create_content(self):
        """Create the advanced tab content."""
        self.scroll = ctk.CTkScrollableFrame(self.tab)
        self.scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Main title
        ctk.CTkLabel(
            self.scroll,
            text="Advanced Settings",
            font=ctk.CTkFont(size=FONT_XL, weight=FONT_WEIGHT_BOLD)
        ).pack(anchor="w", pady=(10, 5))
        
        advanced_desc_label = ctk.CTkLabel(
            self.scroll,
            text="Configure cache, performance, and experimental features. Changes take effect after saving.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550
        )
        advanced_desc_label.pack(anchor="w", pady=(0, 15))
        self.add_wraplength_label(advanced_desc_label)
        
        # Cache Management Section
        self._create_cache_section()
        
        # Performance Settings Section
        self._create_performance_section()
        
        # Experimental Features Section
        self._create_experimental_section()
    
    def _create_cache_section(self):
        """Create the cache management section."""
        ctk.CTkLabel(
            self.scroll,
            text="Cache Management",
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD)
        ).pack(anchor="w", pady=(10, 5))
        
        cache_desc_label = ctk.CTkLabel(
            self.scroll,
            text="Audio cache stores generated speech to improve response times for repeated phrases.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550
        )
        cache_desc_label.pack(anchor="w", pady=(0, 10))
        self.add_wraplength_label(cache_desc_label)
        
        # Cache statistics display
        self.cache_stats_text = ctk.CTkTextbox(
            self.scroll,
            font=ctk.CTkFont(size=FONT_SM),
            height=120,
            wrap="word",
            state="disabled"
        )
        self.cache_stats_text.pack(fill="x", pady=5)
        
        # Cache buttons frame
        cache_buttons_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
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
            self.scroll,
            text="Enable audio cache",
            variable=self.cache_enabled_var,
            font=ctk.CTkFont(size=FONT_MD)
        )
        self.cache_enabled_check.pack(anchor="w", pady=5)
        
        # Max cache size slider
        ctk.CTkLabel(
            self.scroll,
            text="Maximum Cache Size:",
            font=ctk.CTkFont(size=FONT_MD)
        ).pack(anchor="w", pady=(10, 5))
        
        cache_size_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
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
        
        self.create_separator(self.scroll).pack(fill="x", pady=15)
    
    def _create_performance_section(self):
        """Create the performance settings section."""
        ctk.CTkLabel(
            self.scroll,
            text="Performance Settings",
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD)
        ).pack(anchor="w", pady=(10, 5))
        
        # Processing profile dropdown
        ctk.CTkLabel(
            self.scroll,
            text="Processing Profile:",
            font=ctk.CTkFont(size=FONT_MD)
        ).pack(anchor="w", pady=(10, 5))
        
        self.processing_profile_var = ctk.StringVar(value=self.settings.get("processing_profile", "balanced"))
        self.processing_profile_dropdown = ctk.CTkComboBox(
            self.scroll,
            variable=self.processing_profile_var,
            values=["fast_preview", "balanced", "high_quality"],
            font=ctk.CTkFont(size=FONT_SM),
            state="readonly",
            width=200
        )
        self.processing_profile_dropdown.pack(anchor="w", pady=5)
        
        ctk.CTkLabel(
            self.scroll,
            text="Fast Preview: No resampling, no stereo enhancement | Balanced: 48 kHz resampling, moderate stereo enhancement | High Quality: 48 kHz resampling, maximum stereo enhancement",
            font=ctk.CTkFont(size=FONT_XS),
            text_color="gray"
        ).pack(anchor="w", pady=(0, 10))
        
        # Text cache size
        ctk.CTkLabel(
            self.scroll,
            text="Text Cache Size:",
            font=ctk.CTkFont(size=FONT_MD)
        ).pack(anchor="w", pady=(10, 5))
        
        text_cache_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
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
        
        self.create_separator(self.scroll).pack(fill="x", pady=15)
    
    def _create_experimental_section(self):
        """Create the experimental features section."""
        ctk.CTkLabel(
            self.scroll,
            text="Experimental Features",
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD)
        ).pack(anchor="w", pady=(10, 5))
        
        experimental_warning_label = ctk.CTkLabel(
            self.scroll,
            text="⚠️ Experimental features may be unstable or change in future versions.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="orange",
            wraplength=550
        )
        experimental_warning_label.pack(anchor="w", pady=(0, 10))
        self.add_wraplength_label(experimental_warning_label)
        
        # Streaming playback checkbox
        self.streaming_playback_var = ctk.BooleanVar(value=self.settings.get("enable_streaming_playback", False))
        self.streaming_playback_check = ctk.CTkCheckBox(
            self.scroll,
            text="Enable Streaming Playback (Experimental)",
            variable=self.streaming_playback_var,
            font=ctk.CTkFont(size=FONT_MD)
        )
        self.streaming_playback_check.pack(anchor="w", pady=5)
        
        streaming_desc_label = ctk.CTkLabel(
            self.scroll,
            text="Starts playing audio as soon as the first chunks arrive from Edge TTS, reducing the delay before you hear speech. Best for longer text. Note: Audio normalization and viseme sync use estimated timing in streaming mode.",
            font=ctk.CTkFont(size=FONT_XS),
            text_color="gray",
            wraplength=550
        )
        streaming_desc_label.pack(anchor="w", pady=(0, 10))
        self.add_wraplength_label(streaming_desc_label)
    
    def _on_clear_cache(self):
        """Clear the audio cache with user confirmation."""
        # This will be handled by the parent settings window
        if self.on_change:
            self.on_change("clear_cache")
    
    def _on_refresh_cache_stats(self):
        """Refresh and display cache statistics."""
        self.cache_stats_text.configure(state="normal")
        self.cache_stats_text.delete("1.0", "end")
        
        try:
            if self.tts_engine:
                stats = self.tts_engine.get_audio_cache_statistics()
                
                lines = [
                    f"Cache Enabled: {'Yes' if stats.get('enabled', False) else 'No'}",
                    f"Cached Entries: {stats.get('entries', 0)}",
                    f"Current Size: {stats.get('size_mb', 0):.2f} MB / {self.cache_max_size_var.get()} MB",
                ]
                
                if 'hit_rate' in stats:
                    lines.append(f"Hit Rate: {stats['hit_rate']:.1f}%")
                
                if 'total_saved_time' in stats:
                    lines.append(f"Time Saved: {stats['total_saved_time']:.1f}s")
                
                if 'cache_dir' in stats:
                    lines.append(f"Cache Path: {stats['cache_dir']}")
                
                self.cache_stats_text.insert("1.0", "\n".join(lines))
            else:
                self.cache_stats_text.insert("1.0", "TTS engine not available.")
        except Exception as e:
            logger.error(f"Error getting cache statistics: %s", e)
            self.cache_stats_text.insert("1.0", f"Error retrieving cache statistics: {e}")
        
        self.cache_stats_text.configure(state="disabled")
    
    def _on_cache_size_change(self, value):
        """Update cache size label when slider changes."""
        self.cache_size_value_label.configure(text=f"{int(value)} MB")
    
    def get_settings(self) -> Dict[str, Any]:
        """Get current settings from the tab UI."""
        # Validate text cache size
        try:
            text_cache_size = int(self.text_cache_size_var.get())
            if 100 <= text_cache_size <= 10000:
                text_cache_size_value = text_cache_size
            else:
                text_cache_size_value = 1000
        except ValueError:
            text_cache_size_value = 1000
        
        return {
            "audio_cache_enabled": self.cache_enabled_var.get(),
            "audio_cache_max_size_mb": self.cache_max_size_var.get(),
            "processing_profile": self.processing_profile_var.get(),
            "text_cache_size": text_cache_size_value,
            "enable_streaming_playback": self.streaming_playback_var.get(),
        }
    
    def validate(self) -> List[str]:
        """Validate the tab's settings."""
        errors = []
        
        # Validate text cache size
        try:
            text_cache_size = int(self.text_cache_size_var.get())
            if not (100 <= text_cache_size <= 10000):
                errors.append(f"Text cache size out of range (100-10000): {text_cache_size}")
        except ValueError:
            errors.append(f"Invalid text cache size: {self.text_cache_size_var.get()}")
        
        # Validate processing profile
        if self.processing_profile_var.get() not in ["fast_preview", "balanced", "high_quality"]:
            errors.append(f"Invalid processing profile: {self.processing_profile_var.get()}")
        
        return errors