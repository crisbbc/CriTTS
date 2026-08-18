"""Tests for the Advanced tab phrase pre-generation UI wiring."""
import sys
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.modules.setdefault("customtkinter", MagicMock())

from src.gui.settings_tabs.advanced_tab import AdvancedTab
from src.gui.theme_constants import BUTTON_HEIGHT


class _SettingsStub(dict):
    """Minimal settings stub for headless tab creation tests."""

    def get(self, key, default=None):
        return dict.get(self, key, default)

    def set(self, key, value):
        self[key] = value


@pytest.fixture(autouse=True)
def _reset_customtkinter_mock():
    """Keep shared customtkinter mocks isolated across tests."""
    ctk = sys.modules["customtkinter"]
    sys.modules["src.gui.settings_tabs.advanced_tab"].ctk = ctk
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
    # Each variable constructor returns a fresh mock so per-control state
    # (e.g. .get.return_value) stays isolated across controls and tests.
    for attribute in ("StringVar", "BooleanVar", "IntVar", "DoubleVar"):
        getattr(ctk, attribute).side_effect = lambda *a, **k: MagicMock()
    yield
    for attribute in ("StringVar", "BooleanVar", "IntVar", "DoubleVar"):
        getattr(ctk, attribute).side_effect = None
    ctk.reset_mock()


def _build_tab(settings=None, parent_window=None):
    tab = object.__new__(AdvancedTab)
    tab.tab = MagicMock()
    tab.tab.winfo_exists.return_value = True
    tab.scroll = MagicMock()
    tab.sidebar = MagicMock()
    tab.settings = settings or _SettingsStub()
    tab.tts_engine = MagicMock()
    tab.audio_router = MagicMock()
    tab.on_change = None
    tab.parent_window = parent_window
    tab._async_callbacks_active = True
    tab._pregenerating = False
    tab._pregenerate_stop_event = threading.Event()
    tab._wraplength_labels = []
    tab._sections = []

    def _setup_layout():
        tab.scroll = MagicMock()
        tab.sidebar = MagicMock()

    tab.setup_layout = _setup_layout
    return tab


def test_pregeneration_section_loads_values_from_settings():
    """The pre-generation controls should load their values from settings."""
    ctk = sys.modules["customtkinter"]
    tab = _build_tab(
        settings=_SettingsStub(
            {
                "pregenerate_phrases_enabled": False,
                "pregenerate_min_uses": 7,
                "pregenerate_max_phrases": 30,
            }
        )
    )

    AdvancedTab._create_pregeneration_section(tab, MagicMock())

    assert ctk.BooleanVar.call_args.kwargs["value"] is False
    int_values = [call.kwargs["value"] for call in ctk.IntVar.call_args_list]
    assert int_values == [7, 30]
    # Disabled pre-generation should start with the button disabled
    tab.pregenerate_button.configure.assert_called_with(state="disabled")


def test_pregenerate_button_meets_touch_target():
    """The pre-generate button should use the shared 44px button height."""
    ctk = sys.modules["customtkinter"]
    tab = _build_tab()

    AdvancedTab._create_pregeneration_section(tab, MagicMock())

    heights = [
        call.kwargs["height"]
        for call in ctk.CTkButton.call_args_list
        if call.kwargs.get("text") == "Pre-generate Common Phrases"
    ]
    assert heights == [BUTTON_HEIGHT]


def test_pregeneration_settings_round_trip():
    """get_settings() should return the current pre-generation values."""
    tab = _build_tab(
        settings=_SettingsStub(
            {
                "pregenerate_phrases_enabled": True,
                "pregenerate_min_uses": 5,
                "pregenerate_max_phrases": 20,
            }
        )
    )
    AdvancedTab._create_content(tab)

    tab.pregenerate_min_uses_var.get.return_value = 12
    tab.pregenerate_max_phrases_var.get.return_value = 40
    tab.pregenerate_enabled_var.get.return_value = False

    result = AdvancedTab.get_settings(tab)

    assert result["pregenerate_phrases_enabled"] is False
    assert result["pregenerate_min_uses"] == 12
    assert result["pregenerate_max_phrases"] == 40


