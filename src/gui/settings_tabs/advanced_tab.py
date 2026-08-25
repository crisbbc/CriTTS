"""
Advanced Tab
Settings for cache management, performance, and experimental features.
"""
import asyncio
import logging
import threading
import customtkinter as ctk
from typing import Any, Callable, Optional, List, Dict

from .base_tab import BaseTab
from ..theme_constants import (
    FONT_XS, FONT_SM, FONT_MD, FONT_WEIGHT_BOLD,
    BUTTON_HEIGHT, BUTTON_WIDTH_DEFAULT,
    COLOR_DANGER, COLOR_DANGER_HOVER,
    SPACING_MD,
    SPACING_BASE,
    SPACING_SM,
)

logger = logging.getLogger(__name__)


class AdvancedTab(BaseTab):
    """Tab for advanced settings."""

    def __init__(
        self,
        tab_widget: ctk.CTkFrame,
        settings_manager: Any,
        tts_engine: Any = None,
        audio_router: Any = None,
        on_change: Optional[Callable] = None,
        parent_window: Optional[ctk.CTk] = None,
    ):
        """Initialize the advanced tab."""
        self.parent_window = parent_window
        self._async_callbacks_active = True
        self._pregenerating = False
        self._pregenerate_stop_event = threading.Event()
        super().__init__(tab_widget, settings_manager, tts_engine, audio_router, on_change)

    def invalidate_async_callbacks(self) -> None:
        """Stop background pre-generation before the tab is destroyed or rebuilt."""
        self._async_callbacks_active = False
        self._pregenerate_stop_event.set()

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
        except Exception:
            return False

    def _load_data(self):
        """Populate dynamic cache data during settings window refreshes."""
        self._on_refresh_cache_stats()
    
    def _create_content(self):
        """Create the advanced tab content."""
        self.setup_layout()

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
        self._create_cache_section(cache_content)
        
        # Phrase Pre-generation Section
        pregeneration_section, pregeneration_content = self.create_section_surface(
            "Phrase Pre-generation",
            parent=self.scroll,
            description="Pre-generate audio for your most-used phrases so they play instantly instead of synthesizing on demand.",
        )
        pregeneration_section.pack(fill="x", pady=(0, SPACING_MD))
        self._create_pregeneration_section(pregeneration_content)
        
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
        self.proxy_enabled_check.pack(anchor="w", pady=SPACING_BASE)

        # Proxy settings frame (to be toggled)
        self.proxy_frame = self.create_inline_frame(parent)

        # Proxy Type
        type_frame = self.create_inline_frame(self.proxy_frame, pady=SPACING_BASE)
        self.create_setting_label("Proxy Type:", type_frame, width=120).pack(side="left")

        self.proxy_type_var = ctk.StringVar(value=self.settings.get("proxy_type", "http"))
        self.proxy_type_dropdown = ctk.CTkComboBox(
            type_frame,
            variable=self.proxy_type_var,
            values=["http", "socks4", "socks5"],
            font=ctk.CTkFont(size=FONT_SM),
            state="readonly",
            width=150
        )
        self.proxy_type_dropdown.pack(side="left", padx=SPACING_BASE)

        # Proxy Server
        server_frame = self.create_inline_frame(self.proxy_frame, pady=SPACING_BASE)
        self.create_setting_label("Server (IP:Port):", server_frame, width=120).pack(side="left")

        self.proxy_server_var = ctk.StringVar(value=self.settings.get("proxy_server", ""))
        self.proxy_server_entry = ctk.CTkEntry(
            server_frame,
            textvariable=self.proxy_server_var,
            font=ctk.CTkFont(size=FONT_MD),
            placeholder_text="e.g. 127.0.0.1:8080",
            width=250
        )
        self.proxy_server_entry.pack(side="left", padx=SPACING_BASE)

        # Proxy Username
        user_frame = self.create_inline_frame(self.proxy_frame, pady=SPACING_BASE)
        self.create_setting_label("Username (opt):", user_frame, width=120).pack(side="left")

        self.proxy_username_var = ctk.StringVar(value=self.settings.get("proxy_username", ""))
        self.proxy_username_entry = ctk.CTkEntry(
            user_frame,
            textvariable=self.proxy_username_var,
            font=ctk.CTkFont(size=FONT_MD),
            placeholder_text="Optional",
            width=250
        )
        self.proxy_username_entry.pack(side="left", padx=SPACING_BASE)

        # Proxy Password
        pass_frame = self.create_inline_frame(self.proxy_frame, pady=SPACING_BASE)
        self.create_setting_label("Password (opt):", pass_frame, width=120).pack(side="left")

        self.proxy_password_var = ctk.StringVar(value=self.settings.get("proxy_password", ""))
        self.proxy_password_entry = ctk.CTkEntry(
            pass_frame,
            textvariable=self.proxy_password_var,
            font=ctk.CTkFont(size=FONT_MD),
            show="*",
            placeholder_text="Optional",
            width=250
        )
        self.proxy_password_entry.pack(side="left", padx=SPACING_BASE)

        # Initial state update
        self._on_proxy_toggle()

    def _on_proxy_toggle(self):
        """Enable or disable proxy input fields based on checkbox."""
        state = "normal" if self.proxy_enabled_var.get() else "disabled"
        self.proxy_type_dropdown.configure(state="readonly" if self.proxy_enabled_var.get() else "disabled")
        self.proxy_server_entry.configure(state=state)
        self.proxy_username_entry.configure(state=state)
        self.proxy_password_entry.configure(state=state)

    def _create_cache_section(self, parent, surface_theme=None):
        """Create the cache management section."""
        # Cache statistics display
        self.cache_stats_text = ctk.CTkTextbox(
            parent,
            font=ctk.CTkFont(size=FONT_SM),
            height=120,
            wrap="word",
            state="disabled",
            **self.get_input_surface_style(),
        )
        self.cache_stats_text.pack(fill="x", pady=SPACING_BASE)
        
        # Cache buttons frame
        cache_buttons_frame = self.create_inline_frame(parent, pady=SPACING_SM)
        
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
        self.clear_cache_button.pack(side="left", padx=SPACING_BASE)
        
        self.refresh_stats_button = ctk.CTkButton(
            cache_buttons_frame,
            text="Refresh Statistics",
            font=ctk.CTkFont(size=FONT_SM),
            command=self._on_refresh_cache_stats,
            width=BUTTON_WIDTH_DEFAULT,
            height=BUTTON_HEIGHT
        )
        self.refresh_stats_button.pack(side="left", padx=SPACING_BASE)
        
        # Cache enabled checkbox
        self.cache_enabled_var = ctk.BooleanVar(value=self.settings.get("audio_cache_enabled", True))
        self.cache_enabled_check = ctk.CTkCheckBox(
            parent,
            text="Enable audio cache",
            variable=self.cache_enabled_var,
            font=ctk.CTkFont(size=FONT_MD)
        )
        self.cache_enabled_check.pack(anchor="w", pady=SPACING_BASE)
        
        # Max cache size slider
        self.create_setting_label("Maximum Cache Size:", parent).pack(anchor="w", pady=(SPACING_SM, SPACING_BASE))
        
        cache_size_frame = self.create_inline_frame(parent)
        
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
        self.cache_size_slider.pack(side="left", fill="x", expand=True, padx=SPACING_BASE)
        
        self.cache_size_value_label = ctk.CTkLabel(
            cache_size_frame,
            text=f"{self.cache_max_size_var.get()} MB",
            font=ctk.CTkFont(size=FONT_MD),
            width=80
        )
        self.cache_size_value_label.pack(side="right", padx=SPACING_BASE)

    def _create_pregeneration_section(self, parent):
        """Create the phrase pre-generation section."""
        enabled = bool(self.settings.get("pregenerate_phrases_enabled", True))
        self.pregenerate_enabled_var = ctk.BooleanVar(value=enabled)
        self.pregenerate_enabled_check = ctk.CTkCheckBox(
            parent,
            text="Enable phrase pre-generation",
            variable=self.pregenerate_enabled_var,
            font=ctk.CTkFont(size=FONT_MD),
            command=self._on_pregenerate_enabled_toggle,
        )
        self.pregenerate_enabled_check.pack(anchor="w", pady=SPACING_BASE)

        # Minimum uses slider
        self.create_setting_label("Minimum Uses:", parent).pack(anchor="w", pady=(SPACING_SM, SPACING_BASE))
        min_uses_frame = self.create_inline_frame(parent)
        self.pregenerate_min_uses_var = ctk.IntVar(
            value=int(self.settings.get("pregenerate_min_uses", 3))
        )
        self.pregenerate_min_uses_slider = ctk.CTkSlider(
            min_uses_frame,
            from_=1,
            to=50,
            number_of_steps=49,
            variable=self.pregenerate_min_uses_var,
            command=self._on_min_uses_change,
            width=400,
        )
        self.pregenerate_min_uses_slider.pack(side="left", fill="x", expand=True, padx=SPACING_BASE)
        self.pregenerate_min_uses_value_label = ctk.CTkLabel(
            min_uses_frame,
            text=f"{self.pregenerate_min_uses_var.get()}",
            font=ctk.CTkFont(size=FONT_MD),
            width=80,
        )
        self.pregenerate_min_uses_value_label.pack(side="right", padx=SPACING_BASE)

        # Max phrases slider
        self.create_setting_label("Max Phrases:", parent).pack(anchor="w", pady=(SPACING_SM, SPACING_BASE))
        max_phrases_frame = self.create_inline_frame(parent)
        self.pregenerate_max_phrases_var = ctk.IntVar(
            value=int(self.settings.get("pregenerate_max_phrases", 20))
        )
        self.pregenerate_max_phrases_slider = ctk.CTkSlider(
            max_phrases_frame,
            from_=1,
            to=100,
            number_of_steps=99,
            variable=self.pregenerate_max_phrases_var,
            command=self._on_max_phrases_change,
            width=400,
        )
        self.pregenerate_max_phrases_slider.pack(side="left", fill="x", expand=True, padx=SPACING_BASE)
        self.pregenerate_max_phrases_value_label = ctk.CTkLabel(
            max_phrases_frame,
            text=f"{self.pregenerate_max_phrases_var.get()}",
            font=ctk.CTkFont(size=FONT_MD),
            width=80,
        )
        self.pregenerate_max_phrases_value_label.pack(side="right", padx=SPACING_BASE)

        # Action button + status
        pregen_buttons_frame = self.create_inline_frame(parent, pady=SPACING_SM)
        self.pregenerate_button = ctk.CTkButton(
            pregen_buttons_frame,
            text="Pre-generate Common Phrases",
            font=ctk.CTkFont(size=FONT_SM),
            command=self._on_pregenerate,
            width=BUTTON_WIDTH_DEFAULT,
            height=BUTTON_HEIGHT,
        )
        self.pregenerate_button.pack(side="left", padx=SPACING_BASE)
        self.pregenerate_status_label = self.create_surface_status_label(
            pregen_buttons_frame,
            wraplength=220,
        )
        self.pregenerate_status_label.pack(side="left", padx=SPACING_SM)

        self.create_helper_text(
            text=(
                "Common phrases are tracked automatically as you speak. Pre-generating "
                "them ahead of time makes repeated lines play instantly."
            ),
            parent=parent,
            font_size=FONT_XS,
        ).pack(anchor="w", pady=(0, SPACING_SM))

        if not enabled:
            self.pregenerate_button.configure(state="disabled")

    def _on_pregenerate_enabled_toggle(self):
        """Disable the pre-generate button when pre-generation is turned off."""
        state = "normal" if self.pregenerate_enabled_var.get() else "disabled"
        self.pregenerate_button.configure(state=state)

    def _on_min_uses_change(self, value):
        """Update the minimum-uses label when the slider changes."""
        self.pregenerate_min_uses_value_label.configure(text=str(int(value)))

    def _on_max_phrases_change(self, value):
        """Update the max-phrases label when the slider changes."""
        self.pregenerate_max_phrases_value_label.configure(text=str(int(value)))

    def _on_pregenerate(self):
        """Start background pre-generation of common phrases."""
        if self._pregenerating:
            return
        if self.tts_engine is None:
            self.configure_surface_status_label(
                self.pregenerate_status_label, "TTS engine not available.", "warning"
            )
            return
        if not self.pregenerate_enabled_var.get():
            self.configure_surface_status_label(
                self.pregenerate_status_label, "Phrase pre-generation is disabled.", "warning"
            )
            return

        self._pregenerating = True
        self._pregenerate_stop_event.clear()
        self.pregenerate_button.configure(state="disabled")
        self.configure_surface_status_label(
            self.pregenerate_status_label, "Pre-generating...", "idle"
        )

        engine = self.tts_engine

        def run():
            loop = None
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                def progress(generated: int, total: int):
                    self._schedule_on_ui_thread(
                        lambda: self._pregenerate_progress(generated, total)
                    )

                count = loop.run_until_complete(
                    engine.pregenerate_common_phrases(
                        progress_callback=progress,
                        stop_event=self._pregenerate_stop_event,
                    )
                )
                self._schedule_on_ui_thread(lambda: self._pregenerate_done(count))
            except Exception as e:
                logger.error("Phrase pre-generation exception: %s", e)
                self._schedule_on_ui_thread(
                    lambda err=str(e): self._pregenerate_done(-1, error=err)
                )
            finally:
                if loop:
                    loop.close()

        threading.Thread(target=run, daemon=True).start()

    def _pregenerate_progress(self, generated: int, total: int):
        """Update the status label during pre-generation (UI thread)."""
        if not self._is_async_callback_target_alive():
            return
        self.configure_surface_status_label(
            self.pregenerate_status_label,
            f"Pre-generating... {generated}/{total}",
            "idle",
        )

    def _pregenerate_done(self, count: int, error: Optional[str] = None):
        """Handle pre-generation completion on the UI thread."""
        self._pregenerating = False
        if not self._is_async_callback_target_alive():
            return
        # Re-enable only while the feature is still turned on; the user may
        # have unchecked the enable box while a run was in flight.
        state = "normal" if self.pregenerate_enabled_var.get() else "disabled"
        self.pregenerate_button.configure(state=state)
        if error:
            self.configure_surface_status_label(
                self.pregenerate_status_label, f"Error: {error}", "error"
            )
        elif self._pregenerate_stop_event.is_set():
            self.configure_surface_status_label(
                self.pregenerate_status_label,
                f"Cancelled after {count} phrase(s).",
                "warning",
            )
        elif count > 0:
            self.configure_surface_status_label(
                self.pregenerate_status_label,
                f"Done: {count} phrase(s) cached.",
                "success",
            )
        else:
            self.configure_surface_status_label(
                self.pregenerate_status_label,
                "Nothing to pre-generate — speak phrases first or lower 'Minimum Uses'.",
                "idle",
            )

    def _create_performance_section(self, parent):
        """Create the performance settings section."""
        # Processing profile dropdown
        self.create_setting_label("Processing Profile:", parent).pack(anchor="w", pady=(SPACING_SM, SPACING_BASE))
        
        self.processing_profile_var = ctk.StringVar(value=self.settings.get("processing_profile", "balanced"))
        self.processing_profile_dropdown = ctk.CTkComboBox(
            parent,
            variable=self.processing_profile_var,
            values=["fast_preview", "balanced", "high_quality"],
            font=ctk.CTkFont(size=FONT_SM),
            state="readonly",
            width=200
        )
        self.processing_profile_dropdown.pack(anchor="w", pady=SPACING_BASE)
        
        self.create_helper_text(
            text="Fast Preview: No resampling, no stereo enhancement | Balanced: 48 kHz resampling with subtle speech-friendly stereo | High Quality: 48 kHz resampling with gentle stereo enhancement",
            parent=parent,
            font_size=FONT_XS,
        ).pack(anchor="w", pady=(0, SPACING_SM))
        
        # Text cache size
        self.create_setting_label("Text Cache Size:", parent).pack(anchor="w", pady=(SPACING_SM, SPACING_BASE))
        
        text_cache_frame = self.create_inline_frame(parent)
        
        self.text_cache_size_var = ctk.StringVar(value=str(self.settings.get("text_cache_size", 1000)))
        self.text_cache_entry = ctk.CTkEntry(
            text_cache_frame,
            textvariable=self.text_cache_size_var,
            font=ctk.CTkFont(size=FONT_MD),
            width=100
        )
        self.text_cache_entry.pack(side="left", padx=SPACING_BASE)
        
        self.create_helper_text(
            text="Number of processed text entries to cache (100-10000)",
            parent=text_cache_frame,
        ).pack(side="left", padx=SPACING_BASE)

    def _create_experimental_section(self, parent):
        """Create the experimental features section."""
        experimental_warning_label = self.create_helper_text(
            text="⚠ Experimental features may be unstable or change in future versions.",
            parent=parent,
        )
        experimental_warning_label.pack(anchor="w", pady=(0, SPACING_SM))
        
        # Streaming playback checkbox
        self.streaming_playback_var = ctk.BooleanVar(value=self.settings.get("enable_streaming_playback", False))
        self.streaming_playback_check = ctk.CTkCheckBox(
            parent,
            text="Enable Streaming Playback (Experimental)",
            variable=self.streaming_playback_var,
            font=ctk.CTkFont(size=FONT_MD)
        )
        self.streaming_playback_check.pack(anchor="w", pady=SPACING_BASE)
        
        streaming_desc_label = self.create_helper_text(
            text="Starts playing audio as soon as the first chunks arrive from Edge TTS, reducing the delay before you hear speech. Best for longer text. Note: Audio normalization and viseme sync use estimated timing in streaming mode.",
            parent=parent,
            font_size=FONT_XS,
        )
        streaming_desc_label.pack(anchor="w", pady=(0, SPACING_SM))
    
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
            logger.error("Error getting cache statistics: %s", e)
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
            "pregenerate_phrases_enabled": self.pregenerate_enabled_var.get(),
            "pregenerate_min_uses": self.pregenerate_min_uses_var.get(),
            "pregenerate_max_phrases": self.pregenerate_max_phrases_var.get(),
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
