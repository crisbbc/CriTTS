"""
Settings Manager Module
Handles JSON-based configuration persistence for user settings.
"""
import copy
import json
import os
import re
import sys
import logging
import threading
import math
from pathlib import Path

logger = logging.getLogger(__name__)


class SettingsManager:
    """Manages application settings with JSON persistence."""

    VALID_TTS_PROVIDERS = ("edge", "piper", "coqui")
    
    DEFAULT_SETTINGS = {
        "voice": "en-US-AriaNeural",
        "device_index": None,
        "rate": 0,  # -100 to 100, 0 is normal
        "volume": 100,  # 0 to 100
        "pitch": 0,  # -100 to 100, 0 is normal
        "appearance_mode": "Dark",
        "enable_normalization": True,
        "normalization_type": "Peak",

        "abbreviations": {},
        "soundboard_enabled": True,
        "soundboard_slots": {
            "1": "",
            "2": "",
            "3": "",
            "4": "",
            "5": "",
            "6": "",
            "7": "",
            "8": "",
            "9": "",
            "10": ""
        },
        "keybinds": {
            "stop": "Escape",
            "clear": "Ctrl+T",
            "open_settings": "Ctrl+Comma",
            "voice_input": "Ctrl+Shift+V"
        },
        "global_hotkeys_enabled": False,  # Enable system-wide hotkeys (requires keyboard library)
        "favorite_voices": [],
        "recent_voices": [],
        "voice_filter_language": "All",
        "voice_filter_gender": "All",
        "voice_filter_region": "All",
        "voice_view_mode": "list",
        "voice_preview_text": "Hello, this is a voice preview.",
        "force_plain_text_mode": False,
        
        # VRChat OSC Chatbox Settings
        "vrchat_osc_enabled": False,
        "vrchat_osc_ip": "127.0.0.1",
        "vrchat_osc_port": 9000,
        "vrchat_osc_play_sound": True,
        "vrchat_osc_send_on_speak": False,
        "vrchat_osc_typing_animation": False,
        "vrchat_osc_typing_timeout": 2.0,
        "vrchat_osc_message_cooldown": 3.0,

        "speak_mode": "all_text",
        "auto_language_detection": False,
        "language_voice_mappings": {},
        "language_detection_confidence_threshold": 0.3,  # Minimum confidence for language detection (0.0-1.0)
        "language_detection_min_length": 5,  # Minimum text length for language detection
        
        # Audio Cache Settings
        "audio_cache_enabled": True,
        "audio_cache_max_size_mb": 500,
        "audio_cache_path": None,  # None means default ~/.critts/audio_cache/
        
        # Voice Cache Settings
        "voice_cache_path": None,  # None means default ~/.critts/voices_cache.json
        "voice_cache_max_age_days": 7,
        
        # Pre-generation Settings
        "pregenerate_phrases_enabled": True,
        "pregenerate_min_uses": 3,
        "pregenerate_max_phrases": 20,
        
        # Text Processing Settings
        "text_cache_size": 1000,  # Increased from default 100
        "processing_profile": "balanced",  # fast, balanced, quality
        
        # Streaming Playback (Experimental)
        "enable_streaming_playback": False,
        
        # VRChat Viseme Settings
        "vrchat_viseme_enabled": False,
        "vrchat_viseme_smoothing": 0.1,
        "vrchat_voice_amplitude_enabled": False,
        
        # STT (Speech-to-Text) Settings
        "stt_language": "en-US",
        "stt_mic_device_index": None,
        "stt_auto_speak": False,  # Automatically speak transcribed text
        
        # STT Audio Pre-processing Settings
        "stt_min_duration_ms": 300,  # Minimum recording length before transcribing
        "stt_silence_threshold": 200,  # int16 RMS threshold for silence trimming
        "stt_highpass_filter": True,  # Apply 80 Hz high-pass filter
        
        # STT Text Post-processing Settings
        "stt_capitalize": True,  # Capitalize first letter of result
        "stt_add_punctuation": False,  # Append period if no trailing punctuation
        "stt_apply_abbreviations": False,  # Expand abbreviations in STT output
        "stt_corrections": {},  # Word-level correction map for misrecognitions
        "stt_confidence_threshold": 0.0,  # Minimum confidence to accept a result (0.0 = disabled)
        
        # Microphone Passthrough Settings
        "mic_passthrough_enabled": False,  # Master toggle for mic passthrough
        "mic_passthrough_device_index": None,  # Mic to capture (None = system default)
        "mic_passthrough_output_device_index": None,  # Output device for passthrough (None = same as TTS output)
        "mic_passthrough_volume": 100,  # Volume multiplier 0–200 (%)
        
        # Button Visibility Settings
        "visible_buttons": ["speak", "stop", "clear", "voice", "overlay"],  # Toggleable buttons to show (settings is always visible)
        
        # Overlay Settings
        "overlay_visible": True,  # Whether the recording overlay is visible

        # TTS Provider Selection
        "tts_provider": "edge",  # "edge" (online), "piper" (offline fast), or "coqui" (offline high quality)

        # Coqui TTS Settings
        # gpu_device selects the CUDA device (-2 = Auto, -1 = CPU only, 0+ = GPU index)
        # language sets the XTTS v2 synthesis language (ISO code, default: "en")
        "coqui_gpu_device": -2,
        "coqui_language": "en",

        # Piper TTS Settings
        # Keep None to preserve per-voice .onnx.json inference recommendations.
        "piper_noise_scale": None,
        "piper_noise_w_scale": None,
        "piper_sentence_silence": 0.2,

        # Audio clarity EQ: high-pass + presence boost for speech intelligibility
        "enable_clarity_eq": True,

        # Linux PulseAudio/PipeWire sink routing
        "linux_sink_name": "",  # Name of the null sink to route TTS to (empty = no auto-routing)
    }








    
    def __init__(self, config_path=None):
        """Initialize settings manager with optional custom config path."""
        if config_path is None:
            # Store config in user's home directory
            config_dir = Path.home() / ".critts"
            config_dir.mkdir(exist_ok=True)
            # Restrict directory to owner-only on non-Windows to protect settings
            if sys.platform != "win32":
                os.chmod(config_dir, 0o700)
            self.config_path = config_dir / "config.json"
        else:
            self.config_path = Path(config_path)
        
        self._settings = {}
        self._persisted_settings = {}
        self._voices_mapping: dict = {}  # friendly_name -> short_name
        self._lock = threading.RLock()  # Thread safety for settings access (reentrant for update() -> set())
        self.load_settings()

    def _update_persisted_settings_snapshot(self):
        """Track the last settings state known to be synchronized with disk."""
        self._persisted_settings = copy.deepcopy(self._settings)
    
    def set_voices_mapping(self, voices_mapping: dict):
        """
        Set the mapping from friendly voice names to short_names.
        Used by GUI/engine to provide voice mapping for migration.
        
        Args:
            voices_mapping: Dictionary mapping friendly_name -> short_name
        """
        self._voices_mapping = voices_mapping or {}
        # Re-run migration with the new mapping
        self._migrate_voice_setting()
    
    def load_settings(self):
        """Load settings from JSON file or use defaults if file doesn't exist."""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                if not isinstance(loaded, dict):
                    logger.warning("Settings file is not a valid dictionary; resetting to defaults.")
                    self._settings = copy.deepcopy(self.DEFAULT_SETTINGS)
                    self.save_settings()
                    return
                # Merge with defaults, then normalize persisted values before
                # anything consumes them.  Validation alone is not sufficient:
                # malformed JSON values otherwise remain live at runtime.
                self._settings = {**copy.deepcopy(self.DEFAULT_SETTINGS), **loaded}
                self._normalize_loaded_settings()
                self._migrate_voice_setting()
                
                # Validate all settings and log any issues
                issues = self.validate_settings()
                if issues:
                    logger.warning("Settings validation issues: %s", issues)
                self._update_persisted_settings_snapshot()
            else:
                self._settings = copy.deepcopy(self.DEFAULT_SETTINGS)
                self.save_settings()
        except json.JSONDecodeError as e:
            # Back up the corrupted file so the user can recover their settings manually
            backup_path = self.config_path.with_suffix(".corrupted.json")
            try:
                self.config_path.rename(backup_path)
                logger.warning(
                    "Settings file is corrupted (%s). A backup has been saved to '%s'. "
                    "Using defaults.",
                    e, backup_path,
                )
            except OSError:
                logger.warning("Error loading settings: %s. Using defaults.", e)
            self._settings = copy.deepcopy(self.DEFAULT_SETTINGS)
            self._update_persisted_settings_snapshot()
        except IOError as e:
            logger.warning("Error loading settings: %s. Using defaults.", e)
            self._settings = copy.deepcopy(self.DEFAULT_SETTINGS)
            self._update_persisted_settings_snapshot()
    
    def _validate_text_setting(self, key: str, default_value: str) -> bool:
        """
        Validate a text-based setting for corruption or suspicious content.
        
        Args:
            key: The setting key to validate
            default_value: The default value to use if validation fails
            
        Returns:
            True if valid, False if corrupted and reset
        """
        value = self._settings.get(key)
        if value is None:
            return True
        
        if not isinstance(value, str):
            logger.warning("Setting '%s' is not a string; resetting to default.", key)
            self._settings[key] = default_value
            return False
        
        # Check for parameter-like patterns that shouldn't be in text settings
        # Use anchored patterns to catch corrupted TTS parameter strings while
        # allowing normal sentences that contain these words mid-sentence
        param_patterns = [
            r'^rate\s*=',      # Matches "rate=" at start of string or line
            r'^volume\s*=',
            r'^pitch\s*=',
            r'^voice\s*=',
            r'^speed\s*=',
        ]
        
        for pattern in param_patterns:
            if re.search(pattern, value, re.IGNORECASE | re.MULTILINE):
                logger.warning("Setting '%s' contains suspicious parameter pattern; resetting to default. Value was: '%s'", key, value)
                self._settings[key] = default_value
                return False
        
        # Check if text contains only printable characters
        if not all(c.isprintable() or c.isspace() for c in value):
            logger.warning("Setting '%s' contains non-printable characters; resetting to default.", key)
            self._settings[key] = default_value
            return False
        
        return True
    
    def _normalize_loaded_settings(self):
        """Replace malformed persisted values with their individual defaults."""
        for key, default in self.DEFAULT_SETTINGS.items():
            if key not in self._settings:
                continue
            value = self._settings[key]
            valid = True

            if default is None:
                # Optional paths and device indexes have a concrete shape even
                # though their default is None.
                if key in {"audio_cache_path", "voice_cache_path"}:
                    valid = value is None or isinstance(value, str)
                elif key in {"device_index", "stt_mic_device_index", "mic_passthrough_device_index", "mic_passthrough_output_device_index"}:
                    valid = value is None or (isinstance(value, int) and not isinstance(value, bool))
                else:
                    valid = value is None or isinstance(value, (str, int, float, bool))
            elif isinstance(default, bool):
                valid = isinstance(value, bool)
            elif isinstance(default, (int, float)):
                valid = (
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and math.isfinite(float(value))
                )
            else:
                valid = isinstance(value, type(default))

            if not valid:
                logger.warning("Setting '%s' has an invalid type; resetting to default.", key)
                self._settings[key] = copy.deepcopy(default)

        # Validate the structured values that have stricter schemas than their
        # container type alone conveys.
        self._validate_text_setting("voice_preview_text", self.DEFAULT_SETTINGS["voice_preview_text"])
        for key in ("abbreviations", "soundboard_slots", "keybinds", "language_voice_mappings", "stt_corrections"):
            if not isinstance(self._settings.get(key), dict):
                logger.warning("Setting '%s' is not a dictionary; resetting to default.", key)
                self._settings[key] = copy.deepcopy(self.DEFAULT_SETTINGS[key])

        # Apply the same range rules used by interactive settings changes.
        ranges = {
            "rate": (-100, 100),
            "volume": (0, 100),
            "pitch": (-100, 100),
            "audio_cache_max_size_mb": (1, None),
            "stt_silence_threshold": (0, None),
            "mic_passthrough_volume": (0, 200),
            "vrchat_osc_port": (1, 65535),
        }
        for key, (minimum, maximum) in ranges.items():
            value = self._settings.get(key)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                self._settings[key] = copy.deepcopy(self.DEFAULT_SETTINGS[key])
                continue
            if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
                logger.warning("Setting '%s' is out of range; resetting to default.", key)
                self._settings[key] = copy.deepcopy(self.DEFAULT_SETTINGS[key])

        if self._settings.get("tts_provider") not in self.VALID_TTS_PROVIDERS:
            self._settings["tts_provider"] = self.DEFAULT_SETTINGS["tts_provider"]
        if self._settings.get("appearance_mode") not in ("Dark", "Light", "System"):
            self._settings["appearance_mode"] = self.DEFAULT_SETTINGS["appearance_mode"]
        if self._settings.get("normalization_type") not in ("Peak", "RMS", "LUFS", "None"):
            self._settings["normalization_type"] = self.DEFAULT_SETTINGS["normalization_type"]

    def _migrate_voice_setting(self):
        """Migrate legacy friendly voice names without destroying valid Coqui IDs."""
        voice = self._settings.get("voice")
        if not isinstance(voice, str) or not voice:
            return

        # XTTS speaker IDs are human names containing spaces.  They are valid
        # identifiers, not legacy Edge display names, and metadata is loaded
        # after SettingsManager during startup.
        if self._settings.get("tts_provider") == "coqui":
            if self._voices_mapping and voice in self._voices_mapping:
                self._settings["voice"] = self._voices_mapping[voice]
                self.save_settings()
            return

        if " " not in voice and "(" not in voice and ")" not in voice:
            return

        if self._voices_mapping and voice in self._voices_mapping:
            self._settings["voice"] = self._voices_mapping[voice]
            logger.info("Migrated voice setting '%s' to '%s'", voice, self._settings["voice"])
            self.save_settings()
            return

        defaults = {"edge": "en-US-AriaNeural", "piper": "en_US-lessac-medium"}
        provider = self._settings.get("tts_provider", "edge")
        replacement = defaults.get(provider, self.DEFAULT_SETTINGS["voice"])
        logger.warning("Could not map voice '%s' for provider '%s'; resetting to '%s'", voice, provider, replacement)
        self._settings["voice"] = replacement
        self.save_settings()
    
    def save_settings(self):
        """Save current settings to JSON file (atomic write to prevent corruption)."""
        with self._lock:
            tmp_path = self.config_path.with_suffix(".tmp")
            try:
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(self._settings, f, indent=4)
                os.replace(tmp_path, self.config_path)
                self._update_persisted_settings_snapshot()
                return True
            except IOError as e:
                logger.warning("Error saving settings: %s", e)
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass
                return False
    
    def get(self, key, default=None):
        """Get a setting value by key."""
        with self._lock:
            return self._settings.get(key, default)
    
    @staticmethod
    def _default_voice_for_provider(provider: str) -> str:
        """Return the safe initial voice for a provider."""
        return {
            "edge": "en-US-AriaNeural",
            "piper": "en_US-lessac-medium",
            "coqui": "Claribel Dervla",
        }.get(provider, SettingsManager.DEFAULT_SETTINGS["voice"])

    def _voice_matches_provider(self, voice: object, provider: str) -> bool:
        """Recognize provider voice identifier shapes without importing runtimes."""
        if not isinstance(voice, str) or not voice:
            return False
        if provider == "coqui":
            # XTTS speaker IDs are human-readable names.  Prefer the mapping
            # when metadata is loaded, but keep unknown future speaker names
            # rather than replacing them with a stale hard-coded list.
            if voice in self._voices_mapping or voice in self._voices_mapping.values():
                return True
            return " " in voice and "(" not in voice and ")" not in voice
        if provider == "piper":
            return "_" in voice and voice.count("-") >= 2 and " " not in voice
        if provider == "edge":
            return voice.endswith("Neural") and " " not in voice
        return False

    def set(self, key, value):
        """Set a setting value by key with validation."""
        with self._lock:
            
            # A provider switch invalidates the previous provider's voice.  Do
            # this before assigning the new provider so a later voice-tab value
            # in the same settings transaction can still replace the fallback.
            if key == "tts_provider" and value in self.VALID_TTS_PROVIDERS:
                current_voice = self._settings.get("voice")
                if value != self._settings.get("tts_provider") and not self._voice_matches_provider(current_voice, value):
                    self._settings["voice"] = self._default_voice_for_provider(value)

            # Validate keybind format if setting keybinds
            if key == "keybinds" and isinstance(value, dict):
                validated_keybinds = {}
                for action, keybind in value.items():
                    if self._validate_keybind_format(keybind):
                        validated_keybinds[action] = keybind
                    else:
                        logger.warning("Invalid keybind format for %s: %s", action, keybind)
                value = validated_keybinds
            
            # Validate OSC port
            if key == "vrchat_osc_port":
                try:
                    port = int(value)
                    if 1 <= port <= 65535:
                        value = port
                    else:
                        logger.warning("OSC port out of range: %s, using default", value)
                        value = self.DEFAULT_SETTINGS["vrchat_osc_port"]
                except (ValueError, TypeError):
                    logger.warning("Invalid OSC port: %s, using default", value)
                    value = self.DEFAULT_SETTINGS["vrchat_osc_port"]
            
            # Validate normalization type
            if key == "normalization_type" and value not in ["Peak", "RMS", "LUFS", "None"]:
                logger.warning("Invalid normalization type: %s, using default", value)
                value = self.DEFAULT_SETTINGS["normalization_type"]
            
            # Validate appearance mode
            if key == "appearance_mode" and value not in ["Dark", "Light", "System"]:
                logger.warning("Invalid appearance mode: %s, using default", value)
                value = self.DEFAULT_SETTINGS["appearance_mode"]
            
            # Validate TTS provider
            if key == "tts_provider" and value not in self.VALID_TTS_PROVIDERS:
                logger.warning("Invalid TTS provider: %s, using default", value)
                value = self.DEFAULT_SETTINGS["tts_provider"]

            # Normalize numeric settings so programmatic updates cannot inject
            # strings or out-of-range values into runtime arithmetic.
            numeric_ranges = {
                "rate": (-100, 100),
                "volume": (0, 100),
                "pitch": (-100, 100),
                "audio_cache_max_size_mb": (1, None),
                "stt_silence_threshold": (0, None),
                "mic_passthrough_volume": (0, 200),
            }
            if key in numeric_ranges:
                minimum, maximum = numeric_ranges[key]
                try:
                    numeric_value = float(value)
                    if not math.isfinite(numeric_value) or (minimum is not None and numeric_value < minimum) or (maximum is not None and numeric_value > maximum):
                        raise ValueError
                    value = int(numeric_value) if isinstance(self.DEFAULT_SETTINGS[key], int) else numeric_value
                except (TypeError, ValueError):
                    logger.warning("Invalid %s: %s, using default", key, value)
                    value = self.DEFAULT_SETTINGS[key]

            # Validate Coqui GPU device index
            if key == "coqui_gpu_device":
                try:
                    idx = int(value)
                    value = max(-2, idx)
                except (TypeError, ValueError):
                    value = -2
            
            self._settings[key] = value
    
    def get_all(self):
        """Get all settings as a dictionary."""
        with self._lock:
            return copy.deepcopy(self._settings)

    def get_persisted_settings(self):
        """Get the last settings snapshot that successfully loaded from or saved to disk."""
        with self._lock:
            return copy.deepcopy(self._persisted_settings)

    def restore_last_persisted_settings(self):
        """Restore the in-memory settings to the last snapshot known to match disk."""
        with self._lock:
            self._settings = copy.deepcopy(self._persisted_settings)
    
    def update(self, settings_dict):
        """Update multiple settings at once."""
        with self._lock:
            for key, value in settings_dict.items():
                self.set(key, value)

    def _mutate_and_save(self, mutator):
        """Apply an in-memory mutation and roll it back if persistence fails."""
        with self._lock:
            previous_settings = copy.deepcopy(self._persisted_settings)
            mutator()
            if self.save_settings():
                return True
            self._settings = previous_settings
            return False

    def set_and_save(self, key, value):
        """Set a setting and persist it, restoring the previous state on failure."""
        return self._mutate_and_save(lambda: self.set(key, value))

    def update_and_save(self, settings_dict):
        """Update multiple settings and persist them atomically."""
        return self._mutate_and_save(lambda: self.update(settings_dict))
    
    def reset_to_defaults(self):
        """Reset all settings to default values."""
        return self._mutate_and_save(
            lambda: setattr(self, "_settings", copy.deepcopy(self.DEFAULT_SETTINGS))
        )
    
    def _validate_keybind_format(self, keybind_string: str) -> bool:
        """
        Validate keybind format using shared validation utility.
        
        This ensures consistent validation between settings and the keybind manager
        without creating circular imports.
        """
        from ..utils.keybind_utils import validate_keybind_format
        
        return validate_keybind_format(keybind_string)
    
    def validate_settings(self) -> list:
        """Validate all settings and return list of issues."""
        issues = []
        
        with self._lock:
            # Check keybinds
            keybinds = self._settings.get("keybinds", {})
            if not isinstance(keybinds, dict):
                issues.append("keybinds setting is not a dictionary")
            else:
                for action, keybind in keybinds.items():
                    if not self._validate_keybind_format(keybind):
                        issues.append(f"Invalid keybind for {action}: {keybind}")
            
            # Check OSC settings
            osc_port = self._settings.get("vrchat_osc_port")
            try:
                port = int(osc_port)
                if not (1 <= port <= 65535):
                    issues.append(f"OSC port out of range: {port}")
            except (ValueError, TypeError):
                issues.append(f"Invalid OSC port: {osc_port}")
            
            # Check normalization type
            norm_type = self._settings.get("normalization_type")
            if norm_type not in ["Peak", "RMS", "LUFS", "None"]:
                issues.append(f"Invalid normalization type: {norm_type}")
            
            # Check appearance mode
            appearance = self._settings.get("appearance_mode")
            if appearance not in ["Dark", "Light", "System"]:
                issues.append(f"Invalid appearance mode: {appearance}")
            
            # Check TTS provider
            tts_provider = self._settings.get("tts_provider")
            if tts_provider not in self.VALID_TTS_PROVIDERS:
                issues.append(f"Invalid TTS provider: {tts_provider}")
            
            # Check numeric range settings
            rate = self._settings.get("rate")
            if not isinstance(rate, (int, float)) or not (-100 <= rate <= 100):
                issues.append(f"Rate out of range (-100 to 100): {rate}")
            
            volume = self._settings.get("volume")
            if not isinstance(volume, (int, float)) or not (0 <= volume <= 100):
                issues.append(f"Volume out of range (0 to 100): {volume}")
            
            pitch = self._settings.get("pitch")
            if not isinstance(pitch, (int, float)) or not (-100 <= pitch <= 100):
                issues.append(f"Pitch out of range (-100 to 100): {pitch}")
            
            cache_size = self._settings.get("audio_cache_max_size_mb")
            if not isinstance(cache_size, (int, float)) or cache_size <= 0:
                issues.append(f"Audio cache size must be positive: {cache_size}")
            
            silence_threshold = self._settings.get("stt_silence_threshold")
            if not isinstance(silence_threshold, (int, float)) or silence_threshold < 0:
                issues.append(f"STT silence threshold must be non-negative: {silence_threshold}")
            
            mic_passthrough_volume = self._settings.get("mic_passthrough_volume")
            if not isinstance(mic_passthrough_volume, (int, float)) or not (0 <= mic_passthrough_volume <= 200):
                issues.append(f"Mic passthrough volume out of range (0 to 200): {mic_passthrough_volume}")

            soundboard_enabled = self._settings.get("soundboard_enabled")
            if not isinstance(soundboard_enabled, bool):
                issues.append(f"soundboard_enabled must be a boolean: {soundboard_enabled}")

            soundboard_slots = self._settings.get("soundboard_slots")
            if not isinstance(soundboard_slots, dict):
                issues.append("soundboard_slots must be a dictionary")
            else:
                for slot, file_path in soundboard_slots.items():
                    if not isinstance(slot, str) or not slot.isdigit():
                        issues.append(f"Invalid soundboard slot key: {slot}")
                        continue

                    slot_num = int(slot)
                    if not (1 <= slot_num <= 99):
                        issues.append(f"Soundboard slot out of range (1-99): {slot}")

                    if file_path is not None and not isinstance(file_path, str):
                        issues.append(f"Soundboard slot '{slot}' path must be a string or null")
        
        return issues
