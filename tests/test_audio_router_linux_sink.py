"""Tests for the Linux null-sink + virtual-mic setup helper."""
import subprocess
import sys
from types import SimpleNamespace

import pytest

from src.audio.audio_router import AudioRouter


def _result(stdout="", stderr="", returncode=0):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def test_router_defaults_last_auto_setup_result_to_none():
    assert AudioRouter().last_linux_sink_result is None


@pytest.fixture
def linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/pactl" if name == "pactl" else None)


def test_non_linux_is_a_noop(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(a) or _result())

    ok, message = AudioRouter.ensure_linux_sink_modules()

    assert ok is True
    assert message == ""
    assert calls == []


def test_creates_sink_and_mic_when_missing(linux, monkeypatch):
    calls = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: calls.append(a) or {
            0: _result(stdout=""),
            1: _result(returncode=0),
            2: _result(stdout=""),
            3: _result(returncode=0),
        }[len(calls) - 1],
    )

    ok, message = AudioRouter.ensure_linux_sink_modules()

    assert ok is True
    assert message == "✅ Ready! Set Discord input to:\n   CriTTS_Virtual_Mic"
    assert calls[0][0] == ["pactl", "list", "short", "sinks"]
    assert calls[1][0] == [
        "pactl", "load-module", "module-null-sink",
        "sink_name=crittssink",
        "sink_properties=device.description=CriTTS_Null_Sink",
    ]
    assert calls[2][0] == ["pactl", "list", "short", "sources"]
    assert calls[3][0] == [
        "pactl", "load-module", "module-remap-source",
        "source_name=crittssink_mic",
        "source_properties=device.description=CriTTS_Virtual_Mic",
        "master=crittssink.monitor",
    ]


def test_existing_sink_and_mic_are_noop(linux, monkeypatch):
    calls = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: calls.append(a) or {
            0: _result(stdout="0\tcrittssink\tmodule-null-sink.c"),
            1: _result(stdout="0\tcrittssink_mic\tmodule-remap-source.c"),
        }[len(calls) - 1],
    )

    ok, message = AudioRouter.ensure_linux_sink_modules()

    assert ok is True
    assert "✅ Ready!" in message
    # Only the two list calls ran; no load-module calls.
    assert [call[0][1] for call in calls] == ["list", "list"]


def test_missing_pactl_returns_error(linux, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(a) or _result())

    ok, message = AudioRouter.ensure_linux_sink_modules()

    assert ok is False
    assert message == "⚠ pactl not found. Is PipeWire installed?"
    assert calls == []


def test_sink_creation_failure_returns_error(linux, monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: _result() if a[0][1] == "list" else _result(returncode=1, stderr="boom"),
    )

    ok, message = AudioRouter.ensure_linux_sink_modules()

    assert ok is False
    assert message == "❌ Failed to create sink: boom"


def test_mic_failure_returns_partial_success(linux, monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: (
            _result(stdout="0\tcrittssink\tmodule-null-sink.c")
            if a[0][-1] == "sinks"
            else (
                _result(stdout="")
                if a[0][-1] == "sources"
                else _result(returncode=1, stderr="micfail")
            )
        ),
    )

    ok, message = AudioRouter.ensure_linux_sink_modules()

    assert ok is True
    assert "✅ Null sink ready." in message
    assert "⚠ Virtual mic failed (micfail)" in message


def test_custom_sink_name_flows_through(linux, monkeypatch):
    calls = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: calls.append(a) or _result(stdout="", returncode=0),
    )

    ok, _ = AudioRouter.ensure_linux_sink_modules("myvrc")

    assert ok is True
    load_sink = next(c for c in calls if c[0][1] == "load-module" and c[0][2] == "module-null-sink")
    load_mic = next(c for c in calls if c[0][2] == "module-remap-source")
    assert "sink_name=myvrc" in load_sink[0]
    assert "source_name=myvrc_mic" in load_mic[0]
    assert "master=myvrc.monitor" in load_mic[0]
