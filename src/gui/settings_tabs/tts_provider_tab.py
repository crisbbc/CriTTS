"""
TTS Provider Tab
Settings for choosing between available TTS providers (online / offline).
"""
import customtkinter as ctk
from typing import Any, List, Dict

from .base_tab import BaseTab
from ..theme_constants import (
    FONT_SM, FONT_MD, FONT_LG, FONT_XL, FONT_WEIGHT_BOLD,
    COLOR_INFO,
)

# Default Piper noise values (match piper library defaults)
_PIPER_NOISE_SCALE_DEFAULT = 0.667
_PIPER_NOISE_W_SCALE_DEFAULT = 0.8

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

        # --- Piper naturalness settings ---
        self._piper_settings_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        self._piper_settings_frame.pack(fill="x", pady=(0, 5))
        self._create_piper_naturalness_section(self._piper_settings_frame)

        # Show/hide Piper settings depending on current provider
        self._update_piper_settings_visibility(current)

        # --- Informational note about voices ---
        note_label = ctk.CTkLabel(
            self.scroll,
            text=(
                "ℹ  After switching providers, save and reopen Settings to see "
                "the updated voice list in the Voice tab."
            ),
            font=ctk.CTkFont(size=FONT_SM),
            text_color=COLOR_INFO,
            wraplength=500,
            justify="left",
        )
        note_label.pack(anchor="w", pady=(0, 10))
        self.add_wraplength_label(note_label)

    # ------------------------------------------------------------------
    # Piper naturalness sliders
    # ------------------------------------------------------------------

    def _create_piper_naturalness_section(self, parent: ctk.CTkFrame):
        """Create the Piper-specific naturalness sliders."""
        self.create_section_header("Piper Naturalness Settings", parent).pack(
            anchor="w", pady=(5, 5)
        )

        desc = ctk.CTkLabel(
            parent,
            text=(
                "Adjust phoneme variability to improve speech naturalness. "
                "Higher values add more variation; lower values produce more monotone output."
            ),
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=500,
            justify="left",
        )
        desc.pack(anchor="w", pady=(0, 10))
        self.add_wraplength_label(desc)

        # Noise Scale slider (expressiveness)
        ctk.CTkLabel(
            parent,
            text="Expressiveness (noise_scale)",
            font=ctk.CTkFont(size=FONT_MD, weight=FONT_WEIGHT_BOLD),
        ).pack(anchor="w", pady=(5, 2))

        noise_desc = ctk.CTkLabel(
            parent,
            text="Controls generator noise / expressiveness. Default: 0.667",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
        )
        noise_desc.pack(anchor="w", pady=(0, 5))

        noise_frame = ctk.CTkFrame(parent, fg_color="transparent")
        noise_frame.pack(fill="x", pady=(0, 10))

        saved_noise = self.settings.get("piper_noise_scale", _PIPER_NOISE_SCALE_DEFAULT)
        self._noise_scale_var = ctk.DoubleVar(value=float(saved_noise))

        self._noise_scale_slider = ctk.CTkSlider(
            noise_frame,
            from_=0.0,
            to=2.0,
            number_of_steps=200,
            variable=self._noise_scale_var,
            command=self._on_noise_scale_change,
            width=400,
        )
        self._noise_scale_slider.pack(side="left", fill="x", expand=True, padx=5)

        self._noise_scale_label = ctk.CTkLabel(
            noise_frame,
            text=f"{float(saved_noise):.3f}",
            font=ctk.CTkFont(size=FONT_MD),
            width=55,
        )
        self._noise_scale_label.pack(side="right", padx=5)

        # Noise W Scale slider (duration variability)
        ctk.CTkLabel(
            parent,
            text="Duration Variability (noise_w_scale)",
            font=ctk.CTkFont(size=FONT_MD, weight=FONT_WEIGHT_BOLD),
        ).pack(anchor="w", pady=(5, 2))

        noise_w_desc = ctk.CTkLabel(
            parent,
            text="Controls phoneme duration variability. Default: 0.800",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
        )
        noise_w_desc.pack(anchor="w", pady=(0, 5))

        noise_w_frame = ctk.CTkFrame(parent, fg_color="transparent")
        noise_w_frame.pack(fill="x", pady=(0, 10))

        saved_noise_w = self.settings.get("piper_noise_w_scale", _PIPER_NOISE_W_SCALE_DEFAULT)
        self._noise_w_scale_var = ctk.DoubleVar(value=float(saved_noise_w))

        self._noise_w_scale_slider = ctk.CTkSlider(
            noise_w_frame,
            from_=0.0,
            to=2.0,
            number_of_steps=200,
            variable=self._noise_w_scale_var,
            command=self._on_noise_w_scale_change,
            width=400,
        )
        self._noise_w_scale_slider.pack(side="left", fill="x", expand=True, padx=5)

        self._noise_w_scale_label = ctk.CTkLabel(
            noise_w_frame,
            text=f"{float(saved_noise_w):.3f}",
            font=ctk.CTkFont(size=FONT_MD),
            width=55,
        )
        self._noise_w_scale_label.pack(side="right", padx=5)

        self.create_separator(parent).pack(fill="x", pady=(5, 10))

    def _on_noise_scale_change(self, value):
        self._noise_scale_label.configure(text=f"{float(value):.3f}")

    def _on_noise_w_scale_change(self, value):
        self._noise_w_scale_label.configure(text=f"{float(value):.3f}")

    def _update_piper_settings_visibility(self, provider_key: str):
        """Show Piper naturalness settings only when Piper is selected."""
        if provider_key == _PIPER_PROVIDER_KEY:
            self._piper_settings_frame.pack(fill="x", pady=(0, 5))
        else:
            self._piper_settings_frame.pack_forget()

    # ------------------------------------------------------------------

    def _on_provider_changed(self, selected_label: str):
        """Update the description box and Piper settings visibility when a new provider is selected."""
        key = self._label_to_key(selected_label)
        self._desc_label.configure(text=_PROVIDER_DESCRIPTIONS.get(key, ""))
        self._update_piper_settings_visibility(key)

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
            # Rounded to 3 decimal places (slider step is 0.01, extra precision is harmless)
            "piper_noise_scale": round(self._noise_scale_var.get(), 3),
            "piper_noise_w_scale": round(self._noise_w_scale_var.get(), 3),
        }

    def validate(self) -> List[str]:
        key = self._label_to_key(self._provider_var.get())
        if key not in _PROVIDER_OPTIONS:
            return [f"Unknown TTS provider: '{self._provider_var.get()}'"]
        return []
