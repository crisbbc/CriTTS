"""
Soundboard Tab
Settings for custom sound slots used by inline speak commands like [1].
"""
import os
import customtkinter as ctk
from tkinter import filedialog
from typing import Any, List, Dict

from .base_tab import BaseTab
from ..theme_constants import BUTTON_HEIGHT, FONT_SM, FONT_MD, SPACING_BASE, SPACING_SM, SPACING_XS


class SoundboardTab(BaseTab):
    """Tab for soundboard slot settings."""

    def _create_content(self):
        """Create the soundboard tab content."""
        self.setup_layout()

        soundboard_section, soundboard_content = self.create_section_surface("Soundboard")
        soundboard_section.pack(fill="both", expand=True)

        self.info_label = self.create_helper_text(
            "Map slots to local audio files. During Speak, [1]..[99] will play mapped slots instead of being spoken as text.",
            parent=soundboard_content,
        )
        self.info_label.pack(anchor="w", pady=(0, SPACING_SM))

        self.enabled_var = ctk.BooleanVar(value=self.settings.get("soundboard_enabled", True))
        self.enabled_checkbox = ctk.CTkCheckBox(
            soundboard_content,
            text="Enable soundboard command parsing",
            variable=self.enabled_var,
            font=ctk.CTkFont(size=FONT_MD),
        )
        self.enabled_checkbox.pack(anchor="w", pady=(0, SPACING_SM))

        stored_slots = self.settings.get("soundboard_slots", {})
        self.slot_vars: Dict[str, ctk.StringVar] = {}

        slots_frame = ctk.CTkFrame(soundboard_content, fg_color="transparent")
        slots_frame.pack(fill="both", expand=True, pady=(0, SPACING_SM))

        for slot_num in range(1, 11):
            slot_key = str(slot_num)
            default_path = stored_slots.get(slot_key, "") if isinstance(stored_slots, dict) else ""
            if default_path is None:
                default_path = ""

            row = ctk.CTkFrame(slots_frame, fg_color="transparent")
            row.pack(fill="x", pady=SPACING_BASE)

            ctk.CTkLabel(
                row,
                text=f"Slot [{slot_key}]",
                font=ctk.CTkFont(size=FONT_MD),
                width=80,
                anchor="w",
            ).pack(side="left", padx=(0, SPACING_XS))

            self.slot_vars[slot_key] = ctk.StringVar(value=default_path)

            entry = ctk.CTkEntry(
                row,
                textvariable=self.slot_vars[slot_key],
                font=ctk.CTkFont(size=FONT_SM),
            )
            entry.pack(side="left", fill="x", expand=True, padx=(0, SPACING_XS))

            browse_button = ctk.CTkButton(
                row,
                text="Browse",
                width=80,
                height=BUTTON_HEIGHT,
                command=lambda slot=slot_key: self._browse_slot(slot),
            )
            browse_button.pack(side="left", padx=(0, SPACING_BASE))

            clear_button = ctk.CTkButton(
                row,
                text="Clear",
                width=70,
                height=BUTTON_HEIGHT,
                command=lambda slot=slot_key: self._clear_slot(slot),
            )
            clear_button.pack(side="left")

        self.hint_label = self.create_helper_text(
            "Examples: 'hello [1] world' plays slot 1 between two spoken segments. Invalid tokens like [abc] stay as normal spoken text.",
            parent=soundboard_content,
        )
        self.hint_label.pack(anchor="w")

    def _browse_slot(self, slot_key: str):
        """Open file picker and assign an audio file to the slot."""
        path = filedialog.askopenfilename(
            title=f"Select audio file for slot [{slot_key}]",
            filetypes=[
                ("Audio Files", "*.wav *.mp3 *.ogg *.flac *.m4a *.aac"),
                ("All Files", "*.*"),
            ],
        )
        if path:
            self.slot_vars[slot_key].set(path)

    def _clear_slot(self, slot_key: str):
        """Clear file path for a slot."""
        self.slot_vars[slot_key].set("")

    def get_settings(self) -> Dict[str, Any]:
        """Get current settings from the tab UI."""
        slots: Dict[str, str] = {}
        for slot_key, var in self.slot_vars.items():
            slots[slot_key] = var.get().strip()

        return {
            "soundboard_enabled": bool(self.enabled_var.get()),
            "soundboard_slots": slots,
        }

    def validate(self) -> List[str]:
        """Validate configured soundboard slot paths."""
        issues: List[str] = []
        for slot_key, var in self.slot_vars.items():
            path = var.get().strip()
            if path and not os.path.isfile(path):
                issues.append(f"Soundboard slot [{slot_key}] file not found: {path}")
        return issues
