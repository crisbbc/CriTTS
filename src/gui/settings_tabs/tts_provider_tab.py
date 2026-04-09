"""
TTS Provider Tab
Settings for choosing between available TTS providers (online / offline).
"""
import customtkinter as ctk
from typing import Any, Callable, List, Dict, Optional

from .base_tab import BaseTab
from ..theme_constants import (
    FONT_SM, FONT_MD, FONT_LG, FONT_XL, FONT_WEIGHT_BOLD,
    SPACING_MD,
)

# Internal key for the Coqui provider (used for visibility checks)
_COQUI_PROVIDER_KEY = "coqui"

_PROVIDER_OPTIONS = [
    "edge",
    "piper",
    _COQUI_PROVIDER_KEY,
]

_PROVIDER_LABELS = {
    "edge": "Edge TTS (Online)",
    "piper": "Piper TTS (Offline Fast)",
    "coqui": "Coqui TTS (Offline High Quality)",
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
        "Piper — Fast Offline Neural TTS\n\n"
        "• Works fully offline after each voice model is downloaded\n"
        "• Lightweight local inference with low startup overhead\n"
        "• Curated multilingual voice list for quick local playback\n"
        "• Voice models download automatically on first use\n"
        "• Rate and volume controls supported\n"
        "• Note: pitch control is not supported by Piper"
    ),
    "coqui": (
        "Coqui XTTS v2 — High-Quality Offline Neural TTS\n\n"
        "• Works fully offline — no internet needed after first run\n"
        "• Natural, expressive speech with 15 built-in speakers\n"
        "• Multilingual: 17 languages supported\n"
        "• Model downloaded automatically on first use (~1.8 GB)\n"
        "• GPU acceleration supported (NVIDIA CUDA)\n"
        "• Rate and volume controls supported\n"
        "• Note: pitch control is not supported by XTTS v2"
    ),
}


