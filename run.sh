#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
#  CriTTS Launcher for Linux / macOS
#
#  Fast path: skips redundant work on repeated launches.
#  - Venv activated first
#  - pip install only runs when requirements.txt changed (fingerprint)
#  - Update check is fire-and-forget, never blocks startup
#  - Works whether repo was git-cloned or ZIP-downloaded
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# -----------------------------------------------------------------------------
# Helpers: install Python on systems where it isn't already on PATH.
# -----------------------------------------------------------------------------
install_python_system() {
    INSTALL_ATTEMPTS=$((${INSTALL_ATTEMPTS:-0} + 1))
    local SUDO=""
    if [ "$(id -u)" -ne 0 ]; then
        SUDO="sudo"
    fi
    if command -v apt-get >/dev/null 2>&1; then
        echo "[INFO] Detected apt-get (Debian/Ubuntu). Installing python3, python3-pip, python3-venv, python3-tk, libportaudio2, libsndfile1, ffmpeg..."
        # shellcheck disable=SC2086
        $SUDO apt-get update -qq 2>&1 | tail -n 5 || true
        # shellcheck disable=SC2086
        $SUDO apt-get install -y python3 python3-pip python3-venv python3-tk libportaudio2 libsndfile1 ffmpeg
    elif command -v dnf >/dev/null 2>&1; then
        echo "[INFO] Detected dnf (Fedora/RHEL). Installing python3, python3-pip, python3-devel, python3-tkinter, portaudio, libsndfile, ffmpeg..."
        # shellcheck disable=SC2086
        $SUDO dnf install -y python3 python3-pip python3-devel python3-tkinter portaudio libsndfile ffmpeg
    elif command -v pacman >/dev/null 2>&1; then
        echo "[INFO] Detected pacman (Arch). Installing python, python-pip, tk, portaudio, libsndfile, ffmpeg..."
        # shellcheck disable=SC2086
        $SUDO pacman -S --noconfirm python python-pip tk portaudio libsndfile ffmpeg
    elif command -v brew >/dev/null 2>&1; then
        echo "[INFO] Detected Homebrew (macOS). Installing python@3.12..."
        brew install python@3.12
    else
        echo "[ERROR] No supported package manager found (apt-get, dnf, pacman, brew)." >&2
        return 1
    fi
}

install_python_uv() {
    INSTALL_ATTEMPTS=$((${INSTALL_ATTEMPTS:-0} + 1))
    local UV_BIN_DIR="$HOME/.local/bin"
    local UV=""
    if command -v uv >/dev/null 2>&1; then
        UV="$(command -v uv)"
    elif [ -x "$UV_BIN_DIR/uv" ]; then
        UV="$UV_BIN_DIR/uv"
    else
        echo "[INFO] Installing uv..."
        if ! command -v curl >/dev/null 2>&1; then
            echo "[ERROR] curl is required to bootstrap uv." >&2
            return 1
        fi
        if ! curl -LsSf https://astral.sh/uv/install.sh | sh; then
            echo "[ERROR] uv install failed." >&2
            return 1
        fi
        UV="$UV_BIN_DIR/uv"
    fi

    echo "[INFO] Asking uv to install Python 3.12..."
    if ! "$UV" python install 3.12; then
        echo "[ERROR] uv python install failed." >&2
        return 1
    fi

    # uv does NOT drop a python shim on PATH by default -- get the absolute path.
    local PY_PATH
    PY_PATH="$("$UV" python find 3.12 2>/dev/null || true)"
    if [ -z "$PY_PATH" ] || [ ! -x "$PY_PATH" ]; then
        echo "[ERROR] uv python find returned no usable interpreter path." >&2
        return 1
    fi
    export CRITTS_PYTHON="$PY_PATH"
    export PATH="$UV_BIN_DIR:$HOME/.cargo/bin:$PATH"
    echo "[OK] Python installed via uv at: $PY_PATH"
}

