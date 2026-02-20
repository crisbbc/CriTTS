"""
Audio Output Tab
Settings for audio output devices, normalization, and microphone passthrough.
"""
import customtkinter as ctk
from typing import Any, Callable, Optional, List, Dict

from .base_tab import BaseTab
from ..theme_constants import (
    FONT_SM, FONT_MD, FONT_LG, FONT_WEIGHT_BOLD,
)


class AudioOutputTab(BaseTab):
    """Tab for audio output settings."""
    
    def _create_content(self):
        """Create the audio output tab content."""
        self.scroll = ctk.CTkScrollableFrame(self.tab)
        self.scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Device selection
        ctk.CTkLabel(
            self.scroll,
            text="Output Device:",
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD)
        ).pack(anchor="w", pady=(10, 5))
        
        ctk.CTkLabel(
            self.scroll,
            text="Only VB-Cable virtual audio devices are shown. TTS audio must pass through VB-Cable to appear as a microphone in VRChat/Discord.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray"
        ).pack(anchor="w", pady=(0, 5))
        
        # Device dropdown
        self.device_var = ctk.StringVar()
        self.device_dropdown = ctk.CTkComboBox(
            self.scroll,
            variable=self.device_var,
            values=["Loading devices..."],
            font=ctk.CTkFont(size=FONT_MD),
            dropdown_font=ctk.CTkFont(size=FONT_SM),
            width=500,
            state="readonly"
        )
        self.device_dropdown.pack(fill="x", pady=5)
        self.device_dropdown.configure(command=lambda _: self._update_device_info())
        
        # VB-Cable warning label
        self.vbcable_warning_label = ctk.CTkLabel(
            self.scroll,
            text="",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="orange",
            wraplength=550
        )
        self.vbcable_warning_label.pack(anchor="w", pady=(5, 0))
        self.add_wraplength_label(self.vbcable_warning_label)
        
        # Refresh devices button
        ctk.CTkButton(
            self.scroll,
            text="Refresh Device List",
            font=ctk.CTkFont(size=FONT_MD),
            command=self._load_devices,
            height=35
        ).pack(anchor="w", pady=15)
        
        self.create_separator(self.scroll).pack(fill="x", pady=10)
        
        # Device info
        ctk.CTkLabel(
            self.scroll,
            text="Device Information",
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD)
        ).pack(anchor="w", pady=(10, 5))
        
        self.device_info_text = ctk.CTkTextbox(
            self.scroll,
            font=ctk.CTkFont(size=FONT_SM),
            height=150,
            wrap="word",
            state="disabled"
        )
        self.device_info_text.pack(fill="x", pady=5)
        
        self.create_separator(self.scroll).pack(fill="x", pady=15)
        
        # Audio Normalization Section
        self._create_normalization_section()
        
        # Microphone Passthrough Section
        self._create_passthrough_section()
        
        # Initialize devices
        self._devices: List[Dict] = []
        self._input_devices: List[Dict] = []
        self._load_devices()
    
    def _create_normalization_section(self):
        """Create the audio normalization section."""
        ctk.CTkLabel(
            self.scroll,
            text="Audio Normalization",
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD)
        ).pack(anchor="w", pady=(10, 5))
        
        norm_info = ctk.CTkLabel(
            self.scroll,
            text="Normalization helps maintain consistent audio levels and prevents clipping.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550
        )
        norm_info.pack(anchor="w", pady=(0, 10))
        self.add_wraplength_label(norm_info)
        
        ctk.CTkLabel(
            self.scroll,
            text="Normalization Type:",
            font=ctk.CTkFont(size=FONT_MD)
        ).pack(anchor="w", pady=(5, 5))
        
        self.norm_var = ctk.StringVar(value=self.settings.get("normalization_type", "Peak"))
        self.norm_dropdown = ctk.CTkComboBox(
            self.scroll,
            variable=self.norm_var,
            values=["Peak", "RMS", "LUFS", "None"],
            font=ctk.CTkFont(size=FONT_MD),
            state="readonly",
            width=200
        )
        self.norm_dropdown.pack(anchor="w", pady=5)
        
        ctk.CTkLabel(
            self.scroll,
            text="Peak: Prevents clipping | RMS: Consistent loudness | LUFS: Professional standard | None: No processing",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray"
        ).pack(anchor="w", pady=(0, 10))
        
        self.enable_norm_var = ctk.BooleanVar(value=self.settings.get("enable_normalization", True))
        self.enable_norm_check = ctk.CTkCheckBox(
            self.scroll,
            text="Enable audio normalization",
            variable=self.enable_norm_var,
            font=ctk.CTkFont(size=FONT_MD)
        )
        self.enable_norm_check.pack(anchor="w", pady=5)
        
        self.create_separator(self.scroll).pack(fill="x", pady=15)
    
    def _create_passthrough_section(self):
        """Create the microphone passthrough section."""
        ctk.CTkLabel(
            self.scroll,
            text="🎙 Microphone Passthrough",
            font=ctk.CTkFont(size=FONT_LG, weight=FONT_WEIGHT_BOLD)
        ).pack(anchor="w", pady=(10, 5))
        
        passthrough_info = ctk.CTkLabel(
            self.scroll,
            text="Route your real microphone to VBCable at the same time as TTS. Useful for mixing your voice with TTS in VRChat/Discord.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray",
            wraplength=550
        )
        passthrough_info.pack(anchor="w", pady=(0, 10))
        self.add_wraplength_label(passthrough_info)
        
        self.mic_passthrough_enabled_var = ctk.BooleanVar(value=self.settings.get("mic_passthrough_enabled", False))
        self.mic_passthrough_enabled_check = ctk.CTkCheckBox(
            self.scroll,
            text="Enable microphone passthrough to VBCable",
            variable=self.mic_passthrough_enabled_var,
            font=ctk.CTkFont(size=FONT_MD)
        )
        self.mic_passthrough_enabled_check.pack(anchor="w", pady=5)
        
        # Passthrough mic device selection
        ctk.CTkLabel(
            self.scroll,
            text="Passthrough Mic Device:",
            font=ctk.CTkFont(size=FONT_MD)
        ).pack(anchor="w", pady=(10, 5))
        
        passthrough_mic_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        passthrough_mic_frame.pack(fill="x", pady=5)
        
        self.passthrough_mic_var = ctk.StringVar()
        self.passthrough_mic_dropdown = ctk.CTkComboBox(
            passthrough_mic_frame,
            variable=self.passthrough_mic_var,
            values=["Loading..."],
            font=ctk.CTkFont(size=FONT_MD),
            dropdown_font=ctk.CTkFont(size=FONT_SM),
            width=400,
            state="readonly"
        )
        self.passthrough_mic_dropdown.pack(side="left", padx=5)
        
        ctk.CTkButton(
            passthrough_mic_frame,
            text="Refresh",
            font=ctk.CTkFont(size=FONT_MD),
            command=self._load_input_devices,
            height=32,
            width=80
        ).pack(side="left", padx=5)
        
        # Passthrough volume slider
        ctk.CTkLabel(
            self.scroll,
            text="Passthrough Volume:",
            font=ctk.CTkFont(size=FONT_MD)
        ).pack(anchor="w", pady=(10, 5))
        
        passthrough_volume_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        passthrough_volume_frame.pack(fill="x", pady=5)
        
        self.passthrough_volume_var = ctk.IntVar(value=self.settings.get("mic_passthrough_volume", 100))
        self.passthrough_volume_slider = ctk.CTkSlider(
            passthrough_volume_frame,
            from_=0,
            to=200,
            number_of_steps=200,
            variable=self.passthrough_volume_var,
            command=self._on_passthrough_volume_change,
            width=400
        )
        self.passthrough_volume_slider.pack(side="left", fill="x", expand=True, padx=5)
        
        self.passthrough_volume_value_label = ctk.CTkLabel(
            passthrough_volume_frame,
            text=f"{self.passthrough_volume_var.get()}%",
            font=ctk.CTkFont(size=FONT_MD),
            width=50
        )
        self.passthrough_volume_value_label.pack(side="right", padx=5)
        
        ctk.CTkLabel(
            self.scroll,
            text="Volume multiplier: 100% is normal, 200% doubles volume, 0% mutes.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray"
        ).pack(anchor="w", pady=(0, 10))
        
        # Passthrough output device selection
        ctk.CTkLabel(
            self.scroll,
            text="Passthrough Output Device:",
            font=ctk.CTkFont(size=FONT_MD)
        ).pack(anchor="w", pady=(10, 5))
        
        passthrough_output_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        passthrough_output_frame.pack(fill="x", pady=5)
        
        self.passthrough_output_var = ctk.StringVar()
        self.passthrough_output_dropdown = ctk.CTkComboBox(
            passthrough_output_frame,
            variable=self.passthrough_output_var,
            values=["Loading..."],
            font=ctk.CTkFont(size=FONT_MD),
            dropdown_font=ctk.CTkFont(size=FONT_SM),
            width=400,
            state="readonly"
        )
        self.passthrough_output_dropdown.pack(side="left", padx=5)
        
        ctk.CTkButton(
            passthrough_output_frame,
            text="Refresh",
            font=ctk.CTkFont(size=FONT_MD),
            command=self._load_devices,
            height=32,
            width=80
        ).pack(side="left", padx=5)
        
        ctk.CTkLabel(
            self.scroll,
            text="Select the VBCable Input device so your mic audio is mixed with TTS.",
            font=ctk.CTkFont(size=FONT_SM),
            text_color="gray"
        ).pack(anchor="w", pady=(0, 10))
    
    def _load_devices(self):
        """Load audio output devices."""
        all_devices = self.audio_router.get_audio_devices() if self.audio_router else []
        
        # Filter for VB-Cable/CABLE devices only
        vbcable_keywords = ["cable", "vb-audio", "vbaudio", "vb cable"]
        self._devices = [
            d for d in all_devices 
            if any(kw in d.get("name", "").lower() for kw in vbcable_keywords)
        ]
        
        if not self._devices:
            self.vbcable_warning_label.configure(
                text="⚠️ No VB-Cable devices found. Please install VB-Cable from vb-audio.com to route TTS audio to VRChat/Discord."
            )
            self.device_dropdown.configure(values=["No VB-Cable devices found"])
            self.device_var.set("No VB-Cable devices found")
            self.passthrough_output_dropdown.configure(values=["No VB-Cable devices found"])
            self.passthrough_output_var.set("No VB-Cable devices found")
        else:
            self.vbcable_warning_label.configure(text="")
            names = [d.get("name", "Unknown") for d in self._devices]
            self.device_dropdown.configure(values=names)
            
            # Try to select the previously saved device
            idx = self.settings.get("device_index")
            found_saved = False
            for d in self._devices:
                if d.get("index") == idx:
                    self.device_var.set(d.get("name", "Unknown"))
                    found_saved = True
                    break
            
            if not found_saved and names:
                self.device_var.set(names[0])
            
            # Populate passthrough output dropdown
            self.passthrough_output_dropdown.configure(values=names)
            
            # Restore saved passthrough output device
            saved_pt_out = self.settings.get("mic_passthrough_output_device_index")
            if saved_pt_out is not None:
                found_pt_out = False
                for d in self._devices:
                    if d.get("index") == saved_pt_out:
                        self.passthrough_output_var.set(d.get("name", "Unknown"))
                        found_pt_out = True
                        break
                if not found_pt_out and names:
                    cable_device = next(
                        (d for d in self._devices if "cable" in d.get("name", "").lower()),
                        None
                    )
                    self.passthrough_output_var.set(
                        cable_device["name"] if cable_device else names[0]
                    )
            else:
                cable_device = next(
                    (d for d in self._devices if "cable" in d.get("name", "").lower()),
                    None
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
        
        device_names = [d.get("name", "Unknown") for d in self._input_devices]
        self.passthrough_mic_dropdown.configure(values=device_names)
        
        # Restore saved passthrough mic device
        saved_passthrough_index = self.settings.get("mic_passthrough_device_index")
        if saved_passthrough_index is not None:
            for d in self._input_devices:
                if d.get("index") == saved_passthrough_index:
                    self.passthrough_mic_var.set(d.get("name", "Default (System)"))
                    break
            else:
                self.passthrough_mic_var.set("Default (System)")
        else:
            self.passthrough_mic_var.set("Default (System)")
    
    def _update_device_info(self):
        """Update the Device Information textbox."""
        device_name = self.device_var.get()
        device = None
        for d in self._devices:
            if d.get("name") == device_name:
                device = d
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
        
        # Get device index
        device_name = self.device_var.get()
        for d in self._devices:
            if d.get("name") == device_name:
                settings["device_index"] = d.get("index")
                break
        
        # Get passthrough mic device index
        selected_passthrough_mic_name = self.passthrough_mic_var.get()
        for d in self._input_devices:
            if d.get("name") == selected_passthrough_mic_name:
                settings["mic_passthrough_device_index"] = d.get("index")
                break
        
        # Get passthrough output device index
        selected_pt_out_name = self.passthrough_output_var.get()
        for d in self._devices:
            if d.get("name") == selected_pt_out_name:
                settings["mic_passthrough_output_device_index"] = d.get("index")
                break
        
        return settings
    
    def validate(self) -> List[str]:
        """Validate the tab's settings."""
        errors = []
        
        # Validate normalization type
        if self.norm_var.get() not in ["Peak", "RMS", "LUFS", "None"]:
            errors.append(f"Invalid normalization type: {self.norm_var.get()}")
        
        # Validate passthrough volume
        volume = self.passthrough_volume_var.get()
        if not (0 <= volume <= 200):
            errors.append(f"Passthrough volume out of range (0-200): {volume}")
        
        return errors