"""Focused regressions for Wave 2 settings modernization retry 3."""
from unittest.mock import MagicMock
from pathlib import Path
import sys

import pytest

sys.modules.setdefault("customtkinter", MagicMock())

from src.config.settings_manager import SettingsManager
from src.gui.settings_tabs.abbreviations_tab import AbbreviationsTab
from src.gui.settings_tabs.advanced_tab import AdvancedTab
from src.gui.settings_tabs.audio_output_tab import AudioOutputTab
from src.gui.settings_tabs.behavior_tab import BehaviorTab
from src.gui.settings_tabs.keybinds_tab import KeybindsTab
from src.gui.settings_tabs.soundboard_tab import SoundboardTab
from src.gui.theme_constants import BUTTON_HEIGHT, get_settings_surface_theme


class _SettingsStub(dict):
    """Minimal settings stub for headless tab creation tests."""

    def get(self, key, default=None):
        return dict.get(self, key, default)

    def set(self, key, value):
        self[key] = value


@pytest.fixture(autouse=True)
def _reset_customtkinter_mock():
    """Keep shared customtkinter mocks isolated across regression tests."""
    ctk = sys.modules["customtkinter"]
    for module_name in (
        "src.gui.settings_tabs.abbreviations_tab",
        "src.gui.settings_tabs.advanced_tab",
        "src.gui.settings_tabs.audio_output_tab",
        "src.gui.settings_tabs.behavior_tab",
        "src.gui.settings_tabs.keybinds_tab",
        "src.gui.settings_tabs.soundboard_tab",
        "src.gui.settings_tabs.base_tab",
    ):
        sys.modules[module_name].ctk = ctk
    ctk.reset_mock()
    ctk.get_appearance_mode.return_value = "Dark"
    for attribute in (
        "CTkLabel",
        "CTkFrame",
        "CTkButton",
        "CTkCheckBox",
        "CTkComboBox",
        "CTkEntry",
        "CTkScrollableFrame",
        "CTkSlider",
        "CTkTextbox",
        "CTkFont",
        "StringVar",
        "BooleanVar",
        "IntVar",
        "DoubleVar",
    ):
        getattr(ctk, attribute).reset_mock()
    yield
    ctk.get_appearance_mode.return_value = "Dark"
    ctk.reset_mock()


def _build_tab(tab_cls, settings=None, audio_router=None, parent_window=None):
    tab = object.__new__(tab_cls)
    tab.tab = MagicMock()
    tab.scroll = MagicMock()
    tab.sidebar = MagicMock()
    tab.settings = settings or _SettingsStub()
    tab.tts_engine = MagicMock()
    tab.audio_router = audio_router
    tab.on_change = None
    tab.parent_window = parent_window
    tab._wraplength_labels = []
    tab._sections = []
    tab.keybind_vars = {}
    tab.keybind_validation_labels = {}
    tab.keybind_capture_buttons = {}
    tab._capturing_keybind = None
    tab._capture_alt_held = False
    tab.setup_layout = lambda: None
    tab.add_wraplength_label = lambda label: tab._wraplength_labels.append(label)
    return tab


def test_settings_manager_preserves_piper_provider_through_save_and_validation(tmp_path: Path):
    """The settings manager should keep Piper as a valid provider choice."""
    config_path = tmp_path / "config.json"

    manager = SettingsManager(config_path=config_path)
    manager.set("tts_provider", "piper")

    assert manager.get("tts_provider") == "piper"
    assert manager.validate_settings() == []
    assert manager.save_settings() is True

    reloaded = SettingsManager(config_path=config_path)
    assert reloaded.get("tts_provider") == "piper"
    assert reloaded.validate_settings() == []


def test_settings_manager_reset_to_defaults_rolls_back_when_persistence_fails(tmp_path: Path, monkeypatch):
    """Failed reset persistence must leave the live settings on the last saved values."""
    config_path = tmp_path / "config.json"
    manager = SettingsManager(config_path=config_path)
    manager.set("rate", 42)
    assert manager.save_settings() is True

    monkeypatch.setattr(manager, "save_settings", lambda: False)

    assert manager.reset_to_defaults() is False
    assert manager.get("rate") == 42


def test_settings_manager_reset_to_defaults_restores_last_persisted_mutable_voice_lists_on_failure(
    tmp_path: Path, monkeypatch
):
    """Failed reset should restore persisted voice favorites/recents, not unsaved live mutations."""
    config_path = tmp_path / "config.json"
    manager = SettingsManager(config_path=config_path)
    manager.set("favorite_voices", ["saved-favorite"])
    manager.set("recent_voices", ["saved-recent"])
    assert manager.save_settings() is True

    manager.set("favorite_voices", ["unsaved-favorite"])
    manager.set("recent_voices", ["unsaved-recent"])

    monkeypatch.setattr(manager, "save_settings", lambda: False)

    assert manager.reset_to_defaults() is False
    assert manager.get("favorite_voices") == ["saved-favorite"]
    assert manager.get("recent_voices") == ["saved-recent"]


def test_standard_tabs_raise_remaining_buttons_to_touch_target():
    """Wave 2 standard-tab buttons should meet the shared 44px baseline."""
    ctk = sys.modules["customtkinter"]

    abbreviations_tab = _build_tab(AbbreviationsTab)
    AbbreviationsTab._create_content(abbreviations_tab)
    assert [
        call.kwargs["height"]
        for call in ctk.CTkButton.call_args_list
        if call.kwargs.get("text") == "Validate Format"
    ] == [BUTTON_HEIGHT]

    ctk.CTkButton.reset_mock()

    keybinds_tab = _build_tab(KeybindsTab, parent_window=MagicMock())
    keybinds_tab._keybind_manager = MagicMock()
    KeybindsTab._create_content(keybinds_tab)
    set_button_heights = [
        call.kwargs["height"]
        for call in ctk.CTkButton.call_args_list
        if call.kwargs.get("text") == "Set"
    ]
    assert len(set_button_heights) == 4
    assert all(height == BUTTON_HEIGHT for height in set_button_heights)

    ctk.CTkButton.reset_mock()

    audio_router = MagicMock()
    audio_router.get_audio_devices.return_value = []
    audio_router.get_input_devices.return_value = []
    audio_output_tab = _build_tab(AudioOutputTab, audio_router=audio_router)
    AudioOutputTab._create_content(audio_output_tab)
    audio_button_heights = {
        call.kwargs.get("text"): call.kwargs["height"]
        for call in ctk.CTkButton.call_args_list
        if "text" in call.kwargs and "height" in call.kwargs
    }
    assert audio_button_heights["Refresh Device List"] == BUTTON_HEIGHT
    assert audio_button_heights["Refresh"] == BUTTON_HEIGHT

    ctk.CTkButton.reset_mock()

    behavior_audio_router = MagicMock()
    behavior_audio_router.get_input_devices.return_value = []
    behavior_tab = _build_tab(BehaviorTab, audio_router=behavior_audio_router)
    BehaviorTab._create_content(behavior_tab)
    assert [
        call.kwargs["height"]
        for call in ctk.CTkButton.call_args_list
        if call.kwargs.get("text") == "Refresh"
    ] == [BUTTON_HEIGHT]

    ctk.CTkButton.reset_mock()

    soundboard_tab = _build_tab(SoundboardTab)
    SoundboardTab._create_content(soundboard_tab)
    soundboard_button_heights = [
        call.kwargs["height"]
        for call in ctk.CTkButton.call_args_list
        if call.kwargs.get("text") in {"Browse", "Clear"}
    ]
    assert len(soundboard_button_heights) == 20
    assert all(height == BUTTON_HEIGHT for height in soundboard_button_heights)

    ctk.CTkButton.reset_mock()

    advanced_tab = _build_tab(AdvancedTab)
    AdvancedTab._create_cache_section(advanced_tab, MagicMock(), get_settings_surface_theme())
    advanced_button_heights = {
        call.kwargs.get("text"): call.kwargs["height"]
        for call in ctk.CTkButton.call_args_list
        if "text" in call.kwargs and "height" in call.kwargs
    }
    assert advanced_button_heights["Clear Audio Cache"] == BUTTON_HEIGHT
    assert advanced_button_heights["Refresh Statistics"] == BUTTON_HEIGHT


