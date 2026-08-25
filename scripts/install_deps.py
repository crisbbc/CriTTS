#!/usr/bin/env python3
"""Install requirements.txt into a target Python environment.

Robust to virtualenvs that lack a ``pip`` module (e.g. those created with
``uv venv`` without ``--seed``, or Microsoft Store Python where ``python -m pip``
fails but ``pip.exe`` is on PATH). Tries, in order:

    1. python -m pip install   (standard venvs)
    2. pip install             (MS Store: pip.exe alias without module)
    3. uv pip install          (pip-less venvs with uv installed)
    4. ensurepip + retry pip   (bootstrap pip into the interpreter)

Intended to be invoked by the launcher scripts (run.bat / run.sh) with the
already-activated interpreter so ``sys.executable`` is the venv python:

    python scripts/install_deps.py [--requirements PATH] [--python EXE]

Exits 0 on success, non-zero on failure.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_REQ = SCRIPT_DIR / "requirements.txt"


def has_pip(python_exe: str) -> bool:
    """True if the target interpreter has a usable ``pip`` module."""
    return subprocess.call(
        [python_exe, "-m", "pip", "--version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ) == 0


def has_pip_exe() -> bool:
    """True if a ``pip`` executable is available on PATH (MS Store case)."""
    return shutil.which("pip") is not None


def has_uv() -> bool:
    """True if the ``uv`` binary is available on PATH."""
    return shutil.which("uv") is not None


def install_with_pip(python_exe: str, req_path: Path) -> int:
    """``python -m pip install -r <req>``. Returns exit code.

    Note: ``--quiet`` is intentionally NOT used.  The first time a user installs
    this stack, ``coqui-tts`` alone is ~1.5GB and ``scipy`` / ``numpy`` add more;
    seeing pip/uv's progress bars is the difference between an install that
    appears hung and one that the user can monitor.  stderr is still merged into
    stdout so any error message surfaces to the launcher immediately.
    """
    return subprocess.call(
        [python_exe, "-m", "pip", "install", "-r", str(req_path)],
        stdout=None,
        stderr=subprocess.STDOUT,
    )


def install_with_pip_exe(req_path: Path) -> int:
    """``pip install -r <req>`` via standalone pip.exe (MS Store). Returns exit code."""
    return subprocess.call(
        ["pip", "install", "-r", str(req_path)],
        stdout=None,
        stderr=subprocess.STDOUT,
    )


def install_with_uv(python_exe: str, req_path: Path) -> int:
    """``uv pip install --python <exe> -r <req>``. Returns exit code."""
    return subprocess.call(
        ["uv", "pip", "install", "--python", python_exe, "-r", str(req_path)],
        stdout=None,
        stderr=subprocess.STDOUT,
    )


def ensurepip(python_exe: str) -> int:
    """Bootstrap pip into the target interpreter. Returns exit code."""
    return subprocess.call(
        [python_exe, "-m", "ensurepip", "--upgrade"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _detect_pkg_manager() -> str:
    """Return the system package manager in use: apt, dnf, pacman, zypper, brew, or unknown."""
    if sys.platform == "darwin" and shutil.which("brew"):
        return "brew"
    if shutil.which("apt-get"):
        return "apt"
    if shutil.which("dnf"):
        return "dnf"
    if shutil.which("pacman"):
        return "pacman"
    if shutil.which("zypper"):
        return "zypper"
    return "unknown"


def _pkg_install_cmd(pkg: str) -> str:
    """Return a copy-pasteable install command for a package on the current system."""
    pkg_mgr = _detect_pkg_manager()
    prefix = "sudo " if pkg_mgr != "brew" else ""
    if pkg_mgr == "apt":
        return f"{prefix}apt install {pkg}"
    if pkg_mgr == "dnf":
        return f"{prefix}dnf install {pkg}"
    if pkg_mgr == "pacman":
        return f"{prefix}pacman -S {pkg}"
    if pkg_mgr == "zypper":
        return f"{prefix}zypper install {pkg}"
    if pkg_mgr == "brew":
        return f"brew install {pkg}"
    return pkg


def _find_system_library(name: str) -> str | None:
    """Locate a shared library on the system (uses ctypes / ldconfig)."""
    import ctypes.util

    return ctypes.util.find_library(name)


# ---------------------------------------------------------------------------
# System dependency checks
#
# Each entry maps a human label to a (check_fn, missing_message, pkg_map)
# tuple.  check_fn() returns True when the dependency is satisfied.
# pkg_map keys are package-manager names (apt, dnf, pacman, zypper, brew).
# ---------------------------------------------------------------------------

_SYSTEM_DEPS: list[tuple[str, Callable[[], bool], str, dict[str, str]]] = []  # noqa: E501


def _register_system_deps() -> None:
    """Populate _SYSTEM_DEPS — delayed so we can use closures referencing helpers."""
    if _SYSTEM_DEPS:
        return  # already registered

    _SYSTEM_DEPS.extend([
        (
            "Tk (GUI toolkit)",
            lambda: subprocess.call(
                [sys.executable, "-c", "import tkinter"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            ) == 0,
            "Required by customtkinter for the graphical interface.",
            {"apt": "python3-tk", "dnf": "python3-tkinter", "pacman": "tk",
             "zypper": "python3-tk", "brew": "python-tk@3.12"},
        ),
        (
            "PortAudio (audio I/O)",
            lambda: sys.platform == "win32" or _find_system_library("portaudio") is not None,
            "Required by sounddevice for microphone and speaker access.",
            {"apt": "libportaudio2", "dnf": "portaudio", "pacman": "portaudio",
             "zypper": "libportaudio2", "brew": "portaudio"},
        ),
        (
            "libsndfile (audio file I/O)",
            lambda: sys.platform == "win32" or _find_system_library("sndfile") is not None,
            "Required by soundfile for reading WAV audio.",
            {"apt": "libsndfile1", "dnf": "libsndfile", "pacman": "libsndfile",
             "zypper": "libsndfile1", "brew": "libsndfile"},
        ),
        (
            "ffmpeg (MP3 decoding)",
            lambda: shutil.which("ffmpeg") is not None,
            "Required for MP3 audio decoding (Edge TTS output).",
            {"apt": "ffmpeg", "dnf": "ffmpeg", "pacman": "ffmpeg",
             "zypper": "ffmpeg", "brew": "ffmpeg"},
        ),
    ])


def check_system_deps() -> None:
    """Check for required system-level libraries and print guidance for any missing.

    Covers: Tk (customtkinter), PortAudio (sounddevice), libsndfile (soundfile),
    and ffmpeg (MP3 decoding).  Each check is lightweight — library lookups use
    ``ctypes.util.find_library`` / ``shutil.which``, and the Tk check spawns a
    one-shot subprocess.
    """
    _register_system_deps()

    pkg_mgr = _detect_pkg_manager()
    missing: list[tuple[str, str, str]] = []  # (label, description, cmd)

    for label, check, description, pkg_map in _SYSTEM_DEPS:
        try:
            ok = check()
        except Exception:
            ok = False
        if ok:
            continue
        pkg = pkg_map.get(pkg_mgr, list(pkg_map.values())[0])
        cmd = _pkg_install_cmd(pkg)
        missing.append((label, description, cmd))

    if not missing:
        return

    lines = ["\n[WARN] Some system dependencies are missing:\n"]
    for label, description, cmd in missing:
        lines.append(f"  • {label} — {description}")
        lines.append(f"    Install:  {cmd}")
    lines.append("")
    print("\n".join(lines), file=sys.stderr)


def install_requirements(python_exe: str, req_path: Path) -> int:
    """Install ``req_path`` into the environment of ``python_exe``.

    Strategy (first success wins):
      1. python -m pip   -- standard venvs ship with it.
      2. pip             -- MS Store: pip.exe alias without module.
      3. uv              -- works on pip-less venvs (e.g. created with `uv venv`).
      4. ensurepip+pip   -- bootstrap pip into the venv, then retry.

    Returns 0 on success, non-zero if every strategy fails.
    """
    print(
        f"Installing Python dependencies from {req_path.name} "
        "-- this can take several minutes on a fresh install "
        "(coqui-tts alone is ~1.5GB, plus numpy/scipy wheels).",
        flush=True,
    )

    # 1) python -m pip -- standard venvs ship with it.
    if has_pip(python_exe):
        if install_with_pip(python_exe, req_path) == 0:
            return 0

    # 2) pip.exe direct -- MS Store Python has pip as an App Execution Alias
    #    even when `python -m pip` fails (module not on path).
    if has_pip_exe():
        if install_with_pip_exe(req_path) == 0:
            return 0

    # 3) uv -- works on pip-less venvs (e.g. created with `uv venv`).
    if has_uv():
        if install_with_uv(python_exe, req_path) == 0:
            return 0

    # 4) Bootstrap pip into the venv, then retry.
    if ensurepip(python_exe) == 0:
        if install_with_pip(python_exe, req_path) == 0:
            return 0

    print("All install strategies failed (pip, pip.exe, uv, ensurepip).", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Install requirements.txt")
    parser.add_argument("--requirements", default=str(DEFAULT_REQ),
                        help="path to requirements.txt")
    parser.add_argument("--python", default=sys.executable,
                        help="target interpreter (default: current)")
    args = parser.parse_args()
    req_path = Path(args.requirements)
    if not req_path.exists():
        print(f"requirements file not found: {req_path}", file=sys.stderr)
        return 1
    result = install_requirements(args.python, req_path)
    # Verify system-level libraries are present — pip can't install these.
    check_system_deps()
    return result


if __name__ == "__main__":
    sys.exit(main())
