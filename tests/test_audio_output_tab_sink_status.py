"""Tests for replaying/recording the Linux sink result in the Audio Output tab."""

import sys
import threading
from unittest.mock import MagicMock

sys.modules.setdefault("customtkinter", MagicMock())

from src.gui.settings_tabs.audio_output_tab import AudioOutputTab


class FakeThread:
    """Runs the worker synchronously so tests can assert the full path."""

    def __init__(self, target, daemon=False):
        self.target = target
        self.daemon = daemon

    def start(self):
        self.target()


def _make_tab(router):
    tab = object.__new__(AudioOutputTab)
    tab.audio_router = router
    tab.sink_status_label = MagicMock()
    return tab


def test_renders_success_result():
    router = MagicMock()
    router.last_linux_sink_result = (
        True,
        "✅ Ready!\nSet Discord input to:\n   CriTTS_Virtual_Mic",
    )
    tab = _make_tab(router)

    AudioOutputTab._show_last_sink_result(tab)

    tab.sink_status_label.configure.assert_called_once_with(
        text="✅ Ready!\nSet Discord input to:\n   CriTTS_Virtual_Mic",
        text_color="#27ae60",
    )


def test_renders_failure_result():
    router = MagicMock()
    router.last_linux_sink_result = (False, "⚠ pactl not found. Is PipeWire installed?")
    tab = _make_tab(router)

    AudioOutputTab._show_last_sink_result(tab)

    tab.sink_status_label.configure.assert_called_once_with(
        text="⚠ pactl not found. Is PipeWire installed?",
        text_color="#e74c3c",
    )


def test_noop_without_router():
    tab = _make_tab(None)

    AudioOutputTab._show_last_sink_result(tab)

    tab.sink_status_label.configure.assert_not_called()


def test_noop_without_recorded_result():
    router = MagicMock()
    router.last_linux_sink_result = None
    tab = _make_tab(router)

    AudioOutputTab._show_last_sink_result(tab)

    tab.sink_status_label.configure.assert_not_called()


def test_noop_for_non_tuple_result():
    # A bare MagicMock exposes an auto-created child for any attribute, so the
    # unpack must be guarded by a type check rather than truthiness.
    tab = _make_tab(MagicMock())

    AudioOutputTab._show_last_sink_result(tab)

    tab.sink_status_label.configure.assert_not_called()


def test_record_stores_result_on_router():
    router = MagicMock()
    tab = _make_tab(router)

    AudioOutputTab._record_last_sink_result(tab, True, "✅ Ready!")

    assert router.last_linux_sink_result == (True, "✅ Ready!")


def test_record_noop_without_router():
    tab = _make_tab(None)

    AudioOutputTab._record_last_sink_result(tab, True, "✅ Ready!")

    # Nothing to assert beyond it not raising.


def test_create_null_sink_records_success(monkeypatch):
    monkeypatch.setattr(threading, "Thread", FakeThread)
    router = MagicMock()
    router.ensure_linux_sink_modules.return_value = (True, "✅ Ready!")
    tab = _make_tab(router)
    tab.sink_name_var = MagicMock()
    tab.create_sink_button = MagicMock()
    tab.cleanup_sink_button = MagicMock()
    results = []
    tab._after_sink_result = lambda message, *, error: results.append((message, error))

    AudioOutputTab._create_null_sink(tab)

    assert router.last_linux_sink_result == (True, "✅ Ready!")
    assert results == [("✅ Ready!", False)]


def test_cleanup_null_sink_records_removal(monkeypatch):
    monkeypatch.setattr(threading, "Thread", FakeThread)
    router = MagicMock()
    tab = _make_tab(router)
    tab.sink_name_var = MagicMock()
    tab.create_sink_button = MagicMock()
    tab.cleanup_sink_button = MagicMock()
    results = []
    tab._after_sink_result = lambda message, *, error: results.append((message, error))

    AudioOutputTab._cleanup_null_sink(tab)

    router.cleanup_linux_sink_modules.assert_called_once_with()
    assert router.last_linux_sink_result == (True, "🗑 Removed CriTTS sink + virtual mic.")
    assert results == [("🗑 Removed CriTTS sink + virtual mic.", False)]
