"""Unit tests for scripts/install_deps.py install strategy.

All subprocess/shutil calls are mocked -- these tests are hermetic and fast.
They pin down the pip -> pip.exe -> uv -> ensurepip+pip fallback order.
"""
from pathlib import Path

import scripts.install_deps as mod


def _record(calls, name):
    """Return a fake that appends (name, python_exe) to calls and returns 0."""
    def _fake(python_exe, req_path):
        calls.append((name, python_exe))
        return 0
    return _fake


def _record_pip_exe(calls, name):
    """Return a fake for install_with_pip_exe (single-arg: req_path)."""
    def _fake(req_path):
        calls.append((name, "py.exe"))
        return 0
    return _fake


def test_uses_pip_module_when_available(monkeypatch):
    """Strategy 1: python -m pip works -> done, no fallbacks tried."""
    monkeypatch.setattr(mod, "has_pip", lambda exe: True)
    monkeypatch.setattr(mod, "has_pip_exe", lambda: True)
    monkeypatch.setattr(mod, "has_uv", lambda: True)
    calls = []
    monkeypatch.setattr(mod, "install_with_pip", _record(calls, "pip"))
    monkeypatch.setattr(mod, "install_with_pip_exe", lambda req: 99)
    monkeypatch.setattr(mod, "install_with_uv", lambda exe, req: 99)
    monkeypatch.setattr(mod, "ensurepip", lambda exe: 99)

    rc = mod.install_requirements("py.exe", Path("requirements.txt"))

    assert rc == 0
    assert calls == [("pip", "py.exe")]


def test_falls_back_to_pip_exe_when_pip_module_missing(monkeypatch):
    """Strategy 2: python -m pip absent -> pip.exe direct succeeds."""
    monkeypatch.setattr(mod, "has_pip", lambda exe: False)
    monkeypatch.setattr(mod, "has_pip_exe", lambda: True)
    monkeypatch.setattr(mod, "has_uv", lambda: True)
    calls = []
    monkeypatch.setattr(mod, "install_with_pip", lambda exe, req: 99)
    monkeypatch.setattr(mod, "install_with_pip_exe", _record_pip_exe(calls, "pip.exe"))
    monkeypatch.setattr(mod, "install_with_uv", lambda exe, req: 99)
    monkeypatch.setattr(mod, "ensurepip", lambda exe: 99)

    rc = mod.install_requirements("py.exe", Path("requirements.txt"))

    assert rc == 0
    assert calls == [("pip.exe", "py.exe")]


def test_pip_module_fails_falls_back_to_pip_exe(monkeypatch):
    """Strategy 1 fails -> strategy 2 (pip.exe) succeeds."""
    monkeypatch.setattr(mod, "has_pip", lambda exe: True)
    monkeypatch.setattr(mod, "has_pip_exe", lambda: True)
    monkeypatch.setattr(mod, "has_uv", lambda: True)
    calls = []
    monkeypatch.setattr(mod, "install_with_pip", lambda exe, req: calls.append(("pip", exe)) or 1)
    monkeypatch.setattr(mod, "install_with_pip_exe", _record_pip_exe(calls, "pip.exe"))
    monkeypatch.setattr(mod, "install_with_uv", lambda exe, req: 99)
    monkeypatch.setattr(mod, "ensurepip", lambda exe: 99)

    rc = mod.install_requirements("py.exe", Path("requirements.txt"))

    assert rc == 0
    assert calls == [("pip", "py.exe"), ("pip.exe", "py.exe")]


def test_falls_back_to_uv_when_pip_and_pip_exe_missing(monkeypatch):
    """Strategy 1+2 absent -> strategy 3 (uv) succeeds."""
    monkeypatch.setattr(mod, "has_pip", lambda exe: False)
    monkeypatch.setattr(mod, "has_pip_exe", lambda: False)
    monkeypatch.setattr(mod, "has_uv", lambda: True)
    calls = []
    monkeypatch.setattr(mod, "install_with_pip", lambda exe, req: 99)
    monkeypatch.setattr(mod, "install_with_pip_exe", lambda req: 99)
    monkeypatch.setattr(mod, "install_with_uv", _record(calls, "uv"))
    monkeypatch.setattr(mod, "ensurepip", lambda exe: 99)

    rc = mod.install_requirements("py.exe", Path("requirements.txt"))

    assert rc == 0
    assert calls == [("uv", "py.exe")]


def test_falls_back_to_ensurepip_when_neither_pip_nor_uv(monkeypatch):
    """Strategy 1+2+3 absent -> strategy 4 (ensurepip + pip retry) succeeds."""
    monkeypatch.setattr(mod, "has_pip", lambda exe: False)
    monkeypatch.setattr(mod, "has_pip_exe", lambda: False)
    monkeypatch.setattr(mod, "has_uv", lambda: False)
    calls = []
    monkeypatch.setattr(mod, "install_with_pip", _record(calls, "pip"))
    monkeypatch.setattr(mod, "install_with_pip_exe", lambda req: 99)
    monkeypatch.setattr(mod, "install_with_uv", lambda exe, req: 99)
    monkeypatch.setattr(mod, "ensurepip", lambda exe: calls.append(("ensurepip", exe)) or 0)

    rc = mod.install_requirements("py.exe", Path("requirements.txt"))

    assert rc == 0
    assert ("ensurepip", "py.exe") in calls
    assert ("pip", "py.exe") in calls


def test_returns_nonzero_when_all_strategies_fail(monkeypatch):
    """Every strategy fails -> non-zero exit."""
    monkeypatch.setattr(mod, "has_pip", lambda exe: False)
    monkeypatch.setattr(mod, "has_pip_exe", lambda: False)
    monkeypatch.setattr(mod, "has_uv", lambda: False)
    monkeypatch.setattr(mod, "install_with_pip", lambda exe, req: 1)
    monkeypatch.setattr(mod, "install_with_pip_exe", lambda req: 1)
    monkeypatch.setattr(mod, "install_with_uv", lambda exe, req: 1)
    monkeypatch.setattr(mod, "ensurepip", lambda exe: 1)

    rc = mod.install_requirements("py.exe", Path("requirements.txt"))

    assert rc != 0


def test_full_cascade_pip_fails_pip_exe_fails_uv_fails_ensurepip_succeeds(monkeypatch):
    """Full cascade: pip present+fails -> pip.exe fails -> uv fails -> ensurepip -> pip retry succeeds."""
    monkeypatch.setattr(mod, "has_pip", lambda exe: True)
    monkeypatch.setattr(mod, "has_pip_exe", lambda: True)
    monkeypatch.setattr(mod, "has_uv", lambda: True)
    calls = []
    pip_returns = [1, 0]  # first pip call fails, second (after ensurepip) succeeds

    def _fake_pip(python_exe, req_path):
        calls.append(("pip", python_exe))
        return pip_returns.pop(0)

    monkeypatch.setattr(mod, "install_with_pip", _fake_pip)
    monkeypatch.setattr(mod, "install_with_pip_exe",
                        lambda req: calls.append(("pip.exe", "py.exe")) or 1)
    monkeypatch.setattr(mod, "install_with_uv",
                        lambda exe, req: calls.append(("uv", exe)) or 1)
    monkeypatch.setattr(mod, "ensurepip",
                        lambda exe: calls.append(("ensurepip", exe)) or 0)

    rc = mod.install_requirements("py.exe", Path("requirements.txt"))

    assert rc == 0
    assert calls == [
        ("pip", "py.exe"),
        ("pip.exe", "py.exe"),
        ("uv", "py.exe"),
        ("ensurepip", "py.exe"),
        ("pip", "py.exe"),
    ]
