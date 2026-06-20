"""
Appearance Tab
Settings for application appearance and visible buttons.
"""
import customtkinter as ctk
from typing import Any, List, Dict

from .base_tab import BaseTab
from ..theme_constants import FONT_MD


class AppearanceTab(BaseTab):
    """Tab for appearance settings."""

    def _create_content(self):
        """Create the appearance tab content."""
        self.setup_layout()

        appearance_section, appearance_content = self.create_section_surface("Appearance Mode")
        appearance_section.pack(fill="x", pady=(0, 15))

        self.appearance_var = ctk.StringVar(value=self.settings.get("appearance_mode", "Dark"))
        self.appearance_dropdown = ctk.CTkComboBox(
            appearance_content,
            variable=self.appearance_var,
            values=["Dark", "Light", "System"],
            font=ctk.CTkFont(size=FONT_MD),
            state="readonly",
            width=200,
        )
        self.appearance_dropdown.pack(anchor="w", pady=(0, 8))

        self.preview_label = self.create_helper_text(
            "Preview will apply on save",
            parent=appearance_content,
        )
        self.preview_label.pack(anchor="w")

        visible_buttons_section, visible_buttons_content = self.create_section_surface("Visible Buttons")
        visible_buttons_section.pack(fill="x")

        self.visible_buttons_hint = self.create_helper_text(
            "Choose which buttons appear in the main window. Settings is always visible.",
            parent=visible_buttons_content,
        )
        self.visible_buttons_hint.pack(anchor="w", pady=(0, 10))

        current_visible = self.settings.get(
            "visible_buttons",
            ["speak", "stop", "clear", "voice", "overlay"],
        )

        self.visible_buttons_vars: Dict[str, ctk.BooleanVar] = {}
        button_options = [
            ("speak", "Speak"),
            ("stop", "Stop"),
            ("clear", "Clear"),
            ("voice", "Voice"),
            ("overlay", "Overlay"),
        ]

        for button_key, button_label in button_options:
            var = ctk.BooleanVar(value=button_key in current_visible)
            self.visible_buttons_vars[button_key] = var
            checkbox = ctk.CTkCheckBox(
                visible_buttons_content,
                text=button_label,
                variable=var,
                font=ctk.CTkFont(size=FONT_MD),
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

        if self.appearance_var.get() not in ["Dark", "Light", "System"]:
            errors.append(f"Invalid appearance mode: {self.appearance_var.get()}")

        return errors
