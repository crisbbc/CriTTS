"""Tests for surfacing the Linux sink auto-setup result in the status bar."""

import importlib
import sys
import threading
from types import MethodType, SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture(scope="module")
def main_module():
    """Import the real ``main`` module with real customtkinter in place.

    Other test modules install a ``customtkinter`` MagicMock into
    ``sys.modules``, which turns ``class CriTTSApp(ctk.CTk)`` into a
    MagicMock (``spec='str'``) and hides the real methods.  Temporarily swap
    the real package in only while importing, then restore the mock so other
    test modules are unaffected.
    """
    saved = sys.modules.get("customtkinter")
    was_mock = isinstance(saved, MagicMock)
    if was_mock:
        sys.modules.pop("customtkinter", None)
        importlib.import_module("customtkinter")
    try:
        return importlib.import_module("main")
    finally:
        if was_mock:
            sys.modules["customtkinter"] = saved


class FakeMainWindow:
    def __init__(self):
        self.scheduled = []
        self.status_calls = []

    def _safe_after(self, delay_ms, callback):
        self.scheduled.append((delay_ms, callback))
        return object()

    def _set_status(self, message, icon="", message_type="info"):
        self.status_calls.append((message, icon, message_type))


class FakeThread:
    """Runs the worker synchronously so tests can assert the full path."""

    def __init__(self, target, daemon=False):
        self.target = target
        self.daemon = daemon

    def start(self):
        self.target()


def _make_app(main_module, sink_name, ok, message):
    app = SimpleNamespace(
        settings_manager=MagicMock(),
        audio_router=MagicMock(),
        main_window=FakeMainWindow(),
    )
    app.settings_manager.get.return_value = sink_name
    app.audio_router.ensure_linux_sink_modules.return_value = (ok, message)
    # Bind the real method so `_ensure_linux_sink_setup` reaches it instead of
    # a MagicMock auto-attribute.
    app._report_linux_sink_status = MethodType(
        main_module.CriTTSApp._report_linux_sink_status, app
    )
    return app


def _flush(app):
    """Run the one callback the worker scheduled and return the status calls."""
    (delay, callback), = app.main_window.scheduled
    assert delay == 0
    callback()
    return app.main_window.status_calls


def test_report_success_flattens_message_and_uses_success_type(main_module):
    app = _make_app(main_module, "crittssink", True, "✅ Ready!\nSet Discord input to:\n   CriTTS_Virtual_Mic")

    main_module.CriTTSApp._report_linux_sink_status(
        app, True, "✅ Ready!\nSet Discord input to:\n   CriTTS_Virtual_Mic"
    )

    assert _flush(app) == [
        ("✅ Ready! Set Discord input to: CriTTS_Virtual_Mic", "", "success"),
    ]


def test_report_failure_uses_warning_type(main_module):
    app = _make_app(main_module, "crittssink", False, "⚠ pactl not found. Is PipeWire installed?")

    main_module.CriTTSApp._report_linux_sink_status(
        app, False, "⚠ pactl not found. Is PipeWire installed?"
    )

    assert _flush(app) == [
        ("⚠ pactl not found. Is PipeWire installed?", "", "warning"),
    ]


def test_report_explicit_error_type(main_module):
    app = _make_app(main_module, "crittssink", False, "❌ boom")

    main_module.CriTTSApp._report_linux_sink_status(app, False, "❌ boom", "error")

    assert _flush(app) == [("❌ boom", "", "error")]


def test_report_without_main_window_is_noop(main_module):
    app = SimpleNamespace()  # no main_window attribute

    # Should not raise.
    main_module.CriTTSApp._report_linux_sink_status(app, True, "✅ Ready!")


def test_setup_posts_status_when_configured(main_module, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(threading, "Thread", FakeThread)
    app = _make_app(main_module, "crittssink", True, "✅ Ready!\nSet Discord input to:\n   CriTTS_Virtual_Mic")

    main_module.CriTTSApp._ensure_linux_sink_setup(app)

    app.audio_router.ensure_linux_sink_modules.assert_called_once_with("crittssink")
    assert _flush(app) == [
        ("✅ Ready! Set Discord input to: CriTTS_Virtual_Mic", "", "success"),
    ]


def test_setup_skips_without_sink_name(main_module, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(threading, "Thread", FakeThread)
    app = _make_app(main_module, "", True, "✅ Ready!")

    main_module.CriTTSApp._ensure_linux_sink_setup(app)

    app.audio_router.ensure_linux_sink_modules.assert_not_called()
    assert app.main_window.scheduled == []


def test_setup_skips_on_non_linux(main_module, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    app = _make_app(main_module, "crittssink", True, "✅ Ready!")

    main_module.CriTTSApp._ensure_linux_sink_setup(app)

    app.audio_router.ensure_linux_sink_modules.assert_not_called()
    assert app.main_window.scheduled == []


def test_setup_reports_error_status_on_exception(main_module, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(threading, "Thread", FakeThread)
    app = _make_app(main_module, "crittssink", True, "✅ Ready!")
    app.audio_router.ensure_linux_sink_modules.side_effect = RuntimeError("boom")

    main_module.CriTTSApp._ensure_linux_sink_setup(app)

    assert _flush(app) == [("❌ Linux sink setup failed: boom", "", "error")]
