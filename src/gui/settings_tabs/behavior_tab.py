"""
Behavior Tab
Settings for speak mode, auto language detection, and STT options.
"""
import customtkinter as ctk
from typing import Any, List, Dict

from .base_tab import BaseTab
from ..theme_constants import BUTTON_HEIGHT, FONT_MD, FONT_SM, FONT_WEIGHT_BOLD, SPACING_BASE, SPACING_MD, SPACING_SM


class BehaviorTab(BaseTab):
    """Tab for behavior and STT settings."""

    def _create_content(self):
        """Create the behavior tab content."""
        self.setup_layout()

        behavior_section, behavior_content = self.create_section_surface("Behavior")
        behavior_section.pack(fill="x", pady=(0, SPACING_MD))
        self._create_behavior_section(behavior_content)

        transcription_section, transcription_content = self.create_section_surface("Text Transcription")
        transcription_section.pack(fill="x", pady=(0, SPACING_MD))
        self._create_transcription_section(transcription_content)

        refinement_section, refinement_content = self.create_section_surface("Transcription Refinement")
        refinement_section.pack(fill="x", pady=(0, SPACING_MD))
        self._create_refinement_section(refinement_content)

        preprocessing_section, preprocessing_content = self.create_section_surface("Audio Pre-processing")
        preprocessing_section.pack(fill="x", pady=(0, SPACING_MD))
        self._create_preprocessing_section(preprocessing_content)

        corrections_section, corrections_content = self.create_section_surface("Word Corrections")
        corrections_section.pack(fill="x")
        self._create_corrections_section(corrections_content)

    def _create_behavior_section(self, parent: ctk.CTkFrame):
        """Create the general behavior section."""
        self.behavior_desc_label = self.create_helper_text(
            "Choose which text is sent to TTS when you press Speak.",
            parent=parent,
        )
        self.behavior_desc_label.pack(anchor="w", pady=(0, SPACING_SM))

        speak_mode = self.settings.get("speak_mode", "current_line")
        self.speak_mode_current_line_var = ctk.BooleanVar(value=(speak_mode == "current_line"))
        self.speak_mode_check = ctk.CTkCheckBox(
            parent,
            text="Speak current line only (cursor line); when unchecked, speak all text",
            variable=self.speak_mode_current_line_var,
            font=ctk.CTkFont(size=FONT_MD),
        )
        self.speak_mode_check.pack(anchor="w", pady=SPACING_BASE)

        self.behavior_speak_mode_hint_label = self.create_helper_text(
            "Current line: only the line where the cursor is will be spoken. All text: entire textbox.",
            parent=parent,
        )
        self.behavior_speak_mode_hint_label.pack(anchor="w", pady=(SPACING_BASE, SPACING_SM))

        self.auto_language_var = ctk.BooleanVar(
            value=self.settings.get("auto_language_detection", False)
        )
        self.auto_language_check = ctk.CTkCheckBox(
            parent,
            text="Auto-select voice based on text language",
            variable=self.auto_language_var,
            font=ctk.CTkFont(size=FONT_MD),
        )
        self.auto_language_check.pack(anchor="w", pady=SPACING_BASE)

        self.behavior_auto_lang_desc_label = self.create_helper_text(
            "When enabled, the system will automatically detect the language of your text and select the most appropriate voice.",
            parent=parent,
        )
        self.behavior_auto_lang_desc_label.pack(anchor="w", pady=(0, SPACING_SM))

    def _create_transcription_section(self, parent: ctk.CTkFrame):
        """Create the text transcription section."""
        self.transcription_desc_label = self.create_helper_text(
            "Settings for voice input and automatic speech-to-text behaviour.",
            parent=parent,
        )
        self.transcription_desc_label.pack(anchor="w", pady=(0, SPACING_SM))

        self.stt_auto_speak_var = ctk.BooleanVar(value=self.settings.get("stt_auto_speak", False))
        self.stt_auto_speak_check = ctk.CTkCheckBox(
            parent,
            text="Automatically speak transcribed text",
            variable=self.stt_auto_speak_var,
            font=ctk.CTkFont(size=FONT_MD),
        )
        self.stt_auto_speak_check.pack(anchor="w", pady=SPACING_BASE)

        self.stt_auto_speak_desc_label = self.create_helper_text(
            "When enabled, text from voice input will be automatically spoken after transcription completes.",
            parent=parent,
        )
        self.stt_auto_speak_desc_label.pack(anchor="w", pady=(0, SPACING_SM))

        ctk.CTkLabel(
            parent,
            text="Voice Input Language:",
            font=ctk.CTkFont(size=FONT_MD, weight=FONT_WEIGHT_BOLD),
        ).pack(anchor="w", pady=(SPACING_SM, SPACING_BASE))

        self.stt_language_info_label = self.create_helper_text(
            "Language for speech recognition when using the Voice Input button.",
            parent=parent,
        )
        self.stt_language_info_label.pack(anchor="w", pady=(0, SPACING_SM))

        stt_language_frame = ctk.CTkFrame(parent, fg_color="transparent")
        stt_language_frame.pack(fill="x", pady=SPACING_BASE)

        self.stt_language_var = ctk.StringVar(value=self.settings.get("stt_language", "en-US"))
        self.stt_language_dropdown = ctk.CTkOptionMenu(
            stt_language_frame,
            variable=self.stt_language_var,
            values=[
                "en-US",
                "en-GB",
                "es-ES",
                "fr-FR",
                "de-DE",
                "it-IT",
                "pt-BR",
                "ru-RU",
                "zh-CN",
                "ja-JP",
                "ko-KR",
                "ar-SA",
                "hi-IN",
                "nl-NL",
                "pl-PL",
            ],
            font=ctk.CTkFont(size=FONT_MD),
            width=200,
        )
        self.stt_language_dropdown.pack(side="left", padx=SPACING_BASE)

        ctk.CTkLabel(
            parent,
            text="Voice Input Device:",
            font=ctk.CTkFont(size=FONT_MD, weight=FONT_WEIGHT_BOLD),
        ).pack(anchor="w", pady=(SPACING_SM, SPACING_BASE))

        self.mic_device_info_label = self.create_helper_text(
            "Microphone used for voice input. Leave as 'Default' to use the system default.",
            parent=parent,
        )
        self.mic_device_info_label.pack(anchor="w", pady=(0, SPACING_SM))

        mic_device_frame = ctk.CTkFrame(parent, fg_color="transparent")
        mic_device_frame.pack(fill="x", pady=SPACING_BASE)

        self._input_devices: List[Dict] = []
        self.stt_mic_device_var = ctk.StringVar()
        self.stt_mic_device_dropdown = ctk.CTkComboBox(
            mic_device_frame,
            variable=self.stt_mic_device_var,
            values=["Loading..."],
            font=ctk.CTkFont(size=FONT_MD),
            dropdown_font=ctk.CTkFont(size=FONT_SM),
            width=400,
            state="readonly",
        )
        self.stt_mic_device_dropdown.pack(side="left", padx=(0, SPACING_BASE))

        ctk.CTkButton(
            mic_device_frame,
            text="Refresh",
            font=ctk.CTkFont(size=FONT_MD),
            command=self._load_input_devices,
            height=BUTTON_HEIGHT,
            width=80,
        ).pack(side="left")

    def _create_refinement_section(self, parent: ctk.CTkFrame):
        """Create the transcription refinement section."""
        self.refinement_desc_label = self.create_helper_text(
            "Post-processing options for voice input transcription.",
            parent=parent,
        )
        self.refinement_desc_label.pack(anchor="w", pady=(0, SPACING_SM))

        self.stt_capitalize_var = ctk.BooleanVar(value=self.settings.get("stt_capitalize", True))
        self.stt_capitalize_check = ctk.CTkCheckBox(
            parent,
            text="Capitalize first letter of transcription",
            variable=self.stt_capitalize_var,
            font=ctk.CTkFont(size=FONT_MD),
        )
        self.stt_capitalize_check.pack(anchor="w", pady=SPACING_BASE)

        self.stt_add_punctuation_var = ctk.BooleanVar(
            value=self.settings.get("stt_add_punctuation", False)
        )
        self.stt_add_punctuation_check = ctk.CTkCheckBox(
            parent,
            text="Add period if no trailing punctuation",
            variable=self.stt_add_punctuation_var,
            font=ctk.CTkFont(size=FONT_MD),
        )
        self.stt_add_punctuation_check.pack(anchor="w", pady=SPACING_BASE)

        self.stt_apply_abbreviations_var = ctk.BooleanVar(
            value=self.settings.get("stt_apply_abbreviations", False)
        )
        self.stt_apply_abbreviations_check = ctk.CTkCheckBox(
            parent,
            text="Apply abbreviation expansions to voice input",
            variable=self.stt_apply_abbreviations_var,
            font=ctk.CTkFont(size=FONT_MD),
        )
        self.stt_apply_abbreviations_check.pack(anchor="w", pady=SPACING_BASE)

        self.stt_abbreviations_hint_label = self.create_helper_text(
            "Uses the abbreviations defined in the Abbreviations tab.",
            parent=parent,
        )
        self.stt_abbreviations_hint_label.pack(anchor="w", pady=(0, SPACING_SM))

    def _create_preprocessing_section(self, parent: ctk.CTkFrame):
        """Create the audio pre-processing section."""
        self.preprocessing_desc_label = self.create_helper_text(
            "Audio processing applied before transcription to improve accuracy.",
            parent=parent,
        )
        self.preprocessing_desc_label.pack(anchor="w", pady=(0, SPACING_SM))

        self.stt_highpass_filter_var = ctk.BooleanVar(
            value=self.settings.get("stt_highpass_filter", True)
        )
        self.stt_highpass_filter_check = ctk.CTkCheckBox(
            parent,
            text="Apply noise filter (high-pass 80Hz)",
            variable=self.stt_highpass_filter_var,
            font=ctk.CTkFont(size=FONT_MD),
        )
        self.stt_highpass_filter_check.pack(anchor="w", pady=SPACING_BASE)

        self.highpass_hint_label = self.create_helper_text(
            "Reduces low-frequency rumble and background noise.",
            parent=parent,
        )
        self.highpass_hint_label.pack(anchor="w", pady=(0, SPACING_SM))

        ctk.CTkLabel(
            parent,
            text="Minimum Recording Duration:",
            font=ctk.CTkFont(size=FONT_MD),
        ).pack(anchor="w", pady=(SPACING_SM, SPACING_BASE))

        min_duration_frame = ctk.CTkFrame(parent, fg_color="transparent")
        min_duration_frame.pack(fill="x", pady=SPACING_BASE)

        self.stt_min_duration_var = ctk.IntVar(value=self.settings.get("stt_min_duration_ms", 300))
        self.stt_min_duration_slider = ctk.CTkSlider(
            min_duration_frame,
            from_=100,
            to=1000,
            number_of_steps=90,
            variable=self.stt_min_duration_var,
            command=self._on_stt_min_duration_change,
            width=400,
        )
        self.stt_min_duration_slider.pack(side="left", fill="x", expand=True, padx=(0, SPACING_BASE))

        self.stt_min_duration_value_label = ctk.CTkLabel(
            min_duration_frame,
            text=f"{self.stt_min_duration_var.get()}ms",
            font=ctk.CTkFont(size=FONT_MD),
            width=60,
        )
        self.stt_min_duration_value_label.pack(side="right")

        self.min_duration_hint_label = self.create_helper_text(
            "Recordings shorter than this are rejected as accidental clicks.",
            parent=parent,
        )
        self.min_duration_hint_label.pack(anchor="w", pady=(0, SPACING_SM))

        ctk.CTkLabel(
            parent,
            text="Silence Threshold:",
            font=ctk.CTkFont(size=FONT_MD),
        ).pack(anchor="w", pady=(SPACING_SM, SPACING_BASE))

        silence_threshold_frame = ctk.CTkFrame(parent, fg_color="transparent")
        silence_threshold_frame.pack(fill="x", pady=SPACING_BASE)

        self.stt_silence_threshold_var = ctk.IntVar(
            value=self.settings.get("stt_silence_threshold", 200)
        )
        self.stt_silence_threshold_slider = ctk.CTkSlider(
            silence_threshold_frame,
            from_=50,
            to=1000,
            number_of_steps=190,
            variable=self.stt_silence_threshold_var,
            command=self._on_stt_silence_threshold_change,
            width=400,
        )
        self.stt_silence_threshold_slider.pack(side="left", fill="x", expand=True, padx=(0, SPACING_BASE))

        self.stt_silence_threshold_value_label = ctk.CTkLabel(
            silence_threshold_frame,
            text=str(self.stt_silence_threshold_var.get()),
            font=ctk.CTkFont(size=FONT_MD),
            width=60,
        )
        self.stt_silence_threshold_value_label.pack(side="right")

        self.silence_threshold_hint_label = self.create_helper_text(
            "RMS threshold for silence detection. Higher values require louder audio.",
            parent=parent,
        )
        self.silence_threshold_hint_label.pack(anchor="w", pady=(0, SPACING_SM))

        ctk.CTkLabel(
            parent,
            text="Minimum Confidence Threshold:",
            font=ctk.CTkFont(size=FONT_MD),
        ).pack(anchor="w", pady=(SPACING_SM, SPACING_BASE))

        confidence_frame = ctk.CTkFrame(parent, fg_color="transparent")
        confidence_frame.pack(fill="x", pady=SPACING_BASE)

        current_confidence = int(self.settings.get("stt_confidence_threshold", 0.0) * 100)
        self.stt_confidence_threshold_var = ctk.IntVar(value=current_confidence)
        self.stt_confidence_threshold_slider = ctk.CTkSlider(
            confidence_frame,
            from_=0,
            to=100,
            number_of_steps=100,
            variable=self.stt_confidence_threshold_var,
            command=self._on_stt_confidence_change,
            width=400,
        )
        self.stt_confidence_threshold_slider.pack(side="left", fill="x", expand=True, padx=(0, SPACING_BASE))

        self.stt_confidence_threshold_value_label = ctk.CTkLabel(
            confidence_frame,
            text=f"{current_confidence}%",
            font=ctk.CTkFont(size=FONT_MD),
            width=60,
        )
        self.stt_confidence_threshold_value_label.pack(side="right")

        self.confidence_hint_label = self.create_helper_text(
            "Reject transcriptions with confidence below this threshold. 0% = disabled.",
            parent=parent,
        )
        self.confidence_hint_label.pack(anchor="w", pady=(0, SPACING_SM))

    def _create_corrections_section(self, parent: ctk.CTkFrame):
        """Create the word corrections section."""
        self.corrections_desc_label = self.create_helper_text(
            "Fix recurring misrecognitions. For example, map 'critts' to 'CriTTS'.",
            parent=parent,
        )
        self.corrections_desc_label.pack(anchor="w", pady=(0, SPACING_SM))

        self.corrections_text = ctk.CTkTextbox(
            parent,
            wrap="word",
            font=ctk.CTkFont(size=FONT_MD),
            height=100,
            **self.get_input_surface_style(),
        )
        self.corrections_text.pack(fill="x", pady=(0, SPACING_SM))

        corrections_dict = self.settings.get("stt_corrections", {})
        if corrections_dict:
            formatted_lines = [f"{key}={value}" for key, value in sorted(corrections_dict.items())]
            self.corrections_text.insert("1.0", "\n".join(formatted_lines))

        self.corrections_hint_label = self.create_helper_text(
            "Format: word=correction (one per line). Case-insensitive matching.",
            parent=parent,
        )
        self.corrections_hint_label.pack(anchor="w")

        self._load_input_devices()

    def _load_input_devices(self):
        """Load audio input devices (microphones)."""
        if not self.audio_router:
            self.stt_mic_device_dropdown.configure(values=["No audio router"])
            self.stt_mic_device_var.set("No audio router")
            return

        input_devices = self.audio_router.get_input_devices()
        self._input_devices = [{"index": None, "name": "Default (System)"}] + input_devices

        device_names = [device.get("name", "Unknown") for device in self._input_devices]
        self.stt_mic_device_dropdown.configure(values=device_names)

        saved_index = self.settings.get("stt_mic_device_index")
        if saved_index is not None:
            for device in self._input_devices:
                if device.get("index") == saved_index:
                    self.stt_mic_device_var.set(device.get("name", "Default (System)"))
                    break
            else:
                self.stt_mic_device_var.set("Default (System)")
        else:
            self.stt_mic_device_var.set("Default (System)")

    def _on_stt_min_duration_change(self, value):
        """Update minimum duration label when slider changes."""
        self.stt_min_duration_value_label.configure(text=f"{int(value)}ms")

    def _on_stt_silence_threshold_change(self, value):
        """Update silence threshold label when slider changes."""
        self.stt_silence_threshold_value_label.configure(text=str(int(value)))

    def _on_stt_confidence_change(self, value):
        """Update confidence threshold label when slider changes."""
        self.stt_confidence_threshold_value_label.configure(text=f"{int(value)}%")

    def _parse_corrections(self, text: str) -> Dict[str, str]:
        """Parse corrections text into a dictionary."""
        parsed = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            parts = line.split("=", 1)
            if len(parts) == 2:
                key = parts[0].strip()
                value = parts[1].strip()
                if key and value:
                    parsed[key] = value
        return parsed

    def get_settings(self) -> Dict[str, Any]:
        """Get current settings from the tab UI."""
        settings = {
            "speak_mode": "current_line" if self.speak_mode_current_line_var.get() else "all_text",
            "auto_language_detection": self.auto_language_var.get(),
            "stt_language": self.stt_language_var.get(),
            "stt_auto_speak": self.stt_auto_speak_var.get(),
            "stt_capitalize": self.stt_capitalize_var.get(),
            "stt_add_punctuation": self.stt_add_punctuation_var.get(),
            "stt_apply_abbreviations": self.stt_apply_abbreviations_var.get(),
            "stt_highpass_filter": self.stt_highpass_filter_var.get(),
            "stt_min_duration_ms": self.stt_min_duration_var.get(),
            "stt_silence_threshold": self.stt_silence_threshold_var.get(),
            "stt_confidence_threshold": self.stt_confidence_threshold_var.get() / 100.0,
            "stt_corrections": self._parse_corrections(self.corrections_text.get("1.0", "end-1c")),
        }

        selected_mic_name = self.stt_mic_device_var.get()
        for device in self._input_devices:
            if device.get("name") == selected_mic_name:
                settings["stt_mic_device_index"] = device.get("index")
                break

        return settings

    def validate(self) -> List[str]:
        """Validate the tab's settings."""
        errors = []

        threshold = self.stt_silence_threshold_var.get()
        if threshold < 0:
            errors.append(f"Silence threshold must be non-negative: {threshold}")

        confidence = self.stt_confidence_threshold_var.get()
        if not (0 <= confidence <= 100):
            errors.append(f"Confidence threshold out of range (0-100): {confidence}")

        return errors
