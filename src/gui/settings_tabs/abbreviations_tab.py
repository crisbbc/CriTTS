"""
Abbreviations Tab
Settings for text abbreviation expansions.
"""
import customtkinter as ctk
from typing import Any, Callable, Optional, List, Dict

from .base_tab import BaseTab
from ..theme_constants import (
    FONT_SM, FONT_MD, FONT_LG, FONT_WEIGHT_BOLD,
)


class AbbreviationsTab(BaseTab):
    """Tab for abbreviation settings."""
    
    def _create_content(self):
        """Create the abbreviations tab content."""
        self.scroll = ctk.CTkScrollableFrame(self.tab)
        self.scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.title_label = ctk.CTkLabel(
            self.scroll,
            text="Abbreviations",
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD)
        )
        self.title_label.pack(anchor="w", pady=(10, 5))
        
        self.info_label = ctk.CTkLabel(
            self.scroll,
            text="Enter one abbreviation per line in format: key=expansion",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550
        )
        self.info_label.pack(anchor="w", pady=(0, 10))
        self.add_wraplength_label(self.info_label)
        
        self.example_label = ctk.CTkLabel(
            self.scroll,
            text="Example: brb=be right back  |  omg=oh my god",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550
        )
        self.example_label.pack(anchor="w", pady=(0, 5))
        self.add_wraplength_label(self.example_label)
        
        self.create_separator(self.scroll).pack(fill="x", pady=15)
        
        self.abbrev_text = ctk.CTkTextbox(
            self.scroll,
            wrap="word",
            font=ctk.CTkFont(size=FONT_MD)
        )
        self.abbrev_text.pack(fill="both", expand=True, pady=5)
        
        # Load existing abbreviations
        abbrev_dict = self.settings.get("abbreviations", {})
        formatted_lines = [f"{k}={v}" for k, v in sorted(abbrev_dict.items())]
        self.abbrev_text.insert("1.0", "\n".join(formatted_lines))
        
        self.abbrev_validate_btn = ctk.CTkButton(
            self.scroll,
            text="Validate Format",
            command=self._validate_abbreviations,
            width=140,
            height=32
        )
        self.abbrev_validate_btn.pack(anchor="w", pady=10)
        
        self.abbrev_status_label = ctk.CTkLabel(
            self.scroll,
            text="",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550
        )
        self.abbrev_status_label.pack(anchor="w", pady=5)
        self.add_wraplength_label(self.abbrev_status_label)
        
        self.create_separator(self.scroll).pack(fill="x", pady=15)
        
        self.usage_label = ctk.CTkLabel(
            self.scroll,
            text="Usage Tips",
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD)
        )
        self.usage_label.pack(anchor="w", pady=(10, 5))
        
        self.usage_text = ctk.CTkTextbox(
            self.scroll,
            font=ctk.CTkFont(size=FONT_SM),
            height=180,
            wrap="word"
        )
        self.usage_text.pack(fill="x", pady=5)
        self.usage_text.insert("1.0", """Format: one abbreviation per line as key=expansion

Examples:
  brb=be right back
  omg=oh my god
  idk=I don't know

• Matching is case-insensitive in the main window.
• Use # at the start of a line for comments (e.g. # optional abbreviations).
• After saving, abbreviations are expanded when you speak in the main window.""")
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
    
    def get_settings(self) -> Dict[str, Any]:
        """Get current settings from the tab UI."""
        abbrev_raw = self.abbrev_text.get("1.0", "end-1c")
        parsed, _ = self._parse_abbreviations(abbrev_raw)
        return {"abbreviations": parsed}
    
    def validate(self) -> List[str]:
        """Validate the tab's settings."""
        # Abbreviations are parsed and invalid lines are skipped
        # No hard validation errors - just warnings shown in UI
        return []