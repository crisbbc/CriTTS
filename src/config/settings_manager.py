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

_VALID_TTS_PROVIDERS = ("edge", "piper", "coqui")

_APPEARANCE_MODES = ("Dark", "Light", "System")
_NORMALIZATION_TYPES = ("Peak", "RMS", "LUFS", "None")

_NUMERIC_KINDS = ("int", "number")

# Parameter-like prefixes that must never appear in free-text settings.
# Anchored at the start of the whole string so a legitimate multi-line preview
# whose later lines start with these words is not falsely rejected.
_TEXT_PARAM_PATTERNS = (
    re.compile(r"^rate\s*=", re.IGNORECASE),
    re.compile(r"^volume\s*=", re.IGNORECASE),
    re.compile(r"^pitch\s*=", re.IGNORECASE),
    re.compile(r"^voice\s*=", re.IGNORECASE),
    re.compile(r"^speed\s*=", re.IGNORECASE),
)

# Declarative refinements layered on top of the defaults-derived schema.  Every
# key omitted here is still covered: its type is inferred from DEFAULT_SETTINGS,
# and keys whose default is None are treated as nullable unless overridden.
_SCHEMA_OVERRIDES = {
    # Nullable keys (default None) with a concrete non-None shape.
    "device_index": {"kind": "int"},
    "stt_mic_device_index": {"kind": "int"},
    "mic_passthrough_device_index": {"kind": "int"},
    "mic_passthrough_output_device_index": {"kind": "int"},
    "audio_cache_path": {"kind": "str"},
    "voice_cache_path": {"kind": "str"},
    "piper_noise_scale": {"kind": "number", "range": (0.0, 2.0)},
    "piper_noise_w_scale": {"kind": "number", "range": (0.0, 2.0)},

    # Range-constrained numbers.
    "rate": {"range": (-100, 100)},
    "volume": {"range": (0, 100)},
    "pitch": {"range": (-100, 100)},
    "audio_cache_max_size_mb": {"range": (1, None)},
    "stt_silence_threshold": {"range": (0, None)},
    "mic_passthrough_volume": {"range": (0, 200)},
    "vrchat_osc_port": {"range": (1, 65535)},
    "coqui_gpu_device": {"range": (-2, None)},
    "coqui_temperature": {"range": (0.0, 1.0)},
    "coqui_repetition_penalty": {"range": (1.0, 20.0)},
    "coqui_gpu_cleanup_interval": {"range": (0, 100)},
    "stt_confidence_threshold": {"range": (0.0, 1.0)},
    "language_detection_confidence_threshold": {"range": (0.0, 1.0)},
    "piper_sentence_silence": {"range": (0.0, 2.0)},

    # Enumerated string choices.
    "appearance_mode": {"choices": _APPEARANCE_MODES},
    "normalization_type": {"choices": _NORMALIZATION_TYPES},
    "tts_provider": {"choices": _VALID_TTS_PROVIDERS},

    # Free-text content guard (parameter-pattern + printability checks).
    "voice_preview_text": {"text": True},
}


def _derived_kind(default):
    """Infer a schema kind from a setting's default value."""
    if isinstance(default, bool):
        return "bool"
    if isinstance(default, int):
        return "int"
    if isinstance(default, float):
        return "number"
    if isinstance(default, str):
        return "str"
    if isinstance(default, list):
        return "list"
    if isinstance(default, dict):
        return "dict"
    return "any"  # None (and unknown) defaults: accept anything unless overridden


def _value_matches_kind(value, kind, nullable):
    """Return whether `value` satisfies the given schema kind."""
    if value is None:
        return nullable
    if kind == "bool":
        return isinstance(value, bool)
    if kind == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
        )
    if kind == "str":
        return isinstance(value, str)
    if kind == "list":
        return isinstance(value, list)
    if kind == "dict":
        return isinstance(value, dict)
    return True  # "any"


def _in_range(value, rng):
    """Return whether `value` falls within the given (min, max) range."""
    if rng is None:
        return True
    minimum, maximum = rng
    return (minimum is None or value >= minimum) and (maximum is None or value <= maximum)


def _build_schema(default_settings):
    """Derive the declarative schema from defaults, refined by overrides."""
    schema = {}
    for key, default in default_settings.items():
        entry = {
            "kind": _derived_kind(default),
            "default": default,
            "nullable": default is None,
        }
        entry.update(_SCHEMA_OVERRIDES.get(key, {}))
        schema[key] = entry
    return schema


