"""
Appearance Tab
Settings for application appearance and visible buttons.
"""
import customtkinter as ctk
from typing import Any, Callable, Optional, List, Dict

from .base_tab import BaseTab
from ..theme_constants import (
    FONT_MD, FONT_LG, FONT_WEIGHT_BOLD,
)


class AppearanceTab(BaseTab):
    """Tab for appearance settings."""
    
    def _create_content(self):
        """Create the appearance tab content."""
        self.setup_layout()
        
        # Appearance mode
        self.appearance_label = self.create_section_header("Appearance Mode:")
        self.appearance_label.pack(anchor="w", pady=(10, 5))
        
        self.appearance_var = ctk.StringVar(value=self.settings.get("appearance_mode", "Dark"))
        self.appearance_dropdown = ctk.CTkComboBox(
            self.scroll,
            variable=self.appearance_var,
            values=["Dark", "Light", "System"],
            font=ctk.CTkFont(size=FONT_MD),
            state="readonly",
            width=200
        )
        self.appearance_dropdown.pack(anchor="w", pady=5)
        
        # Preview
        self.preview_label = ctk.CTkLabel(
            self.scroll,
            text="Preview will apply on save",
            font=ctk.CTkFont(size=FONT_MD),
            text_color="gray"
        )
        self.preview_label.pack(anchor="w", pady=5)
        
        # Separator
        self.create_separator(self.scroll).pack(fill="x", pady=15)
        
        # Visible Buttons Section
        self.visible_buttons_label = self.create_section_header("Visible Buttons:")
        self.visible_buttons_label.pack(anchor="w", pady=(10, 5))
        
        self.visible_buttons_hint = ctk.CTkLabel(
            self.scroll,
            text="Choose which buttons appear in the main window. Settings is always visible.",
            font=ctk.CTkFont(size=FONT_MD),
            text_color="gray"
        )
        self.visible_buttons_hint.pack(anchor="w", pady=(0, 10))
        self.add_wraplength_label(self.visible_buttons_hint)
        
        # Get current visible buttons from settings
        current_visible = self.settings.get("visible_buttons", ["speak", "stop", "clear", "voice", "overlay"])
        
        # Create checkboxes for each toggleable button
        self.visible_buttons_vars: Dict[str, ctk.BooleanVar] = {}
        button_options = [
            ("speak", "Speak"),
            ("stop", "Stop"),
            ("clear", "Clear"),
            ("voice", "Voice"),
            ("overlay", "Overlay")
        ]
        
        for button_key, button_label in button_options:
            var = ctk.BooleanVar(value=button_key in current_visible)
            self.visible_buttons_vars[button_key] = var
            checkbox = ctk.CTkCheckBox(
                self.scroll,
                text=button_label,
                variable=var,
                font=ctk.CTkFont(size=FONT_MD)
            )
            checkbox.pack(anchor="w", pady=2)
    
    def get_settings(self) -> Dict[str, Any]:
        """Get current settings from the tab UI."""
        visible_buttons = [key for key, var in self.visible_buttons_vars.items() if var.get()]
        return {
            "appearance_mode": self.appearance_var.get(),
            "visible_buttons": visible_buttons,
        }
    
    def validate(self) -> List[str]:
        """Validate the tab's settings."""
        errors = []
        
        # Validate appearance mode
        if self.appearance_var.get() not in ["Dark", "Light", "System"]:
            errors.append(f"Invalid appearance mode: {self.appearance_var.get()}")
        
        return errors