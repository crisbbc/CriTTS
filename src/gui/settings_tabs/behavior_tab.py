"""
Behavior Tab
Settings for speak mode, auto language detection, and STT options.
"""
import customtkinter as ctk
from typing import Any, Callable, Optional, List, Dict

from .base_tab import BaseTab
from ..theme_constants import (
    FONT_SM, FONT_MD, FONT_LG, FONT_WEIGHT_BOLD,
)


class BehaviorTab(BaseTab):
    """Tab for behavior and STT settings."""
    
    def _create_content(self):
        """Create the behavior tab content."""
        self.scroll = ctk.CTkScrollableFrame(self.tab)
        self.scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Behavior Section
        ctk.CTkLabel(
            self.scroll,
            text="Behavior",
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD)
        ).pack(anchor="w", pady=(10, 5))
        
        self.behavior_desc_label = ctk.CTkLabel(
            self.scroll,
            text="Choose which text is sent to TTS when you press Speak.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550
        )
        self.behavior_desc_label.pack(anchor="w", pady=(0, 10))
        self.add_wraplength_label(self.behavior_desc_label)
        
        speak_mode = self.settings.get("speak_mode", "current_line")
        self.speak_mode_current_line_var = ctk.BooleanVar(value=(speak_mode == "current_line"))
        self.speak_mode_check = ctk.CTkCheckBox(
            self.scroll,
            text="Speak current line only (cursor line); when unchecked, speak all text",
            variable=self.speak_mode_current_line_var,
            font=ctk.CTkFont(size=FONT_MD)
        )
        self.speak_mode_check.pack(anchor="w", pady=5)
        
        self.behavior_speak_mode_hint_label = ctk.CTkLabel(
            self.scroll,
            text="Current line: only the line where the cursor is will be spoken. All text: entire textbox.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550
        )
        self.behavior_speak_mode_hint_label.pack(anchor="w", pady=(5, 10))
        self.add_wraplength_label(self.behavior_speak_mode_hint_label)
        
        # Auto language detection
        self.auto_language_var = ctk.BooleanVar(value=self.settings.get("auto_language_detection", False))
        self.auto_language_check = ctk.CTkCheckBox(
            self.scroll,
            text="Auto-select voice based on text language",
            variable=self.auto_language_var,
            font=ctk.CTkFont(size=FONT_MD)
        )
        self.auto_language_check.pack(anchor="w", pady=5)
        
        self.behavior_auto_lang_desc_label = ctk.CTkLabel(
            self.scroll,
            text="When enabled, the system will automatically detect the language of your text and select the most appropriate voice.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550
        )
        self.behavior_auto_lang_desc_label.pack(anchor="w", pady=(0, 10))
        self.add_wraplength_label(self.behavior_auto_lang_desc_label)
        
        self.create_separator(self.scroll).pack(fill="x", pady=15)
        
        # Text Transcription Section
        self._create_transcription_section()
        
        # Audio Pre-processing Section
        self._create_preprocessing_section()
        
        # Word Corrections Section
        self._create_corrections_section()
    
    def _create_transcription_section(self):
        """Create the text transcription section."""
        ctk.CTkLabel(
            self.scroll,
            text="Text Transcription",
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD)
        ).pack(anchor="w", pady=(10, 5))
        
        self.transcription_desc_label = ctk.CTkLabel(
            self.scroll,
            text="Settings for voice input and automatic speech-to-text behaviour.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550
        )
        self.transcription_desc_label.pack(anchor="w", pady=(0, 10))
        self.add_wraplength_label(self.transcription_desc_label)
        
        # Auto-speak after transcription
        self.stt_auto_speak_var = ctk.BooleanVar(value=self.settings.get("stt_auto_speak", False))
        self.stt_auto_speak_check = ctk.CTkCheckBox(
            self.scroll,
            text="Automatically speak transcribed text",
            variable=self.stt_auto_speak_var,
            font=ctk.CTkFont(size=FONT_MD)
        )
        self.stt_auto_speak_check.pack(anchor="w", pady=5)
        
        self.stt_auto_speak_desc_label = ctk.CTkLabel(
            self.scroll,
            text="When enabled, text from voice input will be automatically spoken after transcription completes.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550
        )
        self.stt_auto_speak_desc_label.pack(anchor="w", pady=(0, 10))
        self.add_wraplength_label(self.stt_auto_speak_desc_label)
        
        # Voice Input Language
        ctk.CTkLabel(
            self.scroll,
            text="Voice Input Language:",
            font=ctk.CTkFont(size=FONT_MD, weight=FONT_WEIGHT_BOLD)
        ).pack(anchor="w", pady=(10, 5))
        
        self.stt_language_info_label = ctk.CTkLabel(
            self.scroll,
            text="Language for speech recognition when using the Voice Input button.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550
        )
        self.stt_language_info_label.pack(anchor="w", pady=(0, 10))
        self.add_wraplength_label(self.stt_language_info_label)
        
        stt_language_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        stt_language_frame.pack(fill="x", pady=5)
        
        self.stt_language_var = ctk.StringVar(value=self.settings.get("stt_language", "en-US"))
        self.stt_language_dropdown = ctk.CTkOptionMenu(
            stt_language_frame,
            variable=self.stt_language_var,
            values=[
                "en-US", "en-GB", "es-ES", "fr-FR", "de-DE", 
                "it-IT", "pt-BR", "ru-RU", "zh-CN", "ja-JP", 
                "ko-KR", "ar-SA", "hi-IN", "nl-NL", "pl-PL"
            ],
            font=ctk.CTkFont(size=FONT_MD),
            width=200
        )
        self.stt_language_dropdown.pack(side="left", padx=5)
        
        # Voice Input Device
        ctk.CTkLabel(
            self.scroll,
            text="Voice Input Device:",
            font=ctk.CTkFont(size=FONT_MD, weight=FONT_WEIGHT_BOLD)
        ).pack(anchor="w", pady=(10, 5))
        
        self.mic_device_info_label = ctk.CTkLabel(
            self.scroll,
            text="Microphone used for voice input. Leave as 'Default' to use the system default.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550
        )
        self.mic_device_info_label.pack(anchor="w", pady=(0, 10))
        self.add_wraplength_label(self.mic_device_info_label)
        
        mic_device_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        mic_device_frame.pack(fill="x", pady=5)
        
        self._input_devices: List[Dict] = []
        self.stt_mic_device_var = ctk.StringVar()
        self.stt_mic_device_dropdown = ctk.CTkComboBox(
            mic_device_frame,
            variable=self.stt_mic_device_var,
            values=["Loading..."],
            font=ctk.CTkFont(size=FONT_MD),
            dropdown_font=ctk.CTkFont(size=FONT_SM),
            width=400,
            state="readonly"
        )
        self.stt_mic_device_dropdown.pack(side="left", padx=5)
        
        ctk.CTkButton(
            mic_device_frame,
            text="Refresh",
            font=ctk.CTkFont(size=FONT_MD),
            command=self._load_input_devices,
            height=32,
            width=80
        ).pack(side="left", padx=5)
        
        self.create_separator(self.scroll).pack(fill="x", pady=15)
        
        # Transcription Refinement
        ctk.CTkLabel(
            self.scroll,
            text="Transcription Refinement",
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD)
        ).pack(anchor="w", pady=(10, 5))
        
        self.refinement_desc_label = ctk.CTkLabel(
            self.scroll,
            text="Post-processing options for voice input transcription.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550
        )
        self.refinement_desc_label.pack(anchor="w", pady=(0, 10))
        self.add_wraplength_label(self.refinement_desc_label)
        
        self.stt_capitalize_var = ctk.BooleanVar(value=self.settings.get("stt_capitalize", True))
        self.stt_capitalize_check = ctk.CTkCheckBox(
            self.scroll,
            text="Capitalize first letter of transcription",
            variable=self.stt_capitalize_var,
            font=ctk.CTkFont(size=FONT_MD)
        )
        self.stt_capitalize_check.pack(anchor="w", pady=5)
        
        self.stt_add_punctuation_var = ctk.BooleanVar(value=self.settings.get("stt_add_punctuation", False))
        self.stt_add_punctuation_check = ctk.CTkCheckBox(
            self.scroll,
            text="Add period if no trailing punctuation",
            variable=self.stt_add_punctuation_var,
            font=ctk.CTkFont(size=FONT_MD)
        )
        self.stt_add_punctuation_check.pack(anchor="w", pady=5)
        
        self.stt_apply_abbreviations_var = ctk.BooleanVar(value=self.settings.get("stt_apply_abbreviations", False))
        self.stt_apply_abbreviations_check = ctk.CTkCheckBox(
            self.scroll,
            text="Apply abbreviation expansions to voice input",
            variable=self.stt_apply_abbreviations_var,
            font=ctk.CTkFont(size=FONT_MD)
        )
        self.stt_apply_abbreviations_check.pack(anchor="w", pady=5)
        
        self.stt_abbreviations_hint_label = ctk.CTkLabel(
            self.scroll,
            text="Uses the abbreviations defined in the Abbreviations tab.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550
        )
        self.stt_abbreviations_hint_label.pack(anchor="w", pady=(0, 10))
        self.add_wraplength_label(self.stt_abbreviations_hint_label)
    
    def _create_preprocessing_section(self):
        """Create the audio pre-processing section."""
        self.create_separator(self.scroll).pack(fill="x", pady=15)
        
        ctk.CTkLabel(
            self.scroll,
            text="Audio Pre-processing",
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD)
        ).pack(anchor="w", pady=(10, 5))
        
        self.preprocessing_desc_label = ctk.CTkLabel(
            self.scroll,
            text="Audio processing applied before transcription to improve accuracy.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550
        )
        self.preprocessing_desc_label.pack(anchor="w", pady=(0, 10))
        self.add_wraplength_label(self.preprocessing_desc_label)
        
        # High-pass filter
        self.stt_highpass_filter_var = ctk.BooleanVar(value=self.settings.get("stt_highpass_filter", True))
        self.stt_highpass_filter_check = ctk.CTkCheckBox(
            self.scroll,
            text="Apply noise filter (high-pass 80Hz)",
            variable=self.stt_highpass_filter_var,
            font=ctk.CTkFont(size=FONT_MD)
        )
        self.stt_highpass_filter_check.pack(anchor="w", pady=5)
        
        self.highpass_hint_label = ctk.CTkLabel(
            self.scroll,
            text="Reduces low-frequency rumble and background noise.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550
        )
        self.highpass_hint_label.pack(anchor="w", pady=(0, 10))
        self.add_wraplength_label(self.highpass_hint_label)
        
        # Minimum duration slider
        ctk.CTkLabel(
            self.scroll,
            text="Minimum Recording Duration:",
            font=ctk.CTkFont(size=FONT_MD)
        ).pack(anchor="w", pady=(10, 5))
        
        min_duration_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        min_duration_frame.pack(fill="x", pady=5)
        
        self.stt_min_duration_var = ctk.IntVar(value=self.settings.get("stt_min_duration_ms", 300))
        self.stt_min_duration_slider = ctk.CTkSlider(
            min_duration_frame,
            from_=100,
            to=1000,
            number_of_steps=90,
            variable=self.stt_min_duration_var,
            command=self._on_stt_min_duration_change,
            width=400
        )
        self.stt_min_duration_slider.pack(side="left", fill="x", expand=True, padx=5)
        
        self.stt_min_duration_value_label = ctk.CTkLabel(
            min_duration_frame,
            text=f"{self.stt_min_duration_var.get()}ms",
            font=ctk.CTkFont(size=FONT_MD),
            width=60
        )
        self.stt_min_duration_value_label.pack(side="right", padx=5)
        
        self.min_duration_hint_label = ctk.CTkLabel(
            self.scroll,
            text="Recordings shorter than this are rejected as accidental clicks.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550
        )
        self.min_duration_hint_label.pack(anchor="w", pady=(0, 10))
        self.add_wraplength_label(self.min_duration_hint_label)
        
        # Silence threshold slider
        ctk.CTkLabel(
            self.scroll,
            text="Silence Threshold:",
            font=ctk.CTkFont(size=FONT_MD)
        ).pack(anchor="w", pady=(10, 5))
        
        silence_threshold_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        silence_threshold_frame.pack(fill="x", pady=5)
        
        self.stt_silence_threshold_var = ctk.IntVar(value=self.settings.get("stt_silence_threshold", 200))
        self.stt_silence_threshold_slider = ctk.CTkSlider(
            silence_threshold_frame,
            from_=50,
            to=1000,
            number_of_steps=190,
            variable=self.stt_silence_threshold_var,
            command=self._on_stt_silence_threshold_change,
            width=400
        )
        self.stt_silence_threshold_slider.pack(side="left", fill="x", expand=True, padx=5)
        
        self.stt_silence_threshold_value_label = ctk.CTkLabel(
            silence_threshold_frame,
            text=str(self.stt_silence_threshold_var.get()),
            font=ctk.CTkFont(size=FONT_MD),
            width=60
        )
        self.stt_silence_threshold_value_label.pack(side="right", padx=5)
        
        self.silence_threshold_hint_label = ctk.CTkLabel(
            self.scroll,
            text="RMS threshold for silence detection. Higher values require louder audio.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550
        )
        self.silence_threshold_hint_label.pack(anchor="w", pady=(0, 10))
        self.add_wraplength_label(self.silence_threshold_hint_label)
        
        # Confidence threshold slider
        ctk.CTkLabel(
            self.scroll,
            text="Minimum Confidence Threshold:",
            font=ctk.CTkFont(size=FONT_MD)
        ).pack(anchor="w", pady=(10, 5))
        
        confidence_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        confidence_frame.pack(fill="x", pady=5)
        
        current_confidence = int(self.settings.get("stt_confidence_threshold", 0.0) * 100)
        self.stt_confidence_threshold_var = ctk.IntVar(value=current_confidence)
        self.stt_confidence_threshold_slider = ctk.CTkSlider(
            confidence_frame,
            from_=0,
            to=100,
            number_of_steps=100,
            variable=self.stt_confidence_threshold_var,
            command=self._on_stt_confidence_change,
            width=400
        )
        self.stt_confidence_threshold_slider.pack(side="left", fill="x", expand=True, padx=5)
        
        self.stt_confidence_threshold_value_label = ctk.CTkLabel(
            confidence_frame,
            text=f"{current_confidence}%",
            font=ctk.CTkFont(size=FONT_MD),
            width=60
        )
        self.stt_confidence_threshold_value_label.pack(side="right", padx=5)
        
        self.confidence_hint_label = ctk.CTkLabel(
            self.scroll,
            text="Reject transcriptions with confidence below this threshold. 0% = disabled.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550
        )
        self.confidence_hint_label.pack(anchor="w", pady=(0, 10))
        self.add_wraplength_label(self.confidence_hint_label)
    
    def _create_corrections_section(self):
        """Create the word corrections section."""
        self.create_separator(self.scroll).pack(fill="x", pady=15)
        
        ctk.CTkLabel(
            self.scroll,
            text="Word Corrections",
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD)
        ).pack(anchor="w", pady=(10, 5))
        
        self.corrections_desc_label = ctk.CTkLabel(
            self.scroll,
            text="Fix recurring misrecognitions. For example, map 'critts' to 'CriTTS'.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550
        )
        self.corrections_desc_label.pack(anchor="w", pady=(0, 10))
        self.add_wraplength_label(self.corrections_desc_label)
        
        self.corrections_text = ctk.CTkTextbox(
            self.scroll,
            wrap="word",
            font=ctk.CTkFont(size=FONT_MD),
            height=100
        )
        self.corrections_text.pack(fill="x", pady=5)
        
        # Load existing corrections
        corrections_dict = self.settings.get("stt_corrections", {})
        if corrections_dict:
            formatted_lines = [f"{k}={v}" for k, v in sorted(corrections_dict.items())]
            self.corrections_text.insert("1.0", "\n".join(formatted_lines))
        
        self.corrections_hint_label = ctk.CTkLabel(
            self.scroll,
            text="Format: word=correction (one per line). Case-insensitive matching.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550
        )
        self.corrections_hint_label.pack(anchor="w", pady=(0, 10))
        self.add_wraplength_label(self.corrections_hint_label)
        
        # Load input devices
        self._load_input_devices()
    
    def _load_input_devices(self):
        """Load audio input devices (microphones)."""
        if not self.audio_router:
            self.stt_mic_device_dropdown.configure(values=["No audio router"])
            self.stt_mic_device_var.set("No audio router")
            return
        
        input_devices = self.audio_router.get_input_devices()
        self._input_devices = [{"index": None, "name": "Default (System)"}] + input_devices
        
        device_names = [d.get("name", "Unknown") for d in self._input_devices]
        self.stt_mic_device_dropdown.configure(values=device_names)
        
        # Restore saved STT device
        saved_index = self.settings.get("stt_mic_device_index")
        if saved_index is not None:
            for d in self._input_devices:
                if d.get("index") == saved_index:
                    self.stt_mic_device_var.set(d.get("name", "Default (System)"))
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
        
        # Get STT mic device index
        selected_mic_name = self.stt_mic_device_var.get()
        for d in self._input_devices:
            if d.get("name") == selected_mic_name:
                settings["stt_mic_device_index"] = d.get("index")
                break
        
        return settings
    
    def validate(self) -> List[str]:
        """Validate the tab's settings."""
        errors = []
        
        # Validate silence threshold
        threshold = self.stt_silence_threshold_var.get()
        if threshold < 0:
            errors.append(f"Silence threshold must be non-negative: {threshold}")
        
        # Validate confidence threshold
        confidence = self.stt_confidence_threshold_var.get()
        if not (0 <= confidence <= 100):
            errors.append(f"Confidence threshold out of range (0-100): {confidence}")
        
        return errors