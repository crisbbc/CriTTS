#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Prefer uv — it creates .venv, syncs deps from uv.lock, and runs.
if command -v uv >/dev/null 2>&1; then
  [ -f scripts/update_check.py ] && uv run python scripts/update_check.py &>/dev/null & disown 2>/dev/null || true
  exec uv run python main.py
fi

# Fallback: system python + manual venv (for hosts without uv)
PYTHON=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1; then PYTHON="$c"; break; fi
done
if [ -z "$PYTHON" ]; then
  echo "[ERROR] Python 3.10+ not found. Install it or install uv:" >&2
  echo "  https://www.python.org/downloads/  or  https://docs.astral.sh/uv/" >&2
  exit 1
fi

if [ ! -f .venv/bin/activate ] && [ ! -f venv/bin/activate ]; then
  echo "[INFO] Creating .venv..."
  if ! "$PYTHON" -m venv .venv 2>&1; then
    echo "[ERROR] python -m venv failed. Install python3-venv / python3-tk." >&2
    exit 1
  fi
fi
# shellcheck disable=SC1091
if [ -f .venv/bin/activate ]; then source .venv/bin/activate; else source venv/bin/activate; fi

# Install deps only when needed (fingerprint or import check)
if ! python -c "import customtkinter" >/dev/null 2>&1 || ! python scripts/fingerprint.py --check >/dev/null 2>&1; then
  echo "[INFO] Installing dependencies..."
  python scripts/install_deps.py || exit 1
  python scripts/fingerprint.py --write >/dev/null 2>&1 || true
else
  echo "[OK] Dependencies up to date."
fi

[ -f scripts/update_check.py ] && python scripts/update_check.py &>/dev/null & disown 2>/dev/null || true
exec python main.py