class TTSProviderTab(BaseTab):
    """Tab for selecting the active TTS provider."""

    def __init__(self, *args, **kwargs):
        # Callback invoked with the new provider key whenever the user changes provider.
        # Wired up by SettingsWindow after both tabs are created.
        self._voice_tab_callback: Optional[Callable[[str], None]] = None
        # Optional second callback (e.g. to trigger eager model preloading).
        self._provider_changed_callback: Optional[Callable[[str], None]] = None
        super().__init__(*args, **kwargs)

    def set_voice_tab_callback(self, callback: Optional[Callable[[str], None]]) -> None:
        """Register a callback that is called with the new provider key on change."""
        self._voice_tab_callback = callback

    def set_provider_changed_callback(self, callback: Optional[Callable[[str], None]]) -> None:
        """Register a secondary callback called with the new provider key on change."""
        self._provider_changed_callback = callback

    def _create_content(self):
        """Build the TTS Provider tab UI."""
        self.setup_layout()
        surface_theme = self.get_active_surface_theme()

        # Title
        ctk.CTkLabel(
            self.scroll,
            text="TTS Provider",
            font=ctk.CTkFont(size=FONT_XL, weight=FONT_WEIGHT_BOLD),
        ).pack(anchor="w", pady=(10, 5))

        intro_label = self.create_helper_text(
            text=(
                "Choose which text-to-speech engine CriTTS uses. "
                "Changes take effect after saving and will also update the available voice list."
            ),
            parent=self.scroll,
        )
        intro_label.pack(anchor="w", pady=(0, SPACING_MD))

        provider_section, provider_content = self.create_section_surface(
            "Active Provider",
            parent=self.scroll,
        )
        provider_section.pack(fill="x", pady=(0, SPACING_MD))

        current = self.settings.get("tts_provider", "edge")

        self._provider_var = ctk.StringVar(value=_PROVIDER_LABELS.get(current, _PROVIDER_LABELS["edge"]))

        self._provider_dropdown = ctk.CTkComboBox(
            provider_content,
            variable=self._provider_var,
            values=[_PROVIDER_LABELS[k] for k in _PROVIDER_OPTIONS],
            font=ctk.CTkFont(size=FONT_MD),
            state="readonly",
            width=320,
            command=self._on_provider_changed,
        )
        self._provider_dropdown.pack(anchor="w", pady=(0, 4))

        details_section, details_content = self.create_section_surface(
            "Provider Details",
            parent=self.scroll,
        )
        details_section.pack(fill="x", pady=(0, SPACING_MD))

        self._desc_label = ctk.CTkLabel(
            details_content,
            text=_PROVIDER_DESCRIPTIONS.get(current, ""),
            font=ctk.CTkFont(size=FONT_SM),
            justify="left",
            wraplength=500,
            text_color=surface_theme["text_primary"],
        )
        self._desc_label.pack(anchor="w", pady=(5, 10))
        self.add_wraplength_label(self._desc_label)

        # Store a reference so we can insert the Coqui frame right after this separator.
        self._desc_sep = self.create_separator(details_content)
        self._desc_sep.pack(fill="x", pady=(5, 10))

        # --- Coqui-specific settings (hidden when Edge is selected) ---
        # Plain header label — NOT create_section_header() — so no sidebar button
        # is added for this conditional section.
        self._coqui_settings_frame = ctk.CTkFrame(
            details_content,
            fg_color=surface_theme["pane_fg"],
            corner_radius=self.get_section_surface_style()["corner_radius"],
            border_width=1,
            border_color=surface_theme["border_color"],
        )

        ctk.CTkLabel(
            self._coqui_settings_frame,
            text="Coqui TTS Settings",
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD),
            text_color=surface_theme["text_primary"],
        ).pack(anchor="w", pady=(SPACING_MD, 5), padx=SPACING_MD)

        coqui_gpu_desc = self.create_helper_text(
            text="Select which CUDA GPU Coqui TTS should use. 'Auto' picks the best available GPU automatically.",
            parent=self._coqui_settings_frame,
        )
        coqui_gpu_desc.pack(anchor="w", pady=(0, 6), padx=SPACING_MD)

        gpu_options, gpu_labels = self._build_gpu_options()
        self._gpu_options_map: Dict[str, int] = dict(zip(gpu_labels, gpu_options))

        saved_gpu = self.settings.get("coqui_gpu_device", -2)
        # Find the label that matches the saved device index, fall back to first label
        saved_gpu_label = gpu_labels[0]
        for lbl, idx in self._gpu_options_map.items():
            if idx == saved_gpu:
                saved_gpu_label = lbl
                break

        self._gpu_device_var = ctk.StringVar(value=saved_gpu_label)
        ctk.CTkComboBox(
            self._coqui_settings_frame,
            variable=self._gpu_device_var,
            values=gpu_labels,
            font=ctk.CTkFont(size=FONT_MD),
            state="readonly",
            width=380,
        ).pack(anchor="w", pady=(0, 10), padx=SPACING_MD)

        self.create_separator(self._coqui_settings_frame).pack(fill="x", pady=(5, 10), padx=SPACING_MD)

        # --- Language selection ---
        ctk.CTkLabel(
            self._coqui_settings_frame,
            text="Speech Language",
            font=ctk.CTkFont(size=FONT_MD, weight=FONT_WEIGHT_BOLD),
            text_color=surface_theme["text_primary"],
        ).pack(anchor="w", pady=(0, 4), padx=SPACING_MD)

        language_desc = self.create_helper_text(
            text=(
                "Select the language for speech generation. "
                "XTTS v2 supports 17 languages."
            ),
            parent=self._coqui_settings_frame,
        )
        language_desc.pack(anchor="w", pady=(0, 6), padx=SPACING_MD)

        _LANGUAGE_OPTIONS = [
            ("English (en)", "en"),
            ("Spanish (es)", "es"),
            ("French (fr)", "fr"),
            ("German (de)", "de"),
            ("Italian (it)", "it"),
            ("Portuguese (pt)", "pt"),
            ("Polish (pl)", "pl"),
            ("Turkish (tr)", "tr"),
            ("Russian (ru)", "ru"),
            ("Dutch (nl)", "nl"),
            ("Czech (cs)", "cs"),
            ("Arabic (ar)", "ar"),
            ("Chinese (zh-cn)", "zh-cn"),
            ("Japanese (ja)", "ja"),
            ("Hungarian (hu)", "hu"),
            ("Korean (ko)", "ko"),
            ("Hindi (hi)", "hi"),
        ]
        self._language_label_to_code: Dict[str, str] = {lbl: code for lbl, code in _LANGUAGE_OPTIONS}
        self._language_code_to_label: Dict[str, str] = {code: lbl for lbl, code in _LANGUAGE_OPTIONS}
        language_labels = [lbl for lbl, _ in _LANGUAGE_OPTIONS]

        saved_lang_code = self.settings.get("coqui_language", "en")
        saved_lang_label = self._language_code_to_label.get(saved_lang_code, "English (en)")

        self._language_var = ctk.StringVar(value=saved_lang_label)
        ctk.CTkComboBox(
            self._coqui_settings_frame,
            variable=self._language_var,
            values=language_labels,
            font=ctk.CTkFont(size=FONT_MD),
            state="readonly",
            width=380,
        ).pack(anchor="w", pady=(0, SPACING_MD), padx=SPACING_MD)

        self.create_separator(self._coqui_settings_frame).pack(fill="x", pady=(5, SPACING_MD), padx=SPACING_MD)

        if current == _COQUI_PROVIDER_KEY:
            self._coqui_settings_frame.pack(fill="x", after=self._desc_sep)

        # --- Informational notes (kept inside provider details without extra cards) ---
        note_label = self.create_helper_text(
            text=(
                "ℹ  Switching providers updates the Voice tab list automatically. "
                "Save settings to apply the new provider globally."
            ),
            parent=details_content,
        )
        note_label.pack(anchor="w", pady=(0, 10))

        sliders_note = self.create_helper_text(
            text=(
                "ℹ  Rate and volume controls are available in the Quick Controls panel "
                "and update automatically when you change provider."
            ),
            parent=details_content,
        )
        sliders_note.pack(anchor="w", pady=(0, 10))

    # ------------------------------------------------------------------

    def _on_provider_changed(self, selected_label: str):
        """Update the description box, show/hide Coqui settings, and notify other tabs."""
        key = self._label_to_key(selected_label)
        self._desc_label.configure(text=_PROVIDER_DESCRIPTIONS.get(key, ""))

        # Show or hide the Coqui-specific settings section
        if key == _COQUI_PROVIDER_KEY:
            self._coqui_settings_frame.pack(fill="x", after=self._desc_sep)
        else:
            self._coqui_settings_frame.pack_forget()

        if self._voice_tab_callback is not None:
            self._voice_tab_callback(key)
        if self._provider_changed_callback is not None:
            self._provider_changed_callback(key)

    @staticmethod
    def _build_gpu_options():
        """Return (index_list, label_list) for GPU selection.

        -2 = Auto (best available CUDA GPU)
        0+ = specific CUDA device index
        """
        indices = [-2, 0, 1, 2, 3]
        labels = ["Auto (Best GPU)", "GPU 0", "GPU 1", "GPU 2", "GPU 3"]
        return indices, labels

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
        gpu_label = self._gpu_device_var.get()
        gpu_device = self._gpu_options_map.get(gpu_label, -2)
        language_label = self._language_var.get()
        language_code = self._language_label_to_code.get(language_label, "en")
        return {
            "tts_provider": self._label_to_key(self._provider_var.get()),
            "coqui_gpu_device": gpu_device,
            "coqui_language": language_code,
        }

    def validate(self) -> List[str]:
        key = self._label_to_key(self._provider_var.get())
        if key not in _PROVIDER_OPTIONS:
            return [f"Unknown TTS provider: '{self._provider_var.get()}'"]
        return []
