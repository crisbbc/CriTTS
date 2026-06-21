#!/usr/bin/env python3
"""Install requirements.txt into a target Python environment.

Robust to virtualenvs that lack a ``pip`` module (e.g. those created with
``uv venv`` without ``--seed``). Tries, in order: pip -> uv -> ensurepip+pip.

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


def has_uv() -> bool:
    """True if the ``uv`` binary is available on PATH."""
    return shutil.which("uv") is not None


def install_with_pip(python_exe: str, req_path: Path) -> int:
    """``python -m pip install -r <req>``. Returns exit code."""
    return subprocess.call(
        [python_exe, "-m", "pip", "install", "-r", str(req_path), "--quiet"]
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

    Strategy (first success wins): pip -> uv -> ensurepip+pip.
    Returns 0 on success, non-zero if every strategy fails.
    """
    # Implemented in Task 4.
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Install requirements.txt")
    parser.add_argument("--requirements", default=str(DEFAULT_REQ),
                        help="path to requirements.txt")
    parser.add_argument("--python", default=sys.executable,
                        help="target interpreter (default: current)")
    args = parser.parse_args()
    return install_requirements(args.python, Path(args.requirements))


if __name__ == "__main__":
    sys.exit(main())
