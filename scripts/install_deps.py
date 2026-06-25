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
    """``python -m pip install -r <req>``. Returns exit code."""
    return subprocess.call(
        [python_exe, "-m", "pip", "install", "-r", str(req_path), "--quiet"]
    )


def install_with_pip_exe(req_path: Path) -> int:
    """``pip install -r <req>`` via standalone pip.exe (MS Store). Returns exit code."""
    return subprocess.call(
        ["pip", "install", "-r", str(req_path), "--quiet"]
    )


def install_with_uv(python_exe: str, req_path: Path) -> int:
    """``uv pip install --python <exe> -r <req>``. Returns exit code."""
    return subprocess.call(
        ["uv", "pip", "install", "--python", python_exe, "-r", str(req_path), "--quiet"]
    )


def ensurepip(python_exe: str) -> int:
    """Bootstrap pip into the target interpreter. Returns exit code."""
    return subprocess.call(
        [python_exe, "-m", "ensurepip", "--upgrade"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def install_requirements(python_exe: str, req_path: Path) -> int:
    """Install ``req_path`` into the environment of ``python_exe``.

    Strategy (first success wins):
      1. python -m pip   -- standard venvs ship with it.
      2. pip             -- MS Store: pip.exe alias without module.
      3. uv              -- works on pip-less venvs (e.g. created with `uv venv`).
      4. ensurepip+pip   -- bootstrap pip into the venv, then retry.

    Returns 0 on success, non-zero if every strategy fails.
    """
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
    return install_requirements(args.python, req_path)


if __name__ == "__main__":
    sys.exit(main())