class SettingsManager:
    """Manages application settings with JSON persistence."""

    VALID_TTS_PROVIDERS = _VALID_TTS_PROVIDERS
    
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
        # temperature/repetition_penalty tune XTTS sampling stability: lower
        # temperature and higher repetition_penalty reduce "uhhh"/loop artifacts.
        # enable_text_splitting uses XTTS's language-aware sentence splitter.
        # gpu_cleanup_interval runs torch.cuda.empty_cache() every N syntheses
        # (0 = never) to counter VRAM fragmentation over long sessions.
        "coqui_gpu_device": -2,
        "coqui_language": "en",
        "coqui_temperature": 0.75,
        "coqui_repetition_penalty": 10.0,
        "coqui_enable_text_splitting": True,
        "coqui_gpu_cleanup_interval": 5,

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








    
    # Single declarative source of truth driving load normalization, set()
    # coercion, and validate_settings().  Entries are derived from defaults
    # and refined by the module-level `_SCHEMA_OVERRIDES` table.
    SCHEMA = _build_schema(DEFAULT_SETTINGS)

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
    
    def _text_issue(self, key, value):
        """Return a human-readable issue for a suspicious text setting, else None."""
        for pattern in _TEXT_PARAM_PATTERNS:
            if pattern.match(value):
                return f"Setting '{key}' contains a suspicious parameter pattern"
        if not all(c.isprintable() or c.isspace() for c in value):
            return f"Setting '{key}' contains non-printable characters"
        return None

    def _coerce_setting(self, key, value):
        """Return (coerced_value, issue) for a raw setting value.

        `issue` is None when the value is valid (and canonicalized); otherwise
        it names the problem and the value is replaced by its schema default.
        """
        entry = self.SCHEMA.get(key)
        if entry is None:
            return value, None  # Unknown keys pass through unchanged.

        kind = entry["kind"]
        default = entry["default"]
        nullable = entry.get("nullable", False)

        # Numeric kinds canonicalize numbers (and numeric strings) and reject
        # booleans, non-finite values, and out-of-range values.
        if kind in _NUMERIC_KINDS:
            if value is None and nullable:
                return None, None
            try:
                if isinstance(value, bool):
                    raise ValueError
                numeric = float(value)
                if not math.isfinite(numeric) or not _in_range(numeric, entry.get("range")):
                    raise ValueError
                return (int(numeric) if kind == "int" else numeric), None
            except (TypeError, ValueError):
                return copy.deepcopy(default), f"Setting '{key}' has an invalid value {value!r}"

        if _value_matches_kind(value, kind, nullable):
            choices = entry.get("choices")
            if choices is not None and value not in choices:
                return copy.deepcopy(default), f"Setting '{key}' has an invalid choice {value!r}"
            if entry.get("text"):
                text_issue = self._text_issue(key, value)
                if text_issue is not None:
                    return copy.deepcopy(default), text_issue
            return value, None

        return copy.deepcopy(default), f"Setting '{key}' has an invalid type ({type(value).__name__})"

    def _normalize_loaded_settings(self):
        """Normalize persisted values onto the schema, resetting malformed ones."""
        for key, raw in list(self._settings.items()):
            normalized, issue = self._coerce_setting(key, raw)
            if issue:
                logger.warning("%s; resetting to default.", issue)
            self._settings[key] = normalized

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
        """Set a setting value by key, coercing it through the shared schema."""
        with self._lock:
            # A provider switch invalidates the previous provider's voice.  Do
            # this before assigning the new provider so a later voice-tab value
            # in the same settings transaction can still replace the fallback.
            if key == "tts_provider" and value in self.VALID_TTS_PROVIDERS:
                current_voice = self._settings.get("voice")
                if value != self._settings.get("tts_provider") and not self._voice_matches_provider(current_voice, value):
                    self._settings["voice"] = self._default_voice_for_provider(value)

            # Keybind dictionaries are filtered (keeping valid entries) rather
            # than reset wholesale, so one bad keybind doesn't discard the rest.
            if key == "keybinds" and isinstance(value, dict):
                validated_keybinds = {}
                for action, keybind in value.items():
                    if self._validate_keybind_format(keybind):
                        validated_keybinds[action] = keybind
                    else:
                        logger.warning("Invalid keybind format for %s: %s", action, keybind)
                value = validated_keybinds

            normalized, issue = self._coerce_setting(key, value)
            if issue:
                logger.warning("%s; resetting to default.", issue)
            self._settings[key] = normalized
    
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
    
    def _validate_keybinds(self, keybinds) -> list:
        """Validate keybind entries, preserving the per-action message format."""
        issues = []
        if not isinstance(keybinds, dict):
            issues.append("keybinds setting is not a dictionary")
            return issues
        for action, keybind in keybinds.items():
            if not self._validate_keybind_format(keybind):
                issues.append(f"Invalid keybind for {action}: {keybind}")
        return issues

    def _validate_soundboard_slots(self, soundboard_slots) -> list:
        """Validate soundboard slot keys and paths."""
        issues = []
        if not isinstance(soundboard_slots, dict):
            issues.append("soundboard_slots must be a dictionary")
            return issues
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

    def validate_settings(self) -> list:
        """Validate all settings against the schema and return a list of issues."""
        issues = []
        with self._lock:
            for key, value in self._settings.items():
                _, issue = self._coerce_setting(key, value)
                if issue:
                    issues.append(issue)
            issues.extend(self._validate_keybinds(self._settings.get("keybinds", {})))
            issues.extend(self._validate_soundboard_slots(self._settings.get("soundboard_slots", {})))
        return issues
