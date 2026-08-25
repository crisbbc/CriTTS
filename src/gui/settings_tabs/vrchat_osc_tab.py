"""
VRChat OSC Tab
Settings for VRChat OSC chatbox and viseme features.
"""
import logging
import customtkinter as ctk
from typing import Any, Callable, Optional, List, Dict

from .base_tab import BaseTab
from ..theme_constants import (
    FONT_MD,
    BUTTON_HEIGHT,
    SPACING_MD,
    SPACING_BASE,
    SPACING_SM,
)

logger = logging.getLogger(__name__)

# Try to import VRChatOSCClient
try:
    from ...vrchat import VRChatOSCClient
except Exception:
    VRChatOSCClient = None


class VRChatOSCTab(BaseTab):
    """Tab for VRChat OSC settings."""
    
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
        super().__init__(tab_widget, settings_manager, tts_engine, audio_router, on_change)
    
    def _create_content(self):
        """Create the VRChat OSC tab content."""
        self.setup_layout()

        chatbox_section, chatbox_content = self.create_section_surface(
            "VRChat OSC Chatbox",
            parent=self.scroll,
        )
        chatbox_section.pack(fill="x", pady=(0, SPACING_MD))
        self._create_chatbox_section(chatbox_content)

        viseme_section, viseme_content = self.create_section_surface(
            "VRChat Viseme Lip-Sync",
            parent=self.scroll,
        )
        viseme_section.pack(fill="x", pady=(0, SPACING_MD))
        self._create_viseme_section(viseme_content)

        typing_section, typing_content = self.create_section_surface(
            "Typing Indicator",
            parent=self.scroll,
        )
        typing_section.pack(fill="x", pady=(0, SPACING_MD))
        self._create_typing_indicator_section(typing_content)

        # Initialize OSC enabled state
        self._on_osc_enabled_toggle()

    def _create_chatbox_section(self, parent):
        """Create the VRChat chatbox settings section."""
        self.osc_enabled_var = ctk.BooleanVar(value=self.settings.get("vrchat_osc_enabled", False))
        self.osc_enabled_check = ctk.CTkCheckBox(
            parent,
            text="Enable OSC (send to VRChat chatbox)", 
            variable=self.osc_enabled_var, 
            font=ctk.CTkFont(size=FONT_MD),
            command=self._on_osc_enabled_toggle
        )
        self.osc_enabled_check.pack(anchor="w", pady=SPACING_BASE)
        
        self.create_setting_label("IP:", parent).pack(anchor="w", pady=(SPACING_SM, SPACING_BASE))
        
        self.osc_ip_var = ctk.StringVar(value=self.settings.get("vrchat_osc_ip", "127.0.0.1"))
        self.osc_ip_entry = ctk.CTkEntry(parent, textvariable=self.osc_ip_var, width=200)
        self.osc_ip_entry.pack(anchor="w", pady=SPACING_BASE)
        
        self.create_setting_label("Port (default 9000):", parent).pack(anchor="w", pady=(SPACING_SM, SPACING_BASE))
        
        self.osc_port_var = ctk.StringVar(value=str(self.settings.get("vrchat_osc_port", 9000)))
        self.osc_port_entry = ctk.CTkEntry(parent, textvariable=self.osc_port_var, width=120)
        self.osc_port_entry.pack(anchor="w", pady=SPACING_BASE)
        
        self.osc_play_sound_var = ctk.BooleanVar(value=self.settings.get("vrchat_osc_play_sound", True))
        self.osc_play_sound_check = ctk.CTkCheckBox(
            parent,
            text="Play notification sound when sending", 
            variable=self.osc_play_sound_var, 
            font=ctk.CTkFont(size=FONT_MD)
        )
        self.osc_play_sound_check.pack(anchor="w", pady=SPACING_BASE)
        
        osc_sound_info_label = self.create_helper_text(
            text="Notification sound uses VRChat's built-in chatbox sound. Requires OSC to be enabled and may not work in all VRChat versions.",
            parent=parent,
        )
        osc_sound_info_label.pack(anchor="w", pady=(0, SPACING_BASE))
        
        self.osc_send_on_speak_var = ctk.BooleanVar(value=self.settings.get("vrchat_osc_send_on_speak", False))
        self.osc_send_on_speak_check = ctk.CTkCheckBox(
            parent,
            text="Send to chatbox when speaking (main window)", 
            variable=self.osc_send_on_speak_var, 
            font=ctk.CTkFont(size=FONT_MD)
        )
        self.osc_send_on_speak_check.pack(anchor="w", pady=SPACING_BASE)
        
        ctk.CTkButton(
            parent,
            text="Test connection", 
            command=self._test_osc_connection, 
            width=140, 
            height=BUTTON_HEIGHT
        ).pack(anchor="w", pady=SPACING_MD)
        
        self.osc_status_label = self.create_surface_status_label(parent)
        self.osc_status_label.pack(anchor="w", pady=SPACING_BASE)
    
    def _create_viseme_section(self, parent):
        """Create the viseme lip-sync section."""
        osc_viseme_info_label = self.create_helper_text(
            text="Viseme mapping enables realistic lip-sync animation in VRChat via OSC. Requires OSC to be enabled.",
            parent=parent,
        )
        osc_viseme_info_label.pack(anchor="w", pady=(0, SPACING_SM))
        
        self.viseme_enabled_var = ctk.BooleanVar(value=self.settings.get("vrchat_viseme_enabled", False))
        self.viseme_enabled_check = ctk.CTkCheckBox(
            parent,
            text="Enable Viseme Lip-Sync",
            variable=self.viseme_enabled_var,
            font=ctk.CTkFont(size=FONT_MD)
        )
        self.viseme_enabled_check.pack(anchor="w", pady=SPACING_BASE)
        
        self.create_setting_label("Viseme Smoothing:", parent).pack(anchor="w", pady=(SPACING_SM, SPACING_BASE))
        
        viseme_smoothing_frame = self.create_inline_frame(parent)
        
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
        self.viseme_smoothing_slider.pack(side="left", fill="x", expand=True, padx=SPACING_BASE)
        
        self.viseme_smoothing_value_label = ctk.CTkLabel(
            viseme_smoothing_frame,
            text=f"{current_smoothing}%",
            font=ctk.CTkFont(size=FONT_MD),
            width=50
        )
        self.viseme_smoothing_value_label.pack(side="right", padx=SPACING_BASE)
        
        self.viseme_amplitude_var = ctk.BooleanVar(value=self.settings.get("vrchat_voice_amplitude_enabled", False))
        self.viseme_amplitude_check = ctk.CTkCheckBox(
            parent,
            text="Use Voice Amplitude for Mouth Movement",
            variable=self.viseme_amplitude_var,
            font=ctk.CTkFont(size=FONT_MD)
        )
        self.viseme_amplitude_check.pack(anchor="w", pady=SPACING_BASE)
        
        # Store viseme widgets for enabling/disabling
        self._viseme_widgets = [
            self.viseme_enabled_check,
            self.viseme_smoothing_slider,
            self.viseme_amplitude_check,
        ]
        

    def _create_typing_indicator_section(self, parent):
        """Create the typing indicator section."""
        typing_indicator_info_label = self.create_helper_text(
            text="Shows a typing animation in VRChat's chatbox while TTS is playing.",
            parent=parent,
        )
        typing_indicator_info_label.pack(anchor="w", pady=(0, SPACING_SM))
        
        self.typing_animation_var = ctk.BooleanVar(value=self.settings.get("vrchat_osc_typing_animation", False))
        self.typing_animation_check = ctk.CTkCheckBox(
            parent,
            text="Enable Typing Indicator Animation",
            variable=self.typing_animation_var,
            font=ctk.CTkFont(size=FONT_MD)
        )
        self.typing_animation_check.pack(anchor="w", pady=SPACING_BASE)
        
        self.create_setting_label("Typing Indicator Timeout:", parent).pack(anchor="w", pady=(SPACING_SM, SPACING_BASE))
        
        typing_timeout_frame = self.create_inline_frame(parent)
        
        current_timeout = self.settings.get("vrchat_osc_typing_timeout", 2.0)
        self.typing_timeout_var = ctk.DoubleVar(value=current_timeout)
        self.typing_timeout_slider = ctk.CTkSlider(
            typing_timeout_frame,
            from_=0.5,
            to=10.0,
            number_of_steps=95,
            variable=self.typing_timeout_var,
            command=self._on_typing_timeout_change,
            width=400
        )
        self.typing_timeout_slider.pack(side="left", fill="x", expand=True, padx=SPACING_BASE)
        
        self.typing_timeout_value_label = ctk.CTkLabel(
            typing_timeout_frame,
            text=f"{current_timeout:.1f}s",
            font=ctk.CTkFont(size=FONT_MD),
            width=50
        )
        self.typing_timeout_value_label.pack(side="right", padx=SPACING_BASE)
        
        self.create_setting_label("Message Cooldown:", parent).pack(anchor="w", pady=(SPACING_SM, SPACING_BASE))
        
        message_cooldown_frame = self.create_inline_frame(parent)
        
        current_cooldown = self.settings.get("vrchat_osc_message_cooldown", 3.0)
        self.message_cooldown_var = ctk.DoubleVar(value=current_cooldown)
        self.message_cooldown_slider = ctk.CTkSlider(
            message_cooldown_frame,
            from_=0.0,
            to=10.0,
            number_of_steps=100,
            variable=self.message_cooldown_var,
            command=self._on_message_cooldown_change,
            width=400
        )
        self.message_cooldown_slider.pack(side="left", fill="x", expand=True, padx=SPACING_BASE)
        
        self.message_cooldown_value_label = ctk.CTkLabel(
            message_cooldown_frame,
            text=f"{current_cooldown:.1f}s",
            font=ctk.CTkFont(size=FONT_MD),
            width=50
        )
        self.message_cooldown_value_label.pack(side="right", padx=SPACING_BASE)
        
        message_cooldown_info_label = self.create_helper_text(
            text="Time to wait after sending a message before typing animation can restart. Gives others time to read your message.",
            parent=parent,
        )
        message_cooldown_info_label.pack(anchor="w", pady=(0, SPACING_BASE))
        
        self._typing_indicator_widgets = [
            self.typing_animation_check,
            self.typing_timeout_slider,
            self.message_cooldown_slider,
        ]
    
    def _on_osc_enabled_toggle(self):
        """Toggle viseme and typing indicator options based on OSC enabled state."""
        osc_enabled = self.osc_enabled_var.get()
        
        for widget in self._viseme_widgets:
            try:
                widget.configure(state="normal" if osc_enabled else "disabled")
            except Exception:
                logger.debug("Widget state update failed", exc_info=True)
        
        for widget in self._typing_indicator_widgets:
            try:
                widget.configure(state="normal" if osc_enabled else "disabled")
            except Exception:
                logger.debug("Widget state update failed", exc_info=True)
        
        if not osc_enabled:
            self.viseme_enabled_var.set(False)
            self.typing_animation_var.set(False)
        
        if self.parent_window and hasattr(self.parent_window, "main_window"):
            try:
                self.parent_window.main_window.refresh_vrchat_osc()
            except Exception:
                logger.debug("VRChat OSC tab refresh failed", exc_info=True)
    
    def _on_viseme_smoothing_change(self, value):
        """Update viseme smoothing label when slider changes."""
        self.viseme_smoothing_value_label.configure(text=f"{int(value)}%")
        
        if self.parent_window and hasattr(self.parent_window, "main_window"):
            try:
                self.parent_window.main_window.refresh_vrchat_osc()
            except Exception:
                logger.debug("VRChat OSC tab refresh failed", exc_info=True)
    
    def _on_typing_timeout_change(self, value):
        """Update typing timeout label when slider changes."""
        self.typing_timeout_value_label.configure(text=f"{value:.1f}s")
        
        if self.parent_window and hasattr(self.parent_window, "main_window"):
            try:
                self.parent_window.main_window.refresh_vrchat_osc()
            except Exception:
                logger.debug("VRChat OSC tab refresh failed", exc_info=True)
    
    def _on_message_cooldown_change(self, value):
        """Update message cooldown label when slider changes."""
        self.message_cooldown_value_label.configure(text=f"{value:.1f}s")
        
        if self.parent_window and hasattr(self.parent_window, "main_window"):
            try:
                self.parent_window.main_window.refresh_vrchat_osc()
            except Exception:
                logger.debug("VRChat OSC tab refresh failed", exc_info=True)
    
    def _test_osc_connection(self):
        """Test OSC configuration."""
        self.configure_surface_status_label(self.osc_status_label, "Testing...", "idle")
        if self.parent_window:
            self.parent_window.update()
        
        try:
            port_val = self.osc_port_var.get().strip()
            port = int(port_val) if port_val else 9000
        except ValueError:
            self.configure_surface_status_label(
                self.osc_status_label,
                "Invalid port. Use a number (e.g. 9000).",
                "warning",
            )
            return
        
        ip = self.osc_ip_var.get().strip() or "127.0.0.1"
        
        if not VRChatOSCClient:
            self.configure_surface_status_label(
                self.osc_status_label,
                "OSC client not available.",
                "warning",
            )
            return
        
        client = VRChatOSCClient(ip=ip, port=port)
        success, message = client.test_connection()
        
        if success:
            self.configure_surface_status_label(
                self.osc_status_label,
                "OSC configured correctly. Messages will be sent to VRChat if it's running with OSC enabled.",
                "success",
            )
        else:
            self.configure_surface_status_label(self.osc_status_label, message, "warning")
    
    def get_settings(self) -> Dict[str, Any]:
        """Get current settings from the tab UI."""
        try:
            port = int(self.osc_port_var.get().strip()) if self.osc_port_var.get().strip() else 9000
        except ValueError:
            port = 9000
        
        return {
            "vrchat_osc_enabled": self.osc_enabled_var.get(),
            "vrchat_osc_ip": self.osc_ip_var.get().strip() or "127.0.0.1",
            "vrchat_osc_port": port,
            "vrchat_osc_play_sound": self.osc_play_sound_var.get(),
            "vrchat_osc_send_on_speak": self.osc_send_on_speak_var.get(),
            "vrchat_viseme_enabled": self.viseme_enabled_var.get(),
            "vrchat_viseme_smoothing": self.viseme_smoothing_var.get() / 100.0,
            "vrchat_voice_amplitude_enabled": self.viseme_amplitude_var.get(),
            "vrchat_osc_typing_animation": self.typing_animation_var.get(),
            "vrchat_osc_typing_timeout": self.typing_timeout_var.get(),
            "vrchat_osc_message_cooldown": self.message_cooldown_var.get(),
        }
    
    def validate(self) -> List[str]:
        """Validate the tab's settings."""
        errors = []
        
        # Validate OSC port
        try:
            port = int(self.osc_port_var.get().strip()) if self.osc_port_var.get().strip() else 9000
            if not (1 <= port <= 65535):
                errors.append(f"OSC port out of range: {port}")
        except ValueError:
            errors.append(f"Invalid OSC port: {self.osc_port_var.get()}")
        
        return errors
