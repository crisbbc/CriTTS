#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
#  CriTTS Launcher for Linux / macOS
#
#  Fast path: skips redundant work on repeated launches.
#  - Venv activated first
#  - pip install only runs when requirements.txt changed
#  - Update check is fire-and-forget, never blocks startup
#  - Works whether repo was git-cloned or ZIP-downloaded
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

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
    # Resolve Python — try python3 first (Linux convention), then python
    if command -v python3 &>/dev/null; then
        PYTHON="python3"
    elif command -v python &>/dev/null; then
        PYTHON="python"
    else
        echo "[ERROR] Python 3 is not installed."
        echo ""
        echo "Install it with your package manager:"
        echo "  Debian/Ubuntu: sudo apt install python3 python3-pip"
        echo "  Fedora:        sudo dnf install python3 python3-pip"
        echo "  Arch:          sudo pacman -S python python-pip"
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# [2] Verify Python version
# ---------------------------------------------------------------------------
PY_VER="$("$PYTHON" --version 2>&1 | cut -d' ' -f2)"
echo "[OK] Python $PY_VER found."

# ---------------------------------------------------------------------------
# [3] Install dependencies -- only when requirements.txt changed
# ---------------------------------------------------------------------------
if [ -f "$SCRIPT_DIR/scripts/fingerprint.py" ]; then
    if "$PYTHON" "$SCRIPT_DIR/scripts/fingerprint.py" --check >/dev/null 2>&1; then
        echo "[OK] Dependencies up to date."
    else
        echo "[INFO] Dependencies need updating..."
        "$PYTHON" -m pip install -r "$SCRIPT_DIR/requirements.txt" --quiet
        "$PYTHON" "$SCRIPT_DIR/scripts/fingerprint.py" --write >/dev/null 2>&1
        echo "[OK] Dependencies updated."
    fi
else
    echo "[INFO] Installing dependencies (first run)..."
    "$PYTHON" -m pip install -r "$SCRIPT_DIR/requirements.txt" --quiet
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
