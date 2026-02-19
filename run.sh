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

# Check if Python 3 is installed
echo "[1/3] Checking Python installation..."
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
echo "[2/3] Checking pip..."
if ! $PYTHON_CMD -m pip --version >/dev/null 2>&1; then
    echo "[ERROR] pip is not available."
    echo "Please install pip for Python 3."
    echo "On Debian/Ubuntu: sudo apt install python3-pip"
    echo "On Fedora: sudo dnf install python3-pip"
    echo "On Arch: sudo pacman -S python-pip"
    exit 1
fi
echo "[OK] pip is available."

# Function to check if all requirements are satisfied
check_requirements() {
    $PYTHON_CMD -c "import pkg_resources; pkg_resources.require(open('requirements.txt').read().splitlines())" >/dev/null 2>&1
    return $?
}

# Check if virtual environment exists, if not check if requirements are installed
echo ""
echo "[3/3] Checking dependencies..."

# Check if venv exists
if [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    echo "[INFO] Virtual environment found. Activating..."
    source "$SCRIPT_DIR/venv/bin/activate"
    # After activating venv, check if requirements are satisfied
    if ! check_requirements; then
        echo "[WARN] Some dependencies are missing or outdated."
        echo "[INFO] Installing dependencies from requirements.txt..."
        $PYTHON_CMD -m pip install -r "$SCRIPT_DIR/requirements.txt"
        if [ $? -ne 0 ]; then
            echo "[ERROR] Failed to install dependencies."
            exit 1
        fi
        echo "[OK] Dependencies installed successfully."
    else
        echo "[OK] All dependencies are satisfied."
    fi
else
    # Check if all required packages are installed with correct versions
    if ! check_requirements; then
        echo "[WARN] Some dependencies are missing or outdated."
        echo "[INFO] Installing dependencies from requirements.txt..."
        $PYTHON_CMD -m pip install -r "$SCRIPT_DIR/requirements.txt"
        if [ $? -ne 0 ]; then
            echo "[ERROR] Failed to install dependencies."
            exit 1
        fi
        echo "[OK] Dependencies installed successfully."
    else
        echo "[OK] All dependencies are satisfied."
    fi
fi

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