echo ""
echo "========================================"
echo "  CriTTS Launcher"
echo "========================================"
echo ""

# ---------------------------------------------------------------------------
# [1] Activate virtual environment if it exists
# ---------------------------------------------------------------------------
if [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/venv/bin/activate"
    PYTHON="python"
    echo "[OK] Virtual environment ready."
elif [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.venv/bin/activate"
    PYTHON="python"
    echo "[OK] Virtual environment ready."
else
    # Detect Python on PATH; if missing, prompt to install and retry once. After
    # one install attempt where Python is STILL not on PATH, abort with a manual
    # recovery message instead of re-prompting in a loop. INSTALL_ATTEMPTS is
    # incremented at the top of each install_* helper so the counter reflects
    # how many times we've asked install to do something.
    INSTALL_ATTEMPTS=0
    while true; do
        if [ -n "${CRITTS_PYTHON:-}" ] && [ -x "$CRITTS_PYTHON" ]; then
            PYTHON="$CRITTS_PYTHON"
            break
        fi
        if command -v python3 &>/dev/null; then
            PYTHON="python3"
            break
        fi
        if command -v python &>/dev/null; then
            PYTHON="python"
            break
        fi

        # No Python on PATH. If install was already attempted once and we're back
        # here, the install succeeded but Python still isn't exposed -- abort
        # cleanly with a recovery message rather than re-prompting.
        if [ "${INSTALL_ATTEMPTS:-0}" -ge 1 ]; then
            echo "" >&2
            echo "[ERROR] Python is still not on PATH after ${INSTALL_ATTEMPTS:-1} install attempt(s)." >&2
            echo "" >&2
            echo "To recover, install Python manually:" >&2
            echo "  Debian/Ubuntu: sudo apt install python3 python3-pip python3-venv" >&2
            echo "  Fedora:        sudo dnf install python3 python3-pip python3-devel" >&2
            echo "  Arch:          sudo pacman -S python python-pip" >&2
            echo "  macOS:         brew install python@3.12" >&2
            echo "  Or use uv:     https://docs.astral.sh/uv/" >&2
            echo "  Or the official installer: https://www.python.org/downloads/" >&2
            exit 1
        fi

        echo ""
        echo "[WARN] Python 3 was not detected on PATH."
        echo ""
        echo "How would you like to install Python?"
        echo "  [1] Install via system package manager (recommended; may need sudo)"
        echo "      (supports apt, dnf, pacman, and Homebrew)"
        echo "  [2] Install uv first, then uv installs Python (no sudo, lightweight)"
        echo "  [3] Cancel -- I'll install Python myself"
        echo ""
        PY_INSTALL_CHOICE=""
        read -r -p "Enter 1, 2, or 3 (default 3): " PY_INSTALL_CHOICE
        PY_INSTALL_CHOICE="${PY_INSTALL_CHOICE:-3}"

        case "$PY_INSTALL_CHOICE" in
            1) install_python_system || { echo "[ERROR] install_python_system failed; see messages above." >&2; exit 1; } ;;
            2) install_python_uv || { echo "[ERROR] install_python_uv failed; see messages above." >&2; exit 1; } ;;
            *) echo ""
               echo "Please install Python 3.8+ manually:"
               echo "  Debian/Ubuntu: sudo apt install python3 python3-pip python3-venv"
               echo "  Fedora:        sudo dnf install python3 python3-pip python3-devel"
               echo "  Arch:          sudo pacman -S python python-pip"
               echo "  macOS:         brew install python@3.12"
               exit 1 ;;
        esac
        # Loop continues: re-detects. If found, breaks. If still nothing, the
        # abort block above fires on the next iteration.
    done
fi

