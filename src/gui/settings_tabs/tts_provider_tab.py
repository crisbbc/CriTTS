"""
TTS Provider Tab
Settings for choosing between available TTS providers (online / offline).
"""
import customtkinter as ctk
from typing import Any, Callable, List, Dict, Optional

from .base_tab import BaseTab
from ..theme_constants import (
    FONT_SM, FONT_MD, FONT_XL, FONT_WEIGHT_BOLD,
    COLOR_INFO,
)

# Internal key for the Piper provider (used for visibility checks)
_PIPER_PROVIDER_KEY = "piper"

_PROVIDER_OPTIONS = [
    "edge",
    _PIPER_PROVIDER_KEY,
]

_PROVIDER_LABELS = {
    "edge": "Edge TTS (Online)",
    "piper": "Piper TTS (Offline)",
}

_PROVIDER_DESCRIPTIONS = {
    "edge": (
        "Microsoft Edge Text-to-Speech\n\n"
        "• Requires an active internet connection\n"
        "• 100+ high-quality neural voices\n"
        "• Broad language and dialect support\n"
        "• Rate, volume, and pitch controls"
    ),
    "piper": (
        "Piper — Open-Source Offline Neural TTS\n\n"
        "• Works fully offline — no internet needed\n"
        "• Privacy-focused (no data sent externally)\n"
        "• Open-source voice models (ONNX-based)\n"
        "• Voice models are downloaded on first use\n"
        "• Rate and volume controls supported\n"
        "• Note: pitch control is not supported by Piper"
    ),
}


class TTSProviderTab(BaseTab):
    """Tab for selecting the active TTS provider."""

    def __init__(self, *args, **kwargs):
        # Callback invoked with the new provider key whenever the user changes provider.
        # Wired up by SettingsWindow after both tabs are created.
        self._voice_tab_callback: Optional[Callable[[str], None]] = None
        super().__init__(*args, **kwargs)

    def set_voice_tab_callback(self, callback: Optional[Callable[[str], None]]) -> None:
        """Register a callback that is called with the new provider key on change."""
        self._voice_tab_callback = callback

    def _create_content(self):
        """Build the TTS Provider tab UI."""
        self.setup_layout()

        # Title
        ctk.CTkLabel(
            self.scroll,
            text="TTS Provider",
            font=ctk.CTkFont(size=FONT_XL, weight=FONT_WEIGHT_BOLD),
        ).pack(anchor="w", pady=(10, 5))

        intro_label = ctk.CTkLabel(
            self.scroll,
            text=(
                "Choose which text-to-speech engine CriTTS uses. "
                "Changes take effect after saving and will also update the available voice list."
            ),
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550,
        )
        intro_label.pack(anchor="w", pady=(0, 15))
        self.add_wraplength_label(intro_label)

        # --- Provider selection ---
        self.create_section_header("Active Provider").pack(anchor="w", pady=(5, 5))

        current = self.settings.get("tts_provider", "edge")

        self._provider_var = ctk.StringVar(value=_PROVIDER_LABELS.get(current, _PROVIDER_LABELS["edge"]))

        self._provider_dropdown = ctk.CTkComboBox(
            self.scroll,
            variable=self._provider_var,
            values=[_PROVIDER_LABELS[k] for k in _PROVIDER_OPTIONS],
            font=ctk.CTkFont(size=FONT_MD),
            state="readonly",
            width=320,
            command=self._on_provider_changed,
        )
        self._provider_dropdown.pack(anchor="w", pady=(5, 10))

        self.create_separator(self.scroll).pack(fill="x", pady=(5, 10))

        # --- Description box ---
        self.create_section_header("Provider Details").pack(anchor="w", pady=(5, 5))

        self._desc_label = ctk.CTkLabel(
            self.scroll,
            text=_PROVIDER_DESCRIPTIONS.get(current, ""),
            font=ctk.CTkFont(size=FONT_SM),
            justify="left",
            wraplength=500,
        )
        self._desc_label.pack(anchor="w", pady=(5, 10))
        self.add_wraplength_label(self._desc_label)

        self.create_separator(self.scroll).pack(fill="x", pady=(5, 10))

        # --- Informational note about voices ---
        note_label = ctk.CTkLabel(
            self.scroll,
            text=(
                "ℹ  Switching providers updates the Voice tab list automatically. "
                "Save settings to apply the new provider globally."
            ),
            font=ctk.CTkFont(size=FONT_SM),
            text_color=COLOR_INFO,
            wraplength=500,
            justify="left",
        )
        note_label.pack(anchor="w", pady=(0, 10))
        self.add_wraplength_label(note_label)

        # --- Note directing users to the Voice tab for provider-specific sliders ---
        sliders_note = ctk.CTkLabel(
            self.scroll,
            text=(
                "ℹ  Provider-specific audio controls (e.g. Piper naturalness sliders) "
                "are available in the Voice tab and update automatically when you change provider."
            ),
            font=ctk.CTkFont(size=FONT_SM),
            text_color=COLOR_INFO,
            wraplength=500,
            justify="left",
        )
        sliders_note.pack(anchor="w", pady=(0, 10))
        self.add_wraplength_label(sliders_note)

    # ------------------------------------------------------------------

    def _on_provider_changed(self, selected_label: str):
        """Update the description box and notify the Voice tab when a new provider is selected."""
        key = self._label_to_key(selected_label)
        self._desc_label.configure(text=_PROVIDER_DESCRIPTIONS.get(key, ""))
        if self._voice_tab_callback is not None:
            self._voice_tab_callback(key)

    @staticmethod
    def _label_to_key(label: str) -> str:
        """Reverse-lookup: human-readable label → internal key."""
        for k, v in _PROVIDER_LABELS.items():
            if v == label:
                return k
        return "edge"

    # ------------------------------------------------------------------
    # BaseTab interface
    # ------------------------------------------------------------------

    def get_settings(self) -> Dict[str, Any]:
        return {
            "tts_provider": self._label_to_key(self._provider_var.get()),
        }

    def validate(self) -> List[str]:
        key = self._label_to_key(self._provider_var.get())
        if key not in _PROVIDER_OPTIONS:
            return [f"Unknown TTS provider: '{self._provider_var.get()}'"]
        return []
