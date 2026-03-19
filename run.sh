#!/bin/bash
# CriTTS Launcher for Linux
# Checks requirements and launches the application

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "========================================"
echo "  CriTTS Launcher"
echo "========================================"
echo ""

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check for Git and Auto-Update
echo "[1/4] Checking for Git and updating scripts..."
if ! command_exists git; then
    echo "[WARN] Git is not installed. Attempting to install Git..."
    if command_exists apt; then
        sudo apt update && sudo apt install -y git
    elif command_exists dnf; then
        sudo dnf install -y git
    elif command_exists pacman; then
        sudo pacman -S --noconfirm git
    else
        echo "[WARN] Unsupported package manager. Could not install Git automatically."
    fi
fi

if command_exists git; then
    echo "[INFO] Checking for updates from remote repository..."

    # Detect the current branch
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
    CURRENT_BRANCH="${CURRENT_BRANCH:-main}"

    # Try to use the upstream tracking branch; fall back to current branch
    TRACKING=$(git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null)
    if [ -n "$TRACKING" ]; then
        REMOTE_BRANCH="${TRACKING#origin/}"
    else
        REMOTE_BRANCH="$CURRENT_BRANCH"
    fi

    git fetch origin "$REMOTE_BRANCH" >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        LOCAL=$(git rev-parse HEAD 2>/dev/null)
        REMOTE=$(git rev-parse "origin/$REMOTE_BRANCH" 2>/dev/null)

        if [ -n "$LOCAL" ] && [ -n "$REMOTE" ]; then
            if [ "$LOCAL" != "$REMOTE" ]; then
                echo "[INFO] Updates found. Applying updates and replacing local changes..."
                git reset --hard "origin/$REMOTE_BRANCH" >/dev/null 2>&1
                if [ $? -eq 0 ]; then
                    echo "[OK] Successfully updated to the latest $REMOTE_BRANCH branch."
                    # Re-run the script to ensure we are using the updated version
                    exec bash "$0" "$@"
                else
                    echo "[WARN] Failed to apply updates."
                fi
            else
                echo "[OK] Scripts are up to date."
            fi
        else
            echo "[WARN] Could not determine local or remote commit. Skipping update."
        fi
    else
        echo "[WARN] Failed to fetch updates from remote repository."
    fi
else
    echo "[WARN] Git could not be found or installed. Skipping update check."
fi

# Check if Python 3 is installed
echo ""
echo "[2/4] Checking Python installation..."
if command_exists python3; then
    PYTHON_CMD="python3"
elif command_exists python; then
    PYTHON_CMD="python"
else
    echo "[ERROR] Python is not installed."
    echo ""
    echo "Please install Python 3.8 or higher."
    echo "On Debian/Ubuntu: sudo apt install python3 python3-pip"
    echo "On Fedora: sudo dnf install python3 python3-pip"
    echo "On Arch: sudo pacman -S python python-pip"
    echo ""
    exit 1
fi

# Display Python version
PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | cut -d' ' -f2)
echo "[OK] Python $PYTHON_VERSION found."

# Check if pip is available
echo ""
echo "[3/4] Checking pip..."
if ! $PYTHON_CMD -m pip --version >/dev/null 2>&1; then
    echo "[ERROR] pip is not available."
    echo "Please install pip for Python 3."
    echo "On Debian/Ubuntu: sudo apt install python3-pip"
    echo "On Fedora: sudo dnf install python3-pip"
    echo "On Arch: sudo pacman -S python-pip"
    exit 1
fi
echo "[OK] pip is available."

# Install / update dependencies from requirements.txt
echo ""
echo "[4/4] Checking and installing dependencies..."

# Activate virtual environment if it exists
if [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    echo "[INFO] Virtual environment found. Activating..."
    source "$SCRIPT_DIR/venv/bin/activate"
fi

$PYTHON_CMD -m pip install -r "$SCRIPT_DIR/requirements.txt" --quiet
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to install dependencies."
    exit 1
fi
echo "[OK] Dependencies are satisfied."

# Launch the application
echo ""
echo "========================================"
echo "  Launching CriTTS..."
echo "========================================"
echo ""

$PYTHON_CMD "$SCRIPT_DIR/main.py"

# If the application exits with an error, notify
if [ $? -ne 0 ]; then
    echo ""
    echo "[ERROR] Application exited with an error."
fi