# ---------------------------------------------------------------------------
# [1b] Auto-create virtual environment when none exists
#
# System Python on Arch, Fedora, and Debian 12+ blocks direct package installs
# (PEP 668 “externally managed”).  We create a venv so ``install_deps.py`` has a
# writable site-packages.  Prefer ``uv venv`` when available (faster); fall back
# to ``python -m venv``.
# ---------------------------------------------------------------------------
if [ ! -f "$SCRIPT_DIR/.venv/bin/activate" ] && [ ! -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    echo "[INFO] No virtual environment found — creating one..."
    VENV_MADE=false
    if command -v uv >/dev/null 2>&1; then
        if uv venv --python "$PYTHON" "$SCRIPT_DIR/.venv" 2>&1; then
            VENV_MADE=true
        else
            echo "[WARN] uv venv failed, falling back to python -m venv..."
        fi
    fi
    if [ "$VENV_MADE" = false ]; then
        if ! "$PYTHON" -m venv "$SCRIPT_DIR/.venv"; then
            echo "[ERROR] Could not create virtual environment with python -m venv." >&2
            echo "  Install python3-venv (Debian/Ubuntu) or python (Arch) and retry." >&2
            exit 1
        fi
    fi
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.venv/bin/activate"
    PYTHON="python"
    echo "[OK] Virtual environment created and activated at $SCRIPT_DIR/.venv"
fi

# ---------------------------------------------------------------------------
# [2] Verify Python version
# ---------------------------------------------------------------------------
PY_VER="$("$PYTHON" --version 2>&1 | cut -d' ' -f2)"
echo "[OK] Python $PY_VER found."

# ---------------------------------------------------------------------------
# [3] Install dependencies -- only when requirements.txt changed
#     No hard pip gate: install_deps.py tries pip -> pip.exe -> uv -> ensurepip
# ---------------------------------------------------------------------------
if [ -f "$SCRIPT_DIR/scripts/fingerprint.py" ]; then
    if "$PYTHON" "$SCRIPT_DIR/scripts/fingerprint.py" --check >/dev/null 2>&1; then
        echo "[OK] Dependencies up to date."
    else
        echo "[INFO] Dependencies need updating..."
        if ! "$PYTHON" "$SCRIPT_DIR/scripts/install_deps.py"; then
            echo "[ERROR] Failed to install dependencies."
            echo "  Tried pip, uv, and ensurepip. To resolve:"
            echo "    - Install uv:  https://docs.astral.sh/uv/"
            echo "    - Or recreate the venv with pip:  python -m venv --clear .venv"
            exit 1
        fi
        "$PYTHON" "$SCRIPT_DIR/scripts/fingerprint.py" --write >/dev/null 2>&1
        echo "[OK] Dependencies updated."
    fi
else
    echo "[INFO] Installing dependencies (first run)..."
    if ! "$PYTHON" "$SCRIPT_DIR/scripts/install_deps.py"; then
        echo "[ERROR] Failed to install dependencies."
        echo "  Tried pip, uv, and ensurepip. To resolve:"
        echo "    - Install uv:  https://docs.astral.sh/uv/"
        echo "    - Or recreate the venv with pip:  python -m venv --clear .venv"
        exit 1
    fi
    if [ -f "$SCRIPT_DIR/scripts/fingerprint.py" ]; then
        "$PYTHON" "$SCRIPT_DIR/scripts/fingerprint.py" --write >/dev/null 2>&1
    fi
    echo "[OK] Dependencies installed."
fi

# ---------------------------------------------------------------------------
# [4] Background update check -- fire and forget
# ---------------------------------------------------------------------------
if [ -f "$SCRIPT_DIR/scripts/update_check.py" ]; then
    "$PYTHON" "$SCRIPT_DIR/scripts/update_check.py" &>/dev/null &
    disown 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# [5] Launch
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo "  Launching CriTTS..."
echo "========================================"
echo ""

"$PYTHON" "$SCRIPT_DIR/main.py"
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "[ERROR] Application exited with code $EXIT_CODE."
fi

exit $EXIT_CODE