@pytest.mark.parametrize(
    ("raw_text", "expected_text"),
    [
        ("brb=be right back", "✓ Format valid - 1 abbreviation(s) found"),
        ("brb", "✕ Error: Line 1: missing '=' (use key=expansion)"),
    ],
)
def test_abbreviations_status_label_uses_readable_surface_treatment(raw_text: str, expected_text: str):
    """Abbreviation validation feedback should use readable section-card status styling."""
    surface_theme = get_settings_surface_theme()
    tab = object.__new__(AbbreviationsTab)
    tab.abbrev_text = MagicMock()
    tab.abbrev_text.get.return_value = raw_text
    tab.abbrev_status_label = MagicMock()

    AbbreviationsTab._validate_abbreviations(tab)

    tab.abbrev_status_label.configure.assert_called_once_with(
        text=expected_text,
        text_color=surface_theme["text_supporting"],
    )


def test_keybind_capture_and_validation_labels_use_readable_surface_treatment():
    """Keybind capture/validation feedback should use readable section-card status styling."""
    surface_theme = get_settings_surface_theme()
    tab = object.__new__(KeybindsTab)
    tab.parent_window = None
    tab._capturing_keybind = None
    tab._capture_alt_held = False
    tab._keybind_manager = MagicMock()
    tab.keybind_capture_buttons = {"stop": MagicMock()}
    tab.keybind_validation_labels = {"stop": MagicMock()}
    tab.keybind_vars = {"stop": MagicMock(), "clear": MagicMock()}
    tab.keybind_vars["stop"].get.return_value = "Ctrl+Shift+S"
    tab.keybind_vars["clear"].get.return_value = ""

    KeybindsTab._start_keybind_capture(tab, "stop")
    tab.keybind_validation_labels["stop"].configure.assert_called_with(
        text="• Capturing...",
        text_color=surface_theme["text_supporting"],
    )

    tab.keybind_validation_labels["stop"].configure.reset_mock()
    tab._keybind_manager.validate_keybind.return_value = True

    KeybindsTab._validate_keybind_entry(tab, "stop")

    tab.keybind_validation_labels["stop"].configure.assert_called_once_with(
        text="✓ Ready",
        text_color=surface_theme["text_supporting"],
    )


def test_audio_output_warning_label_uses_readable_surface_treatment():
    """Audio Output warnings on section cards should use readable surface status styling."""
    surface_theme = get_settings_surface_theme()
    tab = object.__new__(AudioOutputTab)
    tab.settings = _SettingsStub()
    tab.audio_router = MagicMock()
    tab.audio_router.get_audio_devices.return_value = []
    tab.audio_router.get_input_devices.return_value = []
    tab.audio_router.detect_linux_audio_system.return_value = "unknown"
    tab.device_dropdown = MagicMock()
    tab.device_var = MagicMock()
    tab.device_info_text = MagicMock()
    tab.passthrough_mic_dropdown = MagicMock()
    tab.passthrough_mic_var = MagicMock()
    tab.passthrough_output_dropdown = MagicMock()
    tab.passthrough_output_var = MagicMock()
    tab.vbcable_warning_label = MagicMock()
    # Pin to Windows behaviour so the test is stable on any OS
    tab._platform = "windows"

    AudioOutputTab._load_devices(tab)

    tab.vbcable_warning_label.configure.assert_called_once_with(
        text=(
            "⚠ No VB-Cable devices found. Please install VB-Cable from vb-audio.com "
            "to route TTS audio to VRChat/Discord."
        ),
        text_color=surface_theme["text_supporting"],
    )
