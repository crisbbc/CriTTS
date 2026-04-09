"""
Audio Output Tab
Settings for audio output devices, normalization, and microphone passthrough.
"""
import customtkinter as ctk
from typing import Any, List, Dict

from .base_tab import BaseTab
from ..theme_constants import BUTTON_HEIGHT, FONT_SM, FONT_MD


class AudioOutputTab(BaseTab):
    """Tab for audio output settings."""

    def _create_content(self):
        """Create the audio output tab content."""
        self.setup_layout()

        output_section, output_content = self.create_section_surface("Output Device")
        output_section.pack(fill="x", pady=(0, 15))

        self.output_device_info_label = self.create_helper_text(
            "Only VB-Cable virtual audio devices are shown. TTS audio must pass through VB-Cable to appear as a microphone in VRChat/Discord.",
            parent=output_content,
        )
        self.output_device_info_label.pack(anchor="w", pady=(0, 8))

        self.device_var = ctk.StringVar()
        self.device_dropdown = ctk.CTkComboBox(
            output_content,
            variable=self.device_var,
            values=["Loading devices..."],
            font=ctk.CTkFont(size=FONT_MD),
            dropdown_font=ctk.CTkFont(size=FONT_SM),
            state="readonly",
        )
        self.device_dropdown.pack(fill="x", pady=(0, 8))
        self.device_dropdown.configure(command=lambda _: self._update_device_info())

        self.vbcable_warning_label = self.create_helper_text(
            "",
            parent=output_content,
            text_color=self.get_surface_status_text_color(),
        )
        self.vbcable_warning_label.pack(anchor="w", pady=(0, 12))

        self.refresh_devices_button = ctk.CTkButton(
            output_content,
            text="Refresh Device List",
            font=ctk.CTkFont(size=FONT_MD),
            command=self._load_devices,
            height=BUTTON_HEIGHT,
        )
        self.refresh_devices_button.pack(anchor="w")

        device_info_section, device_info_content = self.create_section_surface("Device Information")
        device_info_section.pack(fill="x", pady=(0, 15))

        self.device_info_text = ctk.CTkTextbox(
            device_info_content,
            font=ctk.CTkFont(size=FONT_SM),
            height=150,
            wrap="word",
            state="disabled",
            **self.get_input_surface_style(),
        )
        self.device_info_text.pack(fill="x")

        normalization_section, normalization_content = self.create_section_surface("Audio Normalization")
        normalization_section.pack(fill="x", pady=(0, 15))
        self._create_normalization_section(normalization_content)

        passthrough_section, passthrough_content = self.create_section_surface("Microphone Passthrough")
        passthrough_section.pack(fill="x")
        self._create_passthrough_section(passthrough_content)

        self._devices: List[Dict] = []
        self._input_devices: List[Dict] = []
        self._load_devices()

    def _create_normalization_section(self, parent: ctk.CTkFrame):
        """Create the audio normalization section."""
        norm_info = self.create_helper_text(
            "Normalization helps maintain consistent audio levels and prevents clipping.",
            parent=parent,
        )
        norm_info.pack(anchor="w", pady=(0, 10))

        ctk.CTkLabel(
            parent,
            text="Normalization Type:",
            font=ctk.CTkFont(size=FONT_MD),
        ).pack(anchor="w", pady=(5, 5))

        self.norm_var = ctk.StringVar(value=self.settings.get("normalization_type", "Peak"))
        self.norm_dropdown = ctk.CTkComboBox(
            parent,
            variable=self.norm_var,
            values=["Peak", "RMS", "LUFS", "None"],
            font=ctk.CTkFont(size=FONT_MD),
            state="readonly",
            width=200,
        )
        self.norm_dropdown.pack(anchor="w", pady=(0, 8))

        self.norm_types_label = self.create_helper_text(
            "Peak: Prevents clipping | RMS: Consistent loudness | LUFS: Professional standard | None: No processing",
            parent=parent,
        )
        self.norm_types_label.pack(anchor="w", pady=(0, 10))

        self.enable_norm_var = ctk.BooleanVar(value=self.settings.get("enable_normalization", True))
        self.enable_norm_check = ctk.CTkCheckBox(
            parent,
            text="Enable audio normalization",
            variable=self.enable_norm_var,
            font=ctk.CTkFont(size=FONT_MD),
        )
        self.enable_norm_check.pack(anchor="w")

    def _create_passthrough_section(self, parent: ctk.CTkFrame):
        """Create the microphone passthrough section."""
        passthrough_info = self.create_helper_text(
            "Route your real microphone to VBCable at the same time as TTS. Useful for mixing your voice with TTS in VRChat/Discord.",
            parent=parent,
        )
        passthrough_info.pack(anchor="w", pady=(0, 10))

        self.mic_passthrough_enabled_var = ctk.BooleanVar(
            value=self.settings.get("mic_passthrough_enabled", False)
        )
        self.mic_passthrough_enabled_check = ctk.CTkCheckBox(
            parent,
            text="Enable microphone passthrough to VBCable",
            variable=self.mic_passthrough_enabled_var,
            font=ctk.CTkFont(size=FONT_MD),
        )
        self.mic_passthrough_enabled_check.pack(anchor="w", pady=(0, 10))

        ctk.CTkLabel(
            parent,
            text="Passthrough Mic Device:",
            font=ctk.CTkFont(size=FONT_MD),
        ).pack(anchor="w", pady=(0, 5))

        passthrough_mic_frame = ctk.CTkFrame(parent, fg_color="transparent")
        passthrough_mic_frame.pack(fill="x", pady=(0, 10))

        self.passthrough_mic_var = ctk.StringVar()
        self.passthrough_mic_dropdown = ctk.CTkComboBox(
            passthrough_mic_frame,
            variable=self.passthrough_mic_var,
            values=["Loading..."],
            font=ctk.CTkFont(size=FONT_MD),
            dropdown_font=ctk.CTkFont(size=FONT_SM),
            width=400,
            state="readonly",
        )
        self.passthrough_mic_dropdown.pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            passthrough_mic_frame,
            text="Refresh",
            font=ctk.CTkFont(size=FONT_MD),
            command=self._load_input_devices,
            height=BUTTON_HEIGHT,
            width=80,
        ).pack(side="left")

        ctk.CTkLabel(
            parent,
            text="Passthrough Volume:",
            font=ctk.CTkFont(size=FONT_MD),
        ).pack(anchor="w", pady=(0, 5))

        passthrough_volume_frame = ctk.CTkFrame(parent, fg_color="transparent")
        passthrough_volume_frame.pack(fill="x", pady=(0, 4))

        self.passthrough_volume_var = ctk.IntVar(
            value=self.settings.get("mic_passthrough_volume", 100)
        )
        self.passthrough_volume_slider = ctk.CTkSlider(
            passthrough_volume_frame,
            from_=0,
            to=200,
            number_of_steps=200,
            variable=self.passthrough_volume_var,
            command=self._on_passthrough_volume_change,
            width=400,
        )
        self.passthrough_volume_slider.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.passthrough_volume_value_label = ctk.CTkLabel(
            passthrough_volume_frame,
            text=f"{self.passthrough_volume_var.get()}%",
            font=ctk.CTkFont(size=FONT_MD),
            width=50,
        )
        self.passthrough_volume_value_label.pack(side="right")

        self.passthrough_volume_info_label = self.create_helper_text(
            "Volume multiplier: 100% is normal, 200% doubles volume, 0% mutes.",
            parent=parent,
        )
        self.passthrough_volume_info_label.pack(anchor="w", pady=(0, 10))

        ctk.CTkLabel(
            parent,
            text="Passthrough Output Device:",
            font=ctk.CTkFont(size=FONT_MD),
        ).pack(anchor="w", pady=(0, 5))

        passthrough_output_frame = ctk.CTkFrame(parent, fg_color="transparent")
        passthrough_output_frame.pack(fill="x", pady=(0, 4))

        self.passthrough_output_var = ctk.StringVar()
        self.passthrough_output_dropdown = ctk.CTkComboBox(
            passthrough_output_frame,
            variable=self.passthrough_output_var,
            values=["Loading..."],
            font=ctk.CTkFont(size=FONT_MD),
            dropdown_font=ctk.CTkFont(size=FONT_SM),
            width=400,
            state="readonly",
        )
        self.passthrough_output_dropdown.pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            passthrough_output_frame,
            text="Refresh",
            font=ctk.CTkFont(size=FONT_MD),
            command=self._load_devices,
            height=BUTTON_HEIGHT,
            width=80,
        ).pack(side="left")

        self.passthrough_output_hint_label = self.create_helper_text(
            "Select the VBCable Input device so your mic audio is mixed with TTS.",
            parent=parent,
        )
        self.passthrough_output_hint_label.pack(anchor="w")

    def _load_devices(self):
        """Load audio output devices."""
        all_devices = self.audio_router.get_audio_devices() if self.audio_router else []

        vbcable_keywords = ["cable", "vb-audio", "vbaudio", "vb cable"]
        self._devices = [
            device
            for device in all_devices
            if any(keyword in device.get("name", "").lower() for keyword in vbcable_keywords)
        ]

        if not self._devices:
            self.configure_surface_status_label(
                self.vbcable_warning_label,
                "No VB-Cable devices found. Please install VB-Cable from vb-audio.com to route TTS audio to VRChat/Discord.",
                "warning",
            )
            self.device_dropdown.configure(values=["No VB-Cable devices found"])
            self.device_var.set("No VB-Cable devices found")
            self.passthrough_output_dropdown.configure(values=["No VB-Cable devices found"])
            self.passthrough_output_var.set("No VB-Cable devices found")
        else:
            self.vbcable_warning_label.configure(
                text="",
                text_color=self.get_surface_status_text_color(),
            )
            names = [device.get("name", "Unknown") for device in self._devices]
            self.device_dropdown.configure(values=names)

            saved_device_index = self.settings.get("device_index")
            found_saved = False
            for device in self._devices:
                if device.get("index") == saved_device_index:
                    self.device_var.set(device.get("name", "Unknown"))
                    found_saved = True
                    break

            if not found_saved and names:
                self.device_var.set(names[0])

            self.passthrough_output_dropdown.configure(values=names)

            saved_passthrough_output_index = self.settings.get("mic_passthrough_output_device_index")
            if saved_passthrough_output_index is not None:
                found_passthrough_output = False
                for device in self._devices:
                    if device.get("index") == saved_passthrough_output_index:
                        self.passthrough_output_var.set(device.get("name", "Unknown"))
                        found_passthrough_output = True
                        break
                if not found_passthrough_output and names:
                    cable_device = next(
                        (
                            device
                            for device in self._devices
                            if "cable" in device.get("name", "").lower()
                        ),
                        None,
                    )
                    self.passthrough_output_var.set(
                        cable_device["name"] if cable_device else names[0]
                    )
            else:
                cable_device = next(
                    (
                        device
                        for device in self._devices
                        if "cable" in device.get("name", "").lower()
                    ),
                    None,
                )
                self.passthrough_output_var.set(
                    cable_device["name"] if cable_device else (names[0] if names else "")
                )

        self._update_device_info()
        self._load_input_devices()

    def _load_input_devices(self):
        """Load audio input devices (microphones)."""
        if not self.audio_router:
            self.passthrough_mic_dropdown.configure(values=["No audio router"])
            self.passthrough_mic_var.set("No audio router")
            return

        input_devices = self.audio_router.get_input_devices()
        self._input_devices = [{"index": None, "name": "Default (System)"}] + input_devices

        device_names = [device.get("name", "Unknown") for device in self._input_devices]
        self.passthrough_mic_dropdown.configure(values=device_names)

        saved_passthrough_index = self.settings.get("mic_passthrough_device_index")
        if saved_passthrough_index is not None:
            for device in self._input_devices:
                if device.get("index") == saved_passthrough_index:
                    self.passthrough_mic_var.set(device.get("name", "Default (System)"))
                    break
            else:
                self.passthrough_mic_var.set("Default (System)")
        else:
            self.passthrough_mic_var.set("Default (System)")

    def _update_device_info(self):
        """Update the Device Information textbox."""
        device_name = self.device_var.get()
        device = None
        for candidate in self._devices:
            if candidate.get("name") == device_name:
                device = candidate
                break

        self.device_info_text.configure(state="normal")
        self.device_info_text.delete("1.0", "end")

        if device:
            lines = [
                f"Name: {device.get('name', '—')}",
                f"Index: {device.get('index', '—')}",
                f"Channels: {device.get('channels', '—')}",
                f"Sample rate: {device.get('sample_rate', '—')} Hz",
            ]
            self.device_info_text.insert("1.0", "\n".join(lines))
        else:
            self.device_info_text.insert("1.0", "No device selected or devices not loaded.")

        self.device_info_text.configure(state="disabled")

    def _on_passthrough_volume_change(self, value):
        """Update passthrough volume label when slider changes."""
        self.passthrough_volume_value_label.configure(text=f"{int(value)}%")

    def get_settings(self) -> Dict[str, Any]:
        """Get current settings from the tab UI."""
        settings = {
            "normalization_type": self.norm_var.get(),
            "enable_normalization": self.enable_norm_var.get(),
            "mic_passthrough_enabled": self.mic_passthrough_enabled_var.get(),
            "mic_passthrough_volume": self.passthrough_volume_var.get(),
        }

        device_name = self.device_var.get()
        for device in self._devices:
            if device.get("name") == device_name:
                settings["device_index"] = device.get("index")
                break

        selected_passthrough_mic_name = self.passthrough_mic_var.get()
        for device in self._input_devices:
            if device.get("name") == selected_passthrough_mic_name:
                settings["mic_passthrough_device_index"] = device.get("index")
                break

        selected_passthrough_output_name = self.passthrough_output_var.get()
        for device in self._devices:
            if device.get("name") == selected_passthrough_output_name:
                settings["mic_passthrough_output_device_index"] = device.get("index")
                break

        return settings

    def validate(self) -> List[str]:
        """Validate the tab's settings."""
        errors = []

        if self.norm_var.get() not in ["Peak", "RMS", "LUFS", "None"]:
            errors.append(f"Invalid normalization type: {self.norm_var.get()}")

        volume = self.passthrough_volume_var.get()
        if not (0 <= volume <= 200):
            errors.append(f"Passthrough volume out of range (0-200): {volume}")

        return errors
