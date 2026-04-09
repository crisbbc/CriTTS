from unittest.mock import AsyncMock, MagicMock
import sys

sys.modules.setdefault("customtkinter", MagicMock())

from src.gui.main_window import LatestWinsTextAnalysisScheduler, MainWindow
from src.audio.audio_router import PreparedAudioPayload
import numpy as np
import pytest
from src.gui.theme_constants import get_theme_colors


def test_latest_request_supersedes_older_request():
    scheduler = LatestWinsTextAnalysisScheduler()

    older_request = scheduler.next_request("first")
    latest_request = scheduler.next_request("second")

    assert not scheduler.is_latest(older_request)
    assert scheduler.is_latest(latest_request)


def test_latest_request_stays_current_until_another_is_scheduled():
    scheduler = LatestWinsTextAnalysisScheduler()

    request = scheduler.next_request("only")

    assert scheduler.is_latest(request)


class _StubTextInput:
    def __init__(self):
        self.calls = []

    def delete(self, start, end):
        self.calls.append(("delete", start, end))

    def insert(self, index, text):
        self.calls.append(("insert", index, text))

    def focus(self):
        self.calls.append(("focus",))

    def focus_set(self):
        self.calls.append(("focus_set",))

    def get(self, start, end):
        if (start, end) == ("sel.first", "sel.last"):
            return "selected text"
        raise AssertionError(f"unexpected get call: {(start, end)}")


class _StubRoot:
    def __init__(self, clipboard_text="clipboard text"):
        self.clipboard_text = clipboard_text
        self.clipboard = []

    def clipboard_get(self):
        return self.clipboard_text

    def clipboard_clear(self):
        self.clipboard.clear()

    def clipboard_append(self, text):
        self.clipboard.append(text)

    def after(self, delay, callback):
        raise AssertionError(f"unexpected after call: {delay}")


class _StubSettings:
    def __init__(self, values=None):
        self._values = values or {}
        self._save_result = True

    def get(self, key, default=None):
        return self._values.get(key, default)

    def set(self, key, value):
        self._values[key] = value

    def save_settings(self):
        return self._save_result

    def set_save_result(self, result):
        self._save_result = result


class _StubVariable:
    def __init__(self, value=None):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


def _make_window():
    window = MainWindow.__new__(MainWindow)
    window.text_input = _StubTextInput()
    window.root = _StubRoot()
    window._is_typing_active = False
    window._refresh_calls = 0
    window._refresh_after_text_mutation = lambda: setattr(
        window, "_refresh_calls", window._refresh_calls + 1
    )
    return window


def test_refresh_after_text_mutation_updates_highlight_then_schedules_voice_indicator():
    window = MainWindow.__new__(MainWindow)
    calls = []
    window._highlight_current_line = lambda: calls.append("highlight")
    window._schedule_voice_indicator_update = lambda: calls.append("voice")

    MainWindow._refresh_after_text_mutation(window)

    assert calls == ["highlight", "voice"]


def test_set_text_refreshes_after_programmatic_replace():
    window = _make_window()

    MainWindow.set_text(window, "hello world")

    assert window.text_input.calls == [
        ("delete", "1.0", "end"),
        ("insert", "1.0", "hello world"),
    ]
    assert window._refresh_calls == 1


def test_paste_refreshes_after_clipboard_insert():
    window = _make_window()

    result = MainWindow._on_text_paste(window)

    assert result == "break"
    assert ("insert", "insert", "clipboard text") in window.text_input.calls
    assert window._refresh_calls == 1


def test_cut_refreshes_after_selected_text_removed():
    window = _make_window()

    result = MainWindow._on_text_cut(window)

    assert result == "break"
    assert window.root.clipboard == ["selected text"]
    assert ("delete", "sel.first", "sel.last") in window.text_input.calls
    assert window._refresh_calls == 1


def test_clear_refreshes_after_text_deleted():
    window = _make_window()

    MainWindow._on_clear(window)

    assert ("delete", "1.0", "end") in window.text_input.calls
    assert ("focus",) in window.text_input.calls
    assert window._refresh_calls == 1


def test_insert_soundboard_token_refreshes_after_insert():
    window = _make_window()

    MainWindow._insert_soundboard_token(window, "7")

    assert ("insert", "insert", "[7]") in window.text_input.calls
    assert ("focus_set",) in window.text_input.calls
    assert window._refresh_calls == 1


def test_insert_stt_text_refreshes_after_programmatic_insert():
    window = _make_window()
    window.settings = _StubSettings(
        {
            "stt_apply_abbreviations": False,
            "stt_corrections": {},
            "stt_auto_speak": False,
        }
    )
    window._text_preprocessor = None
    window._apply_stt_corrections = lambda text, corrections: text
    window._set_status = lambda message, icon: None

    MainWindow._insert_stt_text(window, "voice text")

    assert ("insert", "insert", "voice text") in window.text_input.calls
    assert window._refresh_calls == 1


