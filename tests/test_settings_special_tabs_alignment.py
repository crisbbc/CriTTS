"""Regression tests for Wave 2 settings-tab surface alignment."""
from pathlib import Path
from unittest.mock import MagicMock
import sys

import pytest

sys.modules.setdefault("customtkinter", MagicMock())

from src.gui.settings_tabs.advanced_tab import AdvancedTab
from src.gui.settings_tabs.tts_provider_tab import TTSProviderTab
from src.gui.settings_tabs.voice_tab import VoiceTab
from src.gui.settings_tabs.vrchat_osc_tab import VRChatOSCTab
from src.gui.theme_constants import BUTTON_HEIGHT, get_settings_surface_theme


class _SettingsStub(dict):
    """Minimal settings stub for headless tab creation tests."""

    def get(self, key, default=None):
        return dict.get(self, key, default)

    def set(self, key, value):
        self[key] = value

    def set_voices_mapping(self, mapping):
        self["voices_mapping"] = mapping


@pytest.fixture(autouse=True)
def _reset_customtkinter_mock():
    """Keep shared customtkinter mocks isolated across regression tests."""
    ctk = sys.modules["customtkinter"]
    for module_name in (
        "src.gui.settings_tabs.advanced_tab",
        "src.gui.settings_tabs.tts_provider_tab",
        "src.gui.settings_tabs.voice_tab",
        "src.gui.settings_tabs.vrchat_osc_tab",
        "src.gui.settings_tabs.base_tab",
    ):
        sys.modules[module_name].ctk = ctk
    ctk.reset_mock()
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
    ctk.reset_mock()


def _build_tab(tab_cls, settings=None):
    tab = object.__new__(tab_cls)
    tab.tab = MagicMock()
    tab.settings = settings or _SettingsStub()
    tab.tts_engine = MagicMock()
    tab.audio_router = MagicMock()
    tab.on_change = None
    tab.parent_window = None
    tab._wraplength_labels = []
    tab._sections = []

    def _setup_layout():
        tab.scroll = MagicMock()
        tab.sidebar = MagicMock()

    tab.setup_layout = _setup_layout
    return tab


def test_voice_tab_keeps_only_favorites_and_recent_sidebar_anchors():
    """Voice tab should not introduce new sidebar anchors while adopting shared surfaces."""
    tab = _build_tab(VoiceTab)
    tab._load_voices = MagicMock()
    tab._preview_stop_event = MagicMock()

    VoiceTab._create_content(tab)

    assert [section["title"] for section in tab._sections] == [
        "★ Favorite Voices",
        "Recent Voices",
    ]


def test_advanced_tab_keeps_sidebar_anchor_order():
    """Advanced tab anchor order must stay stable during the surface refresh."""
    tab = _build_tab(AdvancedTab)

    AdvancedTab._create_content(tab)

    assert [section["title"] for section in tab._sections] == [
        "Cache Management",
        "Network Privacy",
        "Performance Settings",
        "Experimental Features",
    ]


def test_vrchat_osc_tab_keeps_sidebar_anchor_order():
    """VRChat OSC tab should preserve the audited section order."""
    tab = _build_tab(VRChatOSCTab)

    VRChatOSCTab._create_content(tab)

    assert [section["title"] for section in tab._sections] == [
        "VRChat OSC Chatbox",
        "VRChat Viseme Lip-Sync",
        "Typing Indicator",
    ]


def test_tts_provider_tab_keeps_only_top_level_sidebar_anchors():
    """Conditional Coqui content must not create a third sidebar anchor."""
    tab = _build_tab(TTSProviderTab, _SettingsStub(tts_provider="coqui"))

    TTSProviderTab._create_content(tab)

    assert [section["title"] for section in tab._sections] == [
        "Active Provider",
        "Provider Details",
    ]


def test_special_tabs_remove_hardcoded_gray_helper_text():
    """Wave 2 tabs should use shared settings text tokens instead of hardcoded gray helper copy."""
    repo_root = Path(__file__).resolve().parents[1]
    tab_paths = [
        repo_root / "src/gui/settings_tabs/voice_tab.py",
        repo_root / "src/gui/settings_tabs/advanced_tab.py",
        repo_root / "src/gui/settings_tabs/vrchat_osc_tab.py",
        repo_root / "src/gui/settings_tabs/tts_provider_tab.py",
    ]

    for path in tab_paths:
        file_text = path.read_text(encoding="utf-8")
        assert 'text_color="gray"' not in file_text
        assert "text_color='gray'" not in file_text
        assert "\ufe0f" not in file_text


def test_special_tabs_drop_raw_info_and_status_text_colors():
    """Special tabs should not use raw semantic accent colors for small card copy."""
    repo_root = Path(__file__).resolve().parents[1]
    disallowed_tokens = (
        "COLOR_INFO",
        "COLOR_STATUS_IDLE",
        "COLOR_STATUS_SUCCESS",
        "COLOR_STATUS_WARNING",
        "COLOR_STATUS_ERROR",
    )
    tab_paths = [
        repo_root / "src/gui/settings_tabs/voice_tab.py",
        repo_root / "src/gui/settings_tabs/advanced_tab.py",
        repo_root / "src/gui/settings_tabs/vrchat_osc_tab.py",
        repo_root / "src/gui/settings_tabs/tts_provider_tab.py",
    ]

    for path in tab_paths:
        file_text = path.read_text(encoding="utf-8")
        for token in disallowed_tokens:
            assert token not in file_text, f"{path.name} still uses {token}"


def test_special_tabs_raise_explicitly_small_controls_to_touch_target():
    """Audited special-tab controls should use the shared 44px button height."""
    ctk = sys.modules["customtkinter"]

    voice_tab = _build_tab(VoiceTab)
    voice_tab._preview_stop_event = MagicMock()
    voice_tab.create_separator = MagicMock(return_value=MagicMock())
    voice_tab._validate_preview_text = VoiceTab._validate_preview_text.__get__(voice_tab, VoiceTab)

    VoiceTab._create_voice_selection_section(voice_tab, MagicMock())
    VoiceTab._create_preview_section(voice_tab, MagicMock())

    voice_button_heights = {
        call.kwargs["text"]: call.kwargs["height"]
        for call in ctk.CTkButton.call_args_list
        if "text" in call.kwargs and "height" in call.kwargs
    }
    assert voice_button_heights["☆"] == BUTTON_HEIGHT
    assert voice_button_heights["↻"] == BUTTON_HEIGHT
    assert voice_button_heights["▶ Preview"] == BUTTON_HEIGHT
    assert voice_button_heights["⏹ Stop"] == BUTTON_HEIGHT

    ctk.CTkButton.reset_mock()

    osc_tab = _build_tab(VRChatOSCTab)
    osc_tab._on_osc_enabled_toggle = MagicMock()

    VRChatOSCTab._create_chatbox_section(osc_tab, MagicMock())

    osc_button_heights = {
        call.kwargs["text"]: call.kwargs["height"]
        for call in ctk.CTkButton.call_args_list
        if "text" in call.kwargs and "height" in call.kwargs
    }
    assert osc_button_heights["Test connection"] == BUTTON_HEIGHT


def test_surface_status_labels_keep_readable_text_color():
    """Runtime status labels on section cards should use readable surface text treatment."""
    surface_theme = get_settings_surface_theme()
    label = MagicMock()

    VoiceTab.configure_surface_status_label(label, "Playing...", "success")

    label.configure.assert_called_once_with(
        text="✓ Playing...",
        text_color=surface_theme["text_supporting"],
    )
