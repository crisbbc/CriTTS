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
            echo [INFO] Git installed. Note: You may need to restart the script/terminal for Git to be recognized.
        )
    )
)

git --version >nul 2>&1
if not errorlevel 1 (
    echo [INFO] Checking for updates from remote repository...

    REM Detect the current branch
    set "CURRENT_BRANCH=main"
    for /f "tokens=*" %%i in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set CURRENT_BRANCH=%%i

    REM Try to use the upstream tracking branch; fall back to current branch
    set "REMOTE_BRANCH=!CURRENT_BRANCH!"
    for /f "tokens=*" %%i in ('git rev-parse --abbrev-ref --symbolic-full-name @{u} 2^>nul') do (
        set "TRACKING=%%i"
        set "REMOTE_BRANCH=!TRACKING:origin/=!"
    )

    git fetch origin "!REMOTE_BRANCH!" >nul 2>&1
    if not errorlevel 1 (
        for /f "tokens=*" %%i in ('git rev-parse HEAD 2^>nul') do set LOCAL=%%i
        for /f "tokens=*" %%i in ('git rev-parse "origin/!REMOTE_BRANCH!" 2^>nul') do set REMOTE=%%i

        if defined LOCAL if defined REMOTE (
            if not "!LOCAL!"=="!REMOTE!" (
                echo [INFO] Updates found. Applying updates and replacing local changes...
                git reset --hard "origin/!REMOTE_BRANCH!" >nul 2>&1
                if not errorlevel 1 (
                    echo [OK] Successfully updated to the latest !REMOTE_BRANCH! branch.
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
            echo [WARN] Could not determine local or remote commit. Skipping update.
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

REM Install / update dependencies from requirements.txt
echo.
echo [4/4] Checking and installing dependencies...

REM Activate virtual environment if it exists
if exist "%SCRIPT_DIR%venv\Scripts\activate.bat" (
    echo [INFO] Virtual environment found. Activating...
    call "%SCRIPT_DIR%venv\Scripts\activate.bat"
)

python -m pip install -r "%SCRIPT_DIR%requirements.txt" --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo [OK] Dependencies are satisfied.

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