def test_pregenerate_reports_when_engine_missing():
    """Without a TTS engine the button should warn instead of spawning work."""
    tab = _build_tab()
    tab.tts_engine = None

    AdvancedTab._create_pregeneration_section(tab, MagicMock())
    AdvancedTab._on_pregenerate(tab)

    assert tab._pregenerating is False
    text = tab.pregenerate_status_label.configure.call_args.kwargs["text"]
    assert text.startswith("⚠ TTS engine not available.")


def test_pregenerate_reports_when_disabled():
    """Pre-generation should refuse to run while the feature is disabled."""
    tab = _build_tab(
        settings=_SettingsStub({"pregenerate_phrases_enabled": False})
    )

    AdvancedTab._create_pregeneration_section(tab, MagicMock())
    tab.pregenerate_enabled_var.get.return_value = False
    AdvancedTab._on_pregenerate(tab)

    assert tab._pregenerating is False
    text = tab.pregenerate_status_label.configure.call_args.kwargs["text"]
    assert text.startswith("⚠ Phrase pre-generation is disabled.")


def test_pregenerate_runs_background_generation_and_reports_result():
    """Clicking pre-generate should run the engine in a daemon thread and report."""
    parent_window = MagicMock()
    tab = _build_tab(
        settings=_SettingsStub(
            {
                "pregenerate_phrases_enabled": True,
                "pregenerate_min_uses": 3,
                "pregenerate_max_phrases": 20,
            }
        ),
        parent_window=parent_window,
    )
    AdvancedTab._create_pregeneration_section(tab, MagicMock())
    tab.tts_engine.pregenerate_common_phrases = AsyncMock(return_value=3)

    with patch("src.gui.settings_tabs.advanced_tab.threading.Thread") as mock_thread:
        AdvancedTab._on_pregenerate(tab)

    assert tab._pregenerating is True
    tab.pregenerate_button.configure.assert_called_with(state="disabled")
    assert mock_thread.call_count == 1
    assert mock_thread.call_args.kwargs["daemon"] is True
    target = mock_thread.call_args.kwargs["target"]

    # Run the worker body synchronously
    target()

    # The completion callback should be scheduled on the parent window
    assert parent_window.after.call_count >= 1
    for call in parent_window.after.call_args_list:
        callback = call.args[1]
        callback()

    assert tab._pregenerating is False
    tab.pregenerate_button.configure.assert_called_with(state="normal")
    text = tab.pregenerate_status_label.configure.call_args.kwargs["text"]
    assert text.startswith("✓ Done: 3 phrase(s) cached.")
    tab.tts_engine.pregenerate_common_phrases.assert_awaited_once()


def test_pregenerate_done_keeps_button_disabled_when_feature_turned_off_mid_run():
    """Disabling pre-generation during a run must not re-enable the button on completion."""
    parent_window = MagicMock()
    tab = _build_tab(
        settings=_SettingsStub(
            {
                "pregenerate_phrases_enabled": True,
                "pregenerate_min_uses": 3,
                "pregenerate_max_phrases": 20,
            }
        ),
        parent_window=parent_window,
    )
    AdvancedTab._create_pregeneration_section(tab, MagicMock())
    tab.tts_engine.pregenerate_common_phrases = AsyncMock(return_value=2)

    with patch("src.gui.settings_tabs.advanced_tab.threading.Thread") as mock_thread:
        AdvancedTab._on_pregenerate(tab)

    # User unchecks the enable box while the run is in flight
    tab.pregenerate_enabled_var.get.return_value = False

    target = mock_thread.call_args.kwargs["target"]
    target()
    for call in parent_window.after.call_args_list:
        call.args[1]()

    assert tab._pregenerating is False
    # The completion handler must leave the button disabled, matching the toggle
    assert all(
        call.kwargs.get("state") == "disabled"
        for call in tab.pregenerate_button.configure.call_args_list
    )


def test_invalidate_async_callbacks_stops_background_work():
    """Invalidating the tab should flag it dead and signal the stop event."""
    tab = _build_tab()

    AdvancedTab.invalidate_async_callbacks(tab)

    assert tab._async_callbacks_active is False
    assert tab._pregenerate_stop_event.is_set()
