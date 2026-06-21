"""Unit tests for scripts/install_deps.py install strategy.

All subprocess/shutil calls are mocked — these tests are hermetic and fast.
They pin down the pip -> uv -> ensurepip+pip fallback order.
"""
from pathlib import Path

import scripts.install_deps as mod


def _record(calls, name):
    """Return a fake that appends (name, python_exe) to calls and returns 0."""
    def _fake(python_exe, req_path):
        calls.append((name, python_exe))
        return 0
    return _fake


def test_uses_pip_when_available(monkeypatch):
    monkeypatch.setattr(mod, "has_pip", lambda exe: True)
    monkeypatch.setattr(mod, "has_uv", lambda: True)
    calls = []
    monkeypatch.setattr(mod, "install_with_pip", _record(calls, "pip"))
    monkeypatch.setattr(mod, "install_with_uv", lambda exe, req: 99)
    monkeypatch.setattr(mod, "ensurepip", lambda exe: 99)

    rc = mod.install_requirements("py.exe", Path("requirements.txt"))

    assert rc == 0
    assert calls == [("pip", "py.exe")]


def test_falls_back_to_uv_when_pip_missing(monkeypatch):
    monkeypatch.setattr(mod, "has_pip", lambda exe: False)
    monkeypatch.setattr(mod, "has_uv", lambda: True)
    calls = []
    monkeypatch.setattr(mod, "install_with_pip", lambda exe, req: 99)
    monkeypatch.setattr(mod, "install_with_uv", _record(calls, "uv"))
    monkeypatch.setattr(mod, "ensurepip", lambda exe: 99)

    rc = mod.install_requirements("py.exe", Path("requirements.txt"))

    assert rc == 0
    assert calls == [("uv", "py.exe")]


def test_pip_present_but_fails_falls_back_to_uv(monkeypatch):
    monkeypatch.setattr(mod, "has_pip", lambda exe: True)
    monkeypatch.setattr(mod, "has_uv", lambda: True)
    calls = []
    monkeypatch.setattr(mod, "install_with_pip", lambda exe, req: calls.append(("pip", exe)) or 1)
    monkeypatch.setattr(mod, "install_with_uv", _record(calls, "uv"))
    monkeypatch.setattr(mod, "ensurepip", lambda exe: 99)

    rc = mod.install_requirements("py.exe", Path("requirements.txt"))

    assert rc == 0
    assert calls == [("pip", "py.exe"), ("uv", "py.exe")]


def test_falls_back_to_ensurepip_when_neither_pip_nor_uv(monkeypatch):
    monkeypatch.setattr(mod, "has_pip", lambda exe: False)
    monkeypatch.setattr(mod, "has_uv", lambda: False)
    calls = []
    monkeypatch.setattr(mod, "install_with_pip", _record(calls, "pip"))
    monkeypatch.setattr(mod, "install_with_uv", lambda exe, req: 99)
    monkeypatch.setattr(mod, "ensurepip", lambda exe: calls.append(("ensurepip", exe)) or 0)

    rc = mod.install_requirements("py.exe", Path("requirements.txt"))

    assert rc == 0
    assert ("ensurepip", "py.exe") in calls
    assert ("pip", "py.exe") in calls


def test_returns_nonzero_when_all_strategies_fail(monkeypatch):
    monkeypatch.setattr(mod, "has_pip", lambda exe: False)
    monkeypatch.setattr(mod, "has_uv", lambda: False)
    monkeypatch.setattr(mod, "install_with_pip", lambda exe, req: 1)
    monkeypatch.setattr(mod, "install_with_uv", lambda exe, req: 1)
    monkeypatch.setattr(mod, "ensurepip", lambda exe: 1)

    rc = mod.install_requirements("py.exe", Path("requirements.txt"))

    assert rc != 0


def test_pip_and_uv_both_fail_then_ensurepip_and_pip_retry(monkeypatch):
    """Full cascade: pip present+fails -> uv fails -> ensurepip -> pip retry succeeds."""
    monkeypatch.setattr(mod, "has_pip", lambda exe: True)
    monkeypatch.setattr(mod, "has_uv", lambda: True)
    calls = []
    pip_returns = [1, 0]  # first pip call fails, second (after ensurepip) succeeds

    def _fake_pip(python_exe, req_path):
        calls.append(("pip", python_exe))
        return pip_returns.pop(0)

    monkeypatch.setattr(mod, "install_with_pip", _fake_pip)
    monkeypatch.setattr(mod, "install_with_uv",
                        lambda exe, req: calls.append(("uv", exe)) or 1)
    monkeypatch.setattr(mod, "ensurepip",
                        lambda exe: calls.append(("ensurepip", exe)) or 0)

    rc = mod.install_requirements("py.exe", Path("requirements.txt"))

    assert rc == 0
    assert calls == [
        ("pip", "py.exe"),
        ("uv", "py.exe"),
        ("ensurepip", "py.exe"),
        ("pip", "py.exe"),
    ]
