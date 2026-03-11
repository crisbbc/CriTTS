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

REM Check for Git and Auto-Update
echo [1/4] Checking for Git and updating scripts...
git --version >nul 2>&1
if errorlevel 1 (
    echo [WARN] Git is not installed. Attempting to install Git...
    winget --version >nul 2>&1
    if errorlevel 1 (
        echo [WARN] winget is not available. Could not install Git automatically.
    ) else (
        winget install --id Git.Git -e --source winget
        if errorlevel 1 (
            echo [WARN] Failed to install Git automatically.
        ) else (
            REM Need to reload PATH or assume git is now available (might require restart)
            echo [INFO] Git installed. Note: You may need to restart the script/terminal for Git to be recognized.
        )
    )
)

git --version >nul 2>&1
if errorlevel 0 (
    echo [INFO] Checking for updates from remote repository...
    REM Ensure we are tracking a remote branch
    git fetch origin main >nul 2>&1
    if errorlevel 0 (
        for /f "tokens=*" %%i in ('git rev-parse HEAD 2^>nul') do set LOCAL=%%i
        for /f "tokens=*" %%i in ('git rev-parse origin/main 2^>nul') do set REMOTE=%%i

        if not "!LOCAL!"=="!REMOTE!" (
            echo [INFO] Updates found. Applying updates and replacing local changes...
            git reset --hard origin/main >nul 2>&1
            if errorlevel 0 (
                echo [OK] Successfully updated to the latest main branch.
                REM Re-run the script to ensure we are using the updated version
                call "%~f0" %*
                exit /b
            ) else (
                echo [WARN] Failed to apply updates.
            )
        ) else (
            echo [OK] Scripts are up to date.
        )
    ) else (
        echo [WARN] Failed to fetch updates from remote repository.
    )
) else (
    echo [WARN] Git could not be found or installed. Skipping update check.
)

REM Check if Python is installed
echo.
echo [2/4] Checking Python installation...
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
echo [3/4] Checking pip...
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
echo [4/4] Checking dependencies...

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