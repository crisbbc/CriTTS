@echo off
REM CriTTS Launcher for Windows
REM Checks requirements and launches the application

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   CriTTS Launcher
echo ========================================
echo.

REM Get the directory where this batch file is located
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM Check if Python is installed
echo [1/3] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo.
    echo Please install Python 3.8 or higher from:
    echo https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

REM Display Python version
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [OK] Python !PYTHON_VERSION! found.

REM Check if pip is available
echo.
echo [2/3] Checking pip...
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] pip is not available.
    echo Please ensure pip is installed with your Python installation.
    pause
    exit /b 1
)
echo [OK] pip is available.

REM Check if virtual environment exists, if not check if requirements are installed
echo.
echo [3/3] Checking dependencies...

REM Check if venv exists
if exist "%SCRIPT_DIR%venv\Scripts\activate.bat" (
    echo [INFO] Virtual environment found. Activating...
    call "%SCRIPT_DIR%venv\Scripts\activate.bat"
    REM After activating venv, check if requirements are satisfied
    python -c "import customtkinter, edge_tts, langid, sounddevice, soundfile, numpy, scipy, pyloudnorm, pythonosc, speech_recognition, keyboard" >nul 2>&1
    if errorlevel 1 (
        echo [WARN] Some dependencies are missing or outdated.
        echo [INFO] Installing dependencies from requirements.txt...
        python -m pip install -r "%SCRIPT_DIR%requirements.txt"
        if errorlevel 1 (
            echo [ERROR] Failed to install dependencies.
            pause
            exit /b 1
        )
        echo [OK] Dependencies installed successfully.
    ) else (
        echo [OK] All dependencies are satisfied.
    )
) else (
    REM Check if all required packages are installed
    python -c "import customtkinter, edge_tts, langid, sounddevice, soundfile, numpy, scipy, pyloudnorm, pythonosc, speech_recognition, keyboard" >nul 2>&1
    if errorlevel 1 (
        echo [WARN] Some dependencies are missing or outdated.
        echo [INFO] Installing dependencies from requirements.txt...
        python -m pip install -r "%SCRIPT_DIR%requirements.txt"
        if errorlevel 1 (
            echo [ERROR] Failed to install dependencies.
            pause
            exit /b 1
        )
        echo [OK] Dependencies installed successfully.
    ) else (
        echo [OK] All dependencies are satisfied.
    )
)

REM Launch the application
echo.
echo ========================================
echo   Launching CriTTS...
echo ========================================
echo.

python "%SCRIPT_DIR%main.py"

REM If the application exits with an error, pause to show the message
if errorlevel 1 (
    echo.
    echo [ERROR] Application exited with an error.
    pause
)

endlocal