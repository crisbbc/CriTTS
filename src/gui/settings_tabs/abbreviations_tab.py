"""
Abbreviations Tab
Settings for text abbreviation expansions.
"""
import customtkinter as ctk
from typing import Any, List, Dict

from .base_tab import BaseTab
from ..theme_constants import BUTTON_HEIGHT, FONT_SM, FONT_MD


class AbbreviationsTab(BaseTab):
    """Tab for abbreviation settings."""

    def _create_content(self):
        """Create the abbreviations tab content."""
        self.setup_layout()

        abbreviations_section, abbreviations_content = self.create_section_surface("Abbreviations")
        abbreviations_section.pack(fill="both", expand=True, pady=(0, 15))

        self.info_label = self.create_helper_text(
            "Enter one abbreviation per line in format: key=expansion",
            parent=abbreviations_content,
        )
        self.info_label.pack(anchor="w", pady=(0, 10))

        self.example_label = self.create_helper_text(
            "Example: brb=be right back  |  omg=oh my god",
            parent=abbreviations_content,
        )
        self.example_label.pack(anchor="w", pady=(0, 10))

        self.abbrev_text = ctk.CTkTextbox(
            abbreviations_content,
            wrap="word",
            font=ctk.CTkFont(size=FONT_MD),
            height=220,
            **self.get_input_surface_style(),
        )
        self.abbrev_text.pack(fill="both", expand=True, pady=(0, 10))

        abbrev_dict = self.settings.get("abbreviations", {})
        formatted_lines = [f"{key}={value}" for key, value in sorted(abbrev_dict.items())]
        self.abbrev_text.insert("1.0", "\n".join(formatted_lines))

        self.abbrev_validate_btn = ctk.CTkButton(
            abbreviations_content,
            text="Validate Format",
            command=self._validate_abbreviations,
            width=140,
            height=BUTTON_HEIGHT,
        )
        self.abbrev_validate_btn.pack(anchor="w", pady=(0, 10))

        self.abbrev_status_label = ctk.CTkLabel(
            abbreviations_content,
            text="",
            font=ctk.CTkFont(size=FONT_SM),
            text_color=self.get_surface_status_text_color(),
            wraplength=100,
            justify="left",
        )
        self.abbrev_status_label.pack(anchor="w")
        self.add_wraplength_label(self.abbrev_status_label)

        usage_section, usage_content = self.create_section_surface("Usage Tips")
        usage_section.pack(fill="x")

        self.usage_text = ctk.CTkTextbox(
            usage_content,
            font=ctk.CTkFont(size=FONT_SM),
            height=180,
            wrap="word",
            **self.get_input_surface_style(),
        )
        self.usage_text.pack(fill="x")
        self.usage_text.insert(
            "1.0",
            """Format: one abbreviation per line as key=expansion

Examples:
  brb=be right back
  omg=oh my god
  idk=I don't know

• Matching is case-insensitive in the main window.
• Use # at the start of a line for comments (e.g. # optional abbreviations).
• After saving, abbreviations are expanded when you speak in the main window.""",
        )
        self.usage_text.configure(state="disabled")

    def _parse_abbreviations(self, text: str) -> tuple:
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
            self.configure_surface_status_label(
                self.abbrev_status_label,
                f"Format valid - {count} abbreviation(s) found",
                "success",
            )
        elif parsed:
            message = "; ".join(errors[:3]) + ("..." if len(errors) > 3 else "")
            self.configure_surface_status_label(
                self.abbrev_status_label,
                f"Warning: {count} abbreviation(s) found. Issues: {message}",
                "warning",
            )
        else:
            message = "; ".join(errors[:5]) + ("..." if len(errors) > 5 else "")
            self.configure_surface_status_label(
                self.abbrev_status_label,
                f"Error: {message}",
                "error",
            )

    def get_settings(self) -> Dict[str, Any]:
        """Get current settings from the tab UI."""
        abbrev_raw = self.abbrev_text.get("1.0", "end-1c")
        parsed, _ = self._parse_abbreviations(abbrev_raw)
        return {"abbreviations": parsed}

    def validate(self) -> List[str]:
        """Validate the tab's settings."""
        return []