def test_on_text_changed_keeps_keyboard_path_limited_to_voice_update_and_typing():
    window = MainWindow.__new__(MainWindow)
    calls = []
    window._schedule_voice_indicator_update = lambda: calls.append("voice")
    window._handle_typing_animation = lambda: calls.append("typing")

    MainWindow._on_text_changed(window)

    assert calls == ["voice", "typing"]


@pytest.mark.parametrize("quick_controls_visible", [False, True])
def test_apply_theme_recolors_quick_controls(quick_controls_visible):
    colors = get_theme_colors("Light")
    window = MainWindow.__new__(MainWindow)
    window.root = MagicMock()
    window.main_frame = MagicMock()
    window.text_frame = MagicMock()
    window.text_input = MagicMock()
    window.text_label = MagicMock()
    window.voice_indicator_label = MagicMock()
    window.voice_indicator_value = MagicMock()
    window.status_frame = MagicMock()
    window.status_label = MagicMock()
    window.progress_label = MagicMock()
    window.quick_controls_frame = MagicMock()
    window._qc_rate_label = MagicMock()
    window._qc_volume_label = MagicMock()
    window._qc_pitch_label = MagicMock()
    window.controls_toggle_button = MagicMock()
    window._quick_controls_visible = quick_controls_visible

    MainWindow.apply_theme(window, "Light")

    window.quick_controls_frame.configure.assert_called_once_with(
        fg_color=colors["bg_secondary"]
    )
    window._qc_rate_label.configure.assert_called_once_with(
        text_color=colors["text_secondary"]
    )
    window._qc_volume_label.configure.assert_called_once_with(
        text_color=colors["text_secondary"]
    )
    window._qc_pitch_label.configure.assert_called_once_with(
        text_color=colors["text_secondary"]
    )
    expected_button_colors = (
        {
            "fg_color": colors["button_active"],
            "hover_color": colors["button_active_hover"],
        }
        if quick_controls_visible
        else {
            "fg_color": colors["button_neutral"],
            "hover_color": colors["button_neutral_hover"],
        }
    )
    window.controls_toggle_button.configure.assert_called_once_with(
        **expected_button_colors
    )
    if not quick_controls_visible:
        assert expected_button_colors["hover_color"] != expected_button_colors["fg_color"]


def test_refresh_quick_controls_resyncs_visibility_from_settings():
    window = MainWindow.__new__(MainWindow)
    window.settings = _StubSettings(
        {
            "rate": 15,
            "volume": 80,
            "pitch": -10,
            "quick_controls_visible": True,
            "appearance_mode": "Light",
        }
    )
    window._quick_controls_visible = False
    window.quick_controls_frame = MagicMock()
    window.controls_toggle_button = MagicMock()
    window._qc_rate_var = _StubVariable()
    window._qc_volume_var = _StubVariable()
    window._qc_pitch_var = _StubVariable()
    window._qc_rate_label = MagicMock()
    window._qc_volume_label = MagicMock()
    window._qc_pitch_label = MagicMock()
    window._update_quick_controls_provider = MagicMock()

    MainWindow.refresh_quick_controls(window)

    assert window._quick_controls_visible is True
    window.quick_controls_frame.grid.assert_called_once_with()
    window.quick_controls_frame.grid_remove.assert_not_called()
    window.controls_toggle_button.configure.assert_called_once()


def test_toggle_quick_controls_rolls_back_when_persistence_fails():
    window = MainWindow.__new__(MainWindow)
    window.settings = _StubSettings({"quick_controls_visible": False, "appearance_mode": "Light"})
    window.settings.set_save_result(False)
    window._quick_controls_visible = False
    window.quick_controls_frame = MagicMock()
    window.controls_toggle_button = MagicMock()
    window._qc_rate_var = _StubVariable()
    window._qc_volume_var = _StubVariable()
    window._qc_pitch_var = _StubVariable()
    window._qc_rate_label = MagicMock()
    window._qc_volume_label = MagicMock()
    window._qc_pitch_label = MagicMock()
    window._update_quick_controls_provider = MagicMock()
    window._apply_quick_controls_theme = MagicMock()
    window._show_error = MagicMock()

    MainWindow._toggle_quick_controls(window)

    assert window._quick_controls_visible is False
    assert window.settings.get("quick_controls_visible") is False
    window.quick_controls_frame.grid.assert_not_called()
    window.quick_controls_frame.grid_remove.assert_not_called()
    window._show_error.assert_called_once()


