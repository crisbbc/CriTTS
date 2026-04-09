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
    BUTTON_HEIGHT, BUTTON_WIDTH_DEFAULT,
    COLOR_DANGER, COLOR_DANGER_HOVER,
    SPACING_MD,
)

logger = logging.getLogger(__name__)


class AdvancedTab(BaseTab):
    """Tab for advanced settings."""

    def _load_data(self):
        """Populate dynamic cache data during settings window refreshes."""
        self._on_refresh_cache_stats()
    
    def _create_content(self):
        """Create the advanced tab content."""
        self.setup_layout()

        surface_theme = self.get_active_surface_theme()
        
        # Main title
        ctk.CTkLabel(
            self.scroll,
            text="Advanced Settings",
            font=ctk.CTkFont(size=FONT_XL, weight=FONT_WEIGHT_BOLD)
        ).pack(anchor="w", pady=(10, 5))
        
        advanced_desc_label = self.create_helper_text(
            text="Configure cache, performance, and experimental features. Changes take effect after saving.",
            parent=self.scroll,
        )
        advanced_desc_label.pack(anchor="w", pady=(0, SPACING_MD))
        
        # Cache Management Section
        cache_section, cache_content = self.create_section_surface(
            "Cache Management",
            parent=self.scroll,
            description="Audio cache stores generated speech to improve response times for repeated phrases.",
        )
        cache_section.pack(fill="x", pady=(0, SPACING_MD))
        self._create_cache_section(cache_content, surface_theme)
        
        # Network Privacy Section
        privacy_section, privacy_content = self.create_section_surface(
            "Network Privacy",
            parent=self.scroll,
            description="Route Text-to-Speech requests through a proxy to obfuscate your IP address from Microsoft servers.",
        )
        privacy_section.pack(fill="x", pady=(0, SPACING_MD))
        self._create_network_privacy_section(privacy_content)

        # Performance Settings Section
        performance_section, performance_content = self.create_section_surface(
            "Performance Settings",
            parent=self.scroll,
        )
        performance_section.pack(fill="x", pady=(0, SPACING_MD))
        self._create_performance_section(performance_content)
        
        # Experimental Features Section
        experimental_section, experimental_content = self.create_section_surface(
            "Experimental Features",
            parent=self.scroll,
        )
        experimental_section.pack(fill="x", pady=(0, SPACING_MD))
        self._create_experimental_section(experimental_content)
    
    def _create_network_privacy_section(self, parent):
        """Create the network privacy settings section."""
        # Enable proxy checkbox
        self.proxy_enabled_var = ctk.BooleanVar(value=self.settings.get("proxy_enabled", False))
        self.proxy_enabled_check = ctk.CTkCheckBox(
            parent,
            text="Enable Proxy for TTS requests",
            variable=self.proxy_enabled_var,
            font=ctk.CTkFont(size=FONT_MD),
            command=self._on_proxy_toggle
        )
        self.proxy_enabled_check.pack(anchor="w", pady=5)

        # Proxy settings frame (to be toggled)
        self.proxy_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.proxy_frame.pack(fill="x", pady=5)

        # Proxy Type
        type_frame = ctk.CTkFrame(self.proxy_frame, fg_color="transparent")
        type_frame.pack(fill="x", pady=2)
        ctk.CTkLabel(
            type_frame,
            text="Proxy Type:",
            font=ctk.CTkFont(size=FONT_MD),
            width=120,
            anchor="w"
        ).pack(side="left")

        self.proxy_type_var = ctk.StringVar(value=self.settings.get("proxy_type", "http"))
        self.proxy_type_dropdown = ctk.CTkComboBox(
            type_frame,
            variable=self.proxy_type_var,
            values=["http", "socks4", "socks5"],
            font=ctk.CTkFont(size=FONT_SM),
            state="readonly",
            width=150
        )
        self.proxy_type_dropdown.pack(side="left", padx=5)

        # Proxy Server
        server_frame = ctk.CTkFrame(self.proxy_frame, fg_color="transparent")
        server_frame.pack(fill="x", pady=2)
        ctk.CTkLabel(
            server_frame,
            text="Server (IP:Port):",
            font=ctk.CTkFont(size=FONT_MD),
            width=120,
            anchor="w"
        ).pack(side="left")

        self.proxy_server_var = ctk.StringVar(value=self.settings.get("proxy_server", ""))
        self.proxy_server_entry = ctk.CTkEntry(
            server_frame,
            textvariable=self.proxy_server_var,
            font=ctk.CTkFont(size=FONT_MD),
            placeholder_text="e.g. 127.0.0.1:8080",
            width=250
        )
        self.proxy_server_entry.pack(side="left", padx=5)

        # Proxy Username
        user_frame = ctk.CTkFrame(self.proxy_frame, fg_color="transparent")
        user_frame.pack(fill="x", pady=2)
        ctk.CTkLabel(
            user_frame,
            text="Username (opt):",
            font=ctk.CTkFont(size=FONT_MD),
            width=120,
            anchor="w"
        ).pack(side="left")

        self.proxy_username_var = ctk.StringVar(value=self.settings.get("proxy_username", ""))
        self.proxy_username_entry = ctk.CTkEntry(
            user_frame,
            textvariable=self.proxy_username_var,
            font=ctk.CTkFont(size=FONT_MD),
            placeholder_text="Optional",
            width=250
        )
        self.proxy_username_entry.pack(side="left", padx=5)

        # Proxy Password
        pass_frame = ctk.CTkFrame(self.proxy_frame, fg_color="transparent")
        pass_frame.pack(fill="x", pady=2)
        ctk.CTkLabel(
            pass_frame,
            text="Password (opt):",
            font=ctk.CTkFont(size=FONT_MD),
            width=120,
            anchor="w"
        ).pack(side="left")

        self.proxy_password_var = ctk.StringVar(value=self.settings.get("proxy_password", ""))
        self.proxy_password_entry = ctk.CTkEntry(
            pass_frame,
            textvariable=self.proxy_password_var,
            font=ctk.CTkFont(size=FONT_MD),
            show="*",
            placeholder_text="Optional",
            width=250
        )
        self.proxy_password_entry.pack(side="left", padx=5)

        # Initial state update
        self._on_proxy_toggle()

    def _on_proxy_toggle(self):
        """Enable or disable proxy input fields based on checkbox."""
        state = "normal" if self.proxy_enabled_var.get() else "disabled"
        self.proxy_type_dropdown.configure(state="readonly" if self.proxy_enabled_var.get() else "disabled")
        self.proxy_server_entry.configure(state=state)
        self.proxy_username_entry.configure(state=state)
        self.proxy_password_entry.configure(state=state)

    def _create_cache_section(self, parent, surface_theme):
        """Create the cache management section."""
        # Cache statistics display
        self.cache_stats_text = ctk.CTkTextbox(
            parent,
            font=ctk.CTkFont(size=FONT_SM),
            height=120,
            wrap="word",
            state="disabled",
            fg_color=surface_theme["pane_fg"],
            text_color=surface_theme["text_primary"],
        )
        self.cache_stats_text.pack(fill="x", pady=5)
        
        # Cache buttons frame
        cache_buttons_frame = ctk.CTkFrame(parent, fg_color="transparent")
        cache_buttons_frame.pack(fill="x", pady=10)
        
        self.clear_cache_button = ctk.CTkButton(
            cache_buttons_frame,
            text="Clear Audio Cache",
            font=ctk.CTkFont(size=FONT_SM),
            command=self._on_clear_cache,
            width=BUTTON_WIDTH_DEFAULT,
            height=BUTTON_HEIGHT,
            fg_color=COLOR_DANGER,
            hover_color=COLOR_DANGER_HOVER
        )
        self.clear_cache_button.pack(side="left", padx=5)
        
        self.refresh_stats_button = ctk.CTkButton(
            cache_buttons_frame,
            text="Refresh Statistics",
            font=ctk.CTkFont(size=FONT_SM),
            command=self._on_refresh_cache_stats,
            width=BUTTON_WIDTH_DEFAULT,
            height=BUTTON_HEIGHT
        )
        self.refresh_stats_button.pack(side="left", padx=5)
        
        # Cache enabled checkbox
        self.cache_enabled_var = ctk.BooleanVar(value=self.settings.get("audio_cache_enabled", True))
        self.cache_enabled_check = ctk.CTkCheckBox(
            parent,
            text="Enable audio cache",
            variable=self.cache_enabled_var,
            font=ctk.CTkFont(size=FONT_MD)
        )
        self.cache_enabled_check.pack(anchor="w", pady=5)
        
        # Max cache size slider
        ctk.CTkLabel(
            parent,
            text="Maximum Cache Size:",
            font=ctk.CTkFont(size=FONT_MD)
        ).pack(anchor="w", pady=(10, 5))
        
        cache_size_frame = ctk.CTkFrame(parent, fg_color="transparent")
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
        

    def _create_performance_section(self, parent):
        """Create the performance settings section."""
        # Processing profile dropdown
        ctk.CTkLabel(
            parent,
            text="Processing Profile:",
            font=ctk.CTkFont(size=FONT_MD)
        ).pack(anchor="w", pady=(10, 5))
        
        self.processing_profile_var = ctk.StringVar(value=self.settings.get("processing_profile", "balanced"))
        self.processing_profile_dropdown = ctk.CTkComboBox(
            parent,
            variable=self.processing_profile_var,
            values=["fast_preview", "balanced", "high_quality"],
            font=ctk.CTkFont(size=FONT_SM),
            state="readonly",
            width=200
        )
        self.processing_profile_dropdown.pack(anchor="w", pady=5)
        
        self.create_helper_text(
            text="Fast Preview: No resampling, no stereo enhancement | Balanced: 48 kHz resampling with subtle speech-friendly stereo | High Quality: 48 kHz resampling with gentle stereo enhancement",
            parent=parent,
            font_size=FONT_XS,
        ).pack(anchor="w", pady=(0, 10))
        
        # Text cache size
        ctk.CTkLabel(
            parent,
            text="Text Cache Size:",
            font=ctk.CTkFont(size=FONT_MD)
        ).pack(anchor="w", pady=(10, 5))
        
        text_cache_frame = ctk.CTkFrame(parent, fg_color="transparent")
        text_cache_frame.pack(fill="x", pady=5)
        
        self.text_cache_size_var = ctk.StringVar(value=str(self.settings.get("text_cache_size", 1000)))
        self.text_cache_entry = ctk.CTkEntry(
            text_cache_frame,
            textvariable=self.text_cache_size_var,
            font=ctk.CTkFont(size=FONT_MD),
            width=100
        )
        self.text_cache_entry.pack(side="left", padx=5)
        
        self.create_helper_text(
            text="Number of processed text entries to cache (100-10000)",
            parent=text_cache_frame,
        ).pack(side="left", padx=5)

    def _create_experimental_section(self, parent):
        """Create the experimental features section."""
        experimental_warning_label = self.create_helper_text(
            text="⚠ Experimental features may be unstable or change in future versions.",
            parent=parent,
        )
        experimental_warning_label.pack(anchor="w", pady=(0, 10))
        
        # Streaming playback checkbox
        self.streaming_playback_var = ctk.BooleanVar(value=self.settings.get("enable_streaming_playback", False))
        self.streaming_playback_check = ctk.CTkCheckBox(
            parent,
            text="Enable Streaming Playback (Experimental)",
            variable=self.streaming_playback_var,
            font=ctk.CTkFont(size=FONT_MD)
        )
        self.streaming_playback_check.pack(anchor="w", pady=5)
        
        streaming_desc_label = self.create_helper_text(
            text="Starts playing audio as soon as the first chunks arrive from Edge TTS, reducing the delay before you hear speech. Best for longer text. Note: Audio normalization and viseme sync use estimated timing in streaming mode.",
            parent=parent,
            font_size=FONT_XS,
        )
        streaming_desc_label.pack(anchor="w", pady=(0, 10))
    
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
            "proxy_enabled": self.proxy_enabled_var.get(),
            "proxy_type": self.proxy_type_var.get(),
            "proxy_server": self.proxy_server_var.get().strip(),
            "proxy_username": self.proxy_username_var.get().strip(),
            "proxy_password": self.proxy_password_var.get(),
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

        # Validate proxy settings
        if self.proxy_enabled_var.get():
            server = self.proxy_server_var.get().strip()
            if not server:
                errors.append("Proxy server cannot be empty when proxy is enabled.")
            elif ":" not in server:
                errors.append("Proxy server must include a port (e.g. 127.0.0.1:8080).")
            else:
                # Basic port validation
                parts = server.rsplit(":", 1)
                if len(parts) == 2:
                    try:
                        port = int(parts[1])
                        if not (1 <= port <= 65535):
                            errors.append("Proxy port must be between 1 and 65535.")
                    except ValueError:
                        errors.append("Proxy port must be a valid number.")
        
        return errors
