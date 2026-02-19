"""
Settings Manager Module
Handles JSON-based configuration persistence for user settings.
"""
import json
import os
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


class SettingsManager:
    """Manages application settings with JSON persistence."""
    
    DEFAULT_SETTINGS = {
        "voice": "en-US-AriaNeural",
        "device_index": None,
        "rate": 0,  # -100 to 100, 0 is normal
        "volume": 100,  # 0 to 100
        "pitch": 0,  # -100 to 100, 0 is normal
        "appearance_mode": "Dark",
        "enable_normalization": True,
        "normalization_type": "Peak",

        "abbreviations": {
            "idk": "I don't know",
            "brb": "be right back",
            "omg": "oh my god",
            "btw": "by the way",
            "imo": "in my opinion",
            "tbh": "to be honest"
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

        "speak_mode": "all_text",
        "auto_language_detection": False,
        "language_voice_mappings": {},
        
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
        "stt_auto_speak": False  # Automatically speak transcribed text
    }








    
    def __init__(self, config_path=None):
        """Initialize settings manager with optional custom config path."""
        if config_path is None:
            # Store config in user's home directory
            config_dir = Path.home() / ".critts"
            config_dir.mkdir(exist_ok=True)
            self.config_path = config_dir / "config.json"
        else:
            self.config_path = Path(config_path)
        
        self._settings = {}
        self._voices_mapping: dict = {}  # friendly_name -> short_name
        self._lock = threading.RLock()  # Thread safety for settings access (reentrant for update() -> set())
        self.load_settings()
    
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
                    self._settings = self.DEFAULT_SETTINGS.copy()
                    self.save_settings()
                    return
                # Merge with defaults to ensure all keys exist
                self._settings = {**self.DEFAULT_SETTINGS, **loaded}
                # Validate abbreviations is a dictionary
                abbreviations = self._settings.get("abbreviations")
                if not isinstance(abbreviations, dict):
                    logger.warning("abbreviations setting corrupted or invalid; resetting to default.")
                    self._settings["abbreviations"] = self.DEFAULT_SETTINGS["abbreviations"].copy()
                # Validate voice_preview_text for corruption
                self._validate_text_setting("voice_preview_text", self.DEFAULT_SETTINGS["voice_preview_text"])
                self._migrate_voice_setting()
            else:
                self._settings = self.DEFAULT_SETTINGS.copy()
                self.save_settings()
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("Error loading settings: %s. Using defaults.", e)
            self._settings = self.DEFAULT_SETTINGS.copy()
    
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
        import re
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
    
    def _migrate_voice_setting(self):
        """
        Migrate legacy voice setting: if saved value is a friendly name (contains spaces/parentheses),
        map it to the corresponding short_name. Only fall back to default if no match exists.
        Preserves existing valid short_name (no spaces/parentheses).
        """
        voice = self._settings.get("voice")
        if not voice or not isinstance(voice, str):
            return
        
        # If it's already a valid short_name (no spaces or parentheses), preserve it
        if " " not in voice and "(" not in voice and ")" not in voice:
            return
        
        # It's a friendly name - try to map it to short_name
        if self._voices_mapping and voice in self._voices_mapping:
            # Map friendly name to short_name
            self._settings["voice"] = self._voices_mapping[voice]
            logger.info("Migrated voice setting '%s' to '%s'", voice, self._settings["voice"])
        else:
            # No mapping available - fall back to default
            logger.warning("Could not map voice '%s' to short_name; resetting to default", voice)
            self._settings["voice"] = self.DEFAULT_SETTINGS["voice"]
    
    def save_settings(self):
        """Save current settings to JSON file."""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self._settings, f, indent=4)
            return True
        except IOError as e:
            logger.warning("Error saving settings: %s", e)
            return False
    
    def get(self, key, default=None):
        """Get a setting value by key."""
        with self._lock:
            return self._settings.get(key, default)
    
    def set(self, key, value):
        """Set a setting value by key with validation."""
        with self._lock:
            
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
            
            self._settings[key] = value
    
    def get_all(self):
        """Get all settings as a dictionary."""
        with self._lock:
            return self._settings.copy()
    
    def update(self, settings_dict):
        """Update multiple settings at once."""
        with self._lock:
            for key, value in settings_dict.items():
                self.set(key, value)
    
    def reset_to_defaults(self):
        """Reset all settings to default values."""
        with self._lock:
            self._settings = self.DEFAULT_SETTINGS.copy()
            self.save_settings()
    
    def _validate_keybind_format(self, keybind_string: str) -> bool:
        """Validate keybind format."""
        if not keybind_string or not isinstance(keybind_string, str):
            return False
        
        # Basic format check - should contain only valid characters
        import re
        pattern = r'^[A-Za-z0-9+\-_=,\.\/;\'\[\]\\`~!@#$%^&*(){}|:<>? ]+$'
        if not re.match(pattern, keybind_string):
            return False
        
        # Check for critical system shortcuts
        normalized = keybind_string.lower().replace(' ', '')
        critical_shortcuts = ['alt+f4', 'ctrl+alt+delete', 'win+l', 'win+r', 'win+e']
        if any(cs in normalized for cs in critical_shortcuts):
            return False
        
        return True
    
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
        
        return issues
