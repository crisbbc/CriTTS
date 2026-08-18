"""
Audio Output Tab
Settings for audio output devices, normalization, and microphone passthrough.
"""
import sys
import threading
import customtkinter as ctk
from typing import Any, List, Dict

from .base_tab import BaseTab
from ..theme_constants import BUTTON_HEIGHT, FONT_SM, FONT_MD


class AudioOutputTab(BaseTab):
    """Tab for audio output settings."""

    def _create_content(self):
        """Create the audio output tab content."""
        self.setup_layout()

        output_section, output_content = self.create_section_surface("Playback Device")
        output_section.pack(fill="x", pady=(0, 15))

        self._platform = self._detect_platform()
        self.output_device_info_label = self.create_helper_text(
            self._get_playback_device_info_text(),
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

        # Linux-only: PulseAudio sink auto-routing
        if self._platform == "linux":
            sink_section, sink_content = self.create_section_surface("PulseAudio Sink Routing")
            sink_section.pack(fill="x", pady=(0, 15))
            self._create_sink_routing_section(sink_content)

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

    def _create_sink_routing_section(self, parent: ctk.CTkFrame):
        """Create the Linux PulseAudio sink auto-routing section."""
        sink_info = self.create_helper_text(
            "One-click setup: creates a null sink + virtual microphone "
            "so TTS audio is routed directly to Discord/VRChat. "
            "Cleanup on app exit is automatic.",
            parent=parent,
        )
        sink_info.pack(anchor="w", pady=(0, 10))

        # Hidden var to track the sink name for settings
        self.sink_name_var = ctk.StringVar(
            value=self.settings.get("linux_sink_name", "")
        )

        # Button row
        button_frame = ctk.CTkFrame(parent, fg_color="transparent")
        button_frame.pack(anchor="w", pady=(0, 6))

        self.create_sink_button = ctk.CTkButton(
            button_frame,
            text="🔧 Create Null Sink",
            font=ctk.CTkFont(size=FONT_MD),
            command=self._create_null_sink,
            height=BUTTON_HEIGHT,
        )
        self.create_sink_button.pack(side="left", padx=(0, 8))

        self.cleanup_sink_button = ctk.CTkButton(
            button_frame,
            text="🗑 Remove",
            font=ctk.CTkFont(size=FONT_MD),
            command=self._cleanup_null_sink,
            height=BUTTON_HEIGHT,
            fg_color="#e74c3c",
            hover_color="#c0392b",
        )
        self.cleanup_sink_button.pack(side="left")

        self.sink_status_label = self.create_helper_text(
            "",
            parent=parent,
        )
        self.sink_status_label.pack(anchor="w")

    def _create_null_sink(self):
        """One-click setup: create null sink + virtual mic with a fixed name.

        Uses the hardcoded name ``crittssink`` so the user never needs to
        type anything.  The virtual mic appears as "CriTTS_Virtual_Mic" in
        Discord's input device list.  The pactl work lives in
        ``AudioRouter.ensure_linux_sink_modules`` so the startup auto-setup
        and this button share one idempotent implementation.
        """
        sink_name = "crittssink"
        self.sink_name_var.set(sink_name)

        self.create_sink_button.configure(state="disabled", text="⏳ Creating...")
        self.cleanup_sink_button.configure(state="disabled")
        self.sink_status_label.configure(text="")

        def _run():
            try:
                if self.audio_router is None:
                    self._after_sink_result(
                        "⚠ Audio router not available.", error=True
                    )
                    return
                ok, message = self.audio_router.ensure_linux_sink_modules(sink_name)
                self._after_sink_result(message, error=not ok)
            except Exception as e:
                self._after_sink_result(f"❌ Unexpected error: {e}", error=True)

        threading.Thread(target=_run, daemon=True).start()

    def _cleanup_null_sink(self):
        """Remove the null sink and virtual mic modules created by CriTTS."""
        self.cleanup_sink_button.configure(state="disabled", text="⏳ Removing...")
        self.create_sink_button.configure(state="disabled")

        def _run():
            try:
                # Delegate to AudioRouter for the actual pactl work
                if self.audio_router:
                    self.audio_router.cleanup_linux_sink_modules()
                self.sink_name_var.set("")
                self._after_sink_result(
                    "🗑 Removed CriTTS sink + virtual mic.", error=False
                )

            except Exception as e:
                self._after_sink_result(
                    f"❌ Cleanup error: {e}", error=True
                )

        threading.Thread(target=_run, daemon=True).start()

    def _after_sink_result(self, message: str, *, error: bool):
        """Schedule a UI update from the background thread."""
        def _apply():
            self.create_sink_button.configure(state="normal", text="🔧 Create Null Sink")
            self.cleanup_sink_button.configure(state="normal", text="🗑 Remove")
            color = "#e74c3c" if error else "#27ae60"
            self.sink_status_label.configure(text=message, text_color=color)
        try:
            if hasattr(self, "sink_status_label"):
                self.sink_status_label.after(0, _apply)
        except Exception:
            try:
                self.create_sink_button.configure(
                    state="normal", text="🔧 Create Null Sink"
                )
                self.cleanup_sink_button.configure(
                    state="normal", text="🗑 Remove"
                )
            except Exception:
                pass

    def _create_passthrough_section(self, parent: ctk.CTkFrame):
        """Create the microphone passthrough section."""
        passthrough_info = self.create_helper_text(
            self._get_passthrough_info_text(),
            parent=parent,
        )
        passthrough_info.pack(anchor="w", pady=(0, 10))

        self.mic_passthrough_enabled_var = ctk.BooleanVar(
            value=self.settings.get("mic_passthrough_enabled", False)
        )
        self.mic_passthrough_enabled_check = ctk.CTkCheckBox(
            parent,
            text=self._get_passthrough_checkbox_text(),
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
            self._get_passthrough_output_hint_text(),
            parent=parent,
        )
        self.passthrough_output_hint_label.pack(anchor="w")

    @staticmethod
    def _detect_platform() -> str:
        """Return 'linux', 'windows', 'macos', or 'unknown'."""
        if sys.platform.startswith("linux"):
            return "linux"
        if sys.platform == "win32":
            return "windows"
        if sys.platform == "darwin":
            return "macos"
        return "unknown"

    def _get_playback_device_info_text(self) -> str:
        """Return platform-appropriate info text for the playback device section."""
        if self._platform == "linux":
            audio_system = "PipeWire"
            if self.audio_router:
                detected = self.audio_router.detect_linux_audio_system()
                if detected == "pulseaudio":
                    audio_system = "PulseAudio"
                elif detected == "pipewire":
                    audio_system = "PipeWire"
            return (
                f"Select \"default\" (or \"pulse\"/\"pipewire\") — "
                f"{audio_system} aggregates all sinks into a single ALSA device, "
                f"so individual virtual sinks won't appear here. "
                f"Use pavucontrol or pactl move-sink-input to redirect TTS audio to a null sink. "
                f"See README for detailed setup instructions."
            )
        elif self._platform == "macos":
            return (
                "Select where TTS audio should play. To route TTS to VRChat/Discord, "
                "install BlackHole or Loopback and select it here."
            )
        # Windows
        return (
            "Select where TTS audio should play. Only VB-Cable virtual audio devices are shown — "
            "TTS audio passes through the cable and appears as a microphone in VRChat/Discord."
        )

    def _load_devices(self):
        """Load audio output devices."""
        all_devices = self.audio_router.get_audio_devices() if self.audio_router else []

        # Safe fallback: if _create_content hasn't run yet (e.g. tests),
        # detect platform on demand.
        platform = getattr(self, "_platform", None) or self._detect_platform()

        if platform == "windows":
            vbcable_keywords = ["cable", "vb-audio", "vbaudio", "vb cable"]
            self._devices = [
                device
                for device in all_devices
                if any(keyword in device.get("name", "").lower() for keyword in vbcable_keywords)
            ]
        else:
            # Linux/macOS: show all output devices
            self._devices = all_devices

        if not self._devices:
            self._platform = platform  # ensure _platform is set for helper methods
            warning_msg = self._get_no_devices_warning()
            self.configure_surface_status_label(
                self.vbcable_warning_label,
                warning_msg,
                "warning",
            )
            placeholder = self._get_no_devices_placeholder()
            self.device_dropdown.configure(values=[placeholder])
            self.device_var.set(placeholder)
            self.passthrough_output_dropdown.configure(values=[placeholder])
            self.passthrough_output_var.set(placeholder)
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

    def _get_no_devices_warning(self) -> str:
        """Return platform-appropriate warning when no devices are found."""
        if self._platform == "linux":
            audio_system = "PulseAudio/PipeWire"
            if self.audio_router:
                detected = self.audio_router.detect_linux_audio_system()
                if detected != "unknown":
                    audio_system = "PipeWire" if detected == "pipewire" else "PulseAudio"
            return (
                f"No audio output devices found. Check your {audio_system} configuration "
                f"and ensure sound is working on your system."
            )
        elif self._platform == "macos":
            return (
                "No audio output devices found. Check your system audio settings "
                "and ensure sound is working."
            )
        return (
            "No VB-Cable devices found. Please install VB-Cable from vb-audio.com "
            "to route TTS audio to VRChat/Discord."
        )

    def _get_no_devices_placeholder(self) -> str:
        """Return platform-appropriate placeholder when no devices are found."""
        if self._platform == "windows":
            return "No VB-Cable devices found"
        return "No audio devices found"

    def _get_passthrough_info_text(self) -> str:
        """Return platform-appropriate passthrough info text."""
        if self._platform == "windows":
            return (
                "Route your real microphone to VBCable at the same time as TTS. "
                "Useful for mixing your voice with TTS in VRChat/Discord."
            )
        return (
            "Route your real microphone to the selected output device alongside TTS. "
            "Useful for mixing your voice with TTS in VRChat/Discord."
        )

    def _get_passthrough_checkbox_text(self) -> str:
        """Return platform-appropriate passthrough checkbox text."""
        if self._platform == "windows":
            return "Enable microphone passthrough to VBCable"
        return "Enable microphone passthrough to output device"

    def _get_passthrough_output_hint_text(self) -> str:
        """Return platform-appropriate passthrough output hint."""
        if self._platform == "windows":
            return "Select the VBCable Input device so your mic audio is mixed with TTS."
        return (
            "Select the output device where your mic audio should be sent. "
            "Choose the same device as the main output for mixing."
        )

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

        if hasattr(self, "sink_name_var"):
            settings["linux_sink_name"] = self.sink_name_var.get().strip()

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