@pytest.mark.parametrize(
    ("handler_name", "setting_key", "initial_value", "attempted_value", "label_attr", "label_text"),
    [
        ("_on_quick_rate_change", "rate", 15, 25, "_qc_rate_label", "Speed: +15%"),
        ("_on_quick_volume_change", "volume", 80, 65, "_qc_volume_label", "Volume: 80%"),
        ("_on_quick_pitch_change", "pitch", -10, 30, "_qc_pitch_label", "Pitch: -10%"),
    ],
)
def test_quick_control_slider_rolls_back_when_persistence_fails(
    handler_name, setting_key, initial_value, attempted_value, label_attr, label_text
):
    window = MainWindow.__new__(MainWindow)
    window.settings = _StubSettings(
        {
            "rate": initial_value if setting_key == "rate" else 0,
            "volume": initial_value if setting_key == "volume" else 100,
            "pitch": initial_value if setting_key == "pitch" else 0,
            "quick_controls_visible": False,
            "appearance_mode": "Light",
        }
    )
    window.settings.set_save_result(False)
    window._quick_controls_visible = False
    window.quick_controls_frame = MagicMock()
    window.controls_toggle_button = MagicMock()
    window._qc_rate_var = _StubVariable(window.settings.get("rate"))
    window._qc_volume_var = _StubVariable(window.settings.get("volume"))
    window._qc_pitch_var = _StubVariable(window.settings.get("pitch"))
    window._qc_rate_label = MagicMock()
    window._qc_volume_label = MagicMock()
    window._qc_pitch_label = MagicMock()
    window._update_quick_controls_provider = MagicMock()
    window._apply_quick_controls_theme = MagicMock()
    window.refresh_quick_controls = lambda: MainWindow.refresh_quick_controls(window)
    window._show_error = MagicMock()

    getattr(MainWindow, handler_name)(window, attempted_value)

    assert window.settings.get(setting_key) == initial_value
    assert getattr(window, f"_qc_{setting_key}_var").get() == initial_value
    getattr(window, label_attr).configure.assert_called_with(text=label_text)
    window._show_error.assert_called_once()


def test_toggle_overlay_rolls_back_when_persistence_fails():
    window = MainWindow.__new__(MainWindow)
    window.settings = _StubSettings({"overlay_visible": True})
    window.settings.set_save_result(False)
    window._overlay_visible = True
    window._recording_overlay = MagicMock()
    window._stt_state = None
    window.overlay_button = MagicMock()
    window._show_error = MagicMock()

    MainWindow._on_toggle_overlay(window)

    assert window._overlay_visible is True
    assert window.settings.get("overlay_visible") is True
    window._recording_overlay.show_overlay.assert_not_called()
    window._recording_overlay.hide_overlay.assert_not_called()
    window.overlay_button.configure.assert_not_called()
    window._show_error.assert_called_once()


@pytest.mark.asyncio
async def test_play_audio_segment_prepares_audio_once_for_viseme_and_amplitude_playback():
    window = MainWindow.__new__(MainWindow)
    prepared = PreparedAudioPayload(
        data=np.zeros((4800, 2), dtype=np.float32),
        sample_rate=48000,
    )
    window.settings = _StubSettings(
        {
            "vrchat_voice_amplitude_enabled": True,
            "enable_clarity_eq": True,
        }
    )
    window._viseme_mapper = MagicMock()
    window._amplitude_analyzer = MagicMock()
    window._amplitude_analyzer.get_amplitude = MagicMock(return_value=0.5)
    window.osc_client = MagicMock()
    window.audio_router = MagicMock()
    window.audio_router.prepare_audio_for_playback = AsyncMock(return_value=prepared)
    window.audio_router.get_audio_duration = AsyncMock(side_effect=AssertionError("duration should come from prepared audio"))
    window.audio_router.play_audio_with_amplitude = AsyncMock(return_value=True)

    result = await MainWindow._play_audio_segment(
        window,
        audio_data=b"segment-bytes",
        segment_text="hello there",
        speech_rate=0,
        device_idx=2,
        enable_normalization=True,
        normalization_type="Peak",
        processing_profile="balanced",
        enable_viseme=True,
    )

    assert result is True
    window.audio_router.prepare_audio_for_playback.assert_awaited_once_with(
        b"segment-bytes",
        enable_normalization=True,
        normalization_type="Peak",
        processing_profile="balanced",
        enable_clarity_eq=True,
    )
    window._viseme_mapper.start_viseme_animation.assert_called_once()
    assert window._viseme_mapper.start_viseme_animation.call_args.kwargs["duration"] == pytest.approx(0.1)
    window.audio_router.play_audio_with_amplitude.assert_awaited_once_with(
        b"segment-bytes",
        48000,
        2,
        True,
        "Peak",
        amplitude_callback=window.audio_router.play_audio_with_amplitude.await_args.kwargs["amplitude_callback"],
        processing_profile="balanced",
        enable_clarity_eq=True,
        prepared_audio=prepared,
    )
