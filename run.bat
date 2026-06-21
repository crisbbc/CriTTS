@echo off
setlocal enabledelayedexpansion

REM ==============================================================================
REM  CriTTS Launcher for Windows
REM
REM  Fast path: skips redundant work on repeated launches.
REM  - Venv activated first
REM  - pip install only runs when requirements.txt changed
REM  - Update check is fire-and-forget, never blocks startup
REM  - Works whether repo was git-cloned or ZIP-downloaded
REM ==============================================================================

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo.
echo ========================================
echo   CriTTS Launcher
echo ========================================
echo.

REM ---------------------------------------------------------------------------
REM [1] Activate virtual environment if it exists
REM ---------------------------------------------------------------------------
if exist "%SCRIPT_DIR%venv\Scripts\activate.bat" goto :activate_venv
if exist "%SCRIPT_DIR%.venv\Scripts\activate.bat" goto :activate_dotvenv
goto :check_python

:activate_venv
call "%SCRIPT_DIR%venv\Scripts\activate.bat" >nul 2>&1
if not errorlevel 1 (
    echo [OK] Virtual environment ready.
) else (
    echo [WARN] Virtual environment exists but activation failed.
)
goto :check_python

:activate_dotvenv
call "%SCRIPT_DIR%.venv\Scripts\activate.bat" >nul 2>&1
if not errorlevel 1 (
    echo [OK] Virtual environment ready.
) else (
    echo [WARN] .venv exists but activation failed.
)

REM ---------------------------------------------------------------------------
REM [2] Check Python
REM ---------------------------------------------------------------------------
:check_python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo.
    echo Please install Python 3.9+ from:
    echo     https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set "PYTHON_VERSION=%%i"
echo [OK] Python %PYTHON_VERSION% found.

REM ---------------------------------------------------------------------------
REM [3] Install dependencies -- only when requirements.txt changed
REM ---------------------------------------------------------------------------
if not exist "%SCRIPT_DIR%scripts\fingerprint.py" goto :install_deps_no_check

python "%SCRIPT_DIR%scripts\fingerprint.py" --check >nul 2>&1
if errorlevel 1 goto :install_deps_update
echo [OK] Dependencies up to date.
goto :check_updates

:install_deps_update
echo [INFO] Dependencies need updating...
python "%SCRIPT_DIR%scripts\install_deps.py"
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    echo.
    echo   Tried pip, uv, and ensurepip. To resolve:
    echo     - Install uv:  https://docs.astral.sh/uv/
    echo     - Or recreate the venv with pip:  python -m venv --clear .venv
    pause
    exit /b 1
)
python "%SCRIPT_DIR%scripts\fingerprint.py" --write >nul 2>&1
echo [OK] Dependencies updated.
goto :check_updates

:install_deps_no_check
echo [INFO] Installing dependencies ^(first run^)...
python "%SCRIPT_DIR%scripts\install_deps.py"
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    echo.
    echo   Tried pip, uv, and ensurepip. To resolve:
    echo     - Install uv:  https://docs.astral.sh/uv/
    echo     - Or recreate the venv with pip:  python -m venv --clear .venv
    pause
    exit /b 1
)
if exist "%SCRIPT_DIR%scripts\fingerprint.py" (
    python "%SCRIPT_DIR%scripts\fingerprint.py" --write >nul 2>&1
)
echo [OK] Dependencies installed.

REM ---------------------------------------------------------------------------
REM [4] Background update check -- fire and forget
REM ---------------------------------------------------------------------------
:check_updates
if exist "%SCRIPT_DIR%scripts\update_check.py" (
    start /b python "%SCRIPT_DIR%scripts\update_check.py" >nul 2>&1
)

REM ---------------------------------------------------------------------------
REM [5] Launch
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo   Launching CriTTS...
echo ========================================
echo.

python "%SCRIPT_DIR%main.py"
if errorlevel 1 (
    echo.
    echo [ERROR] Application exited with an error.
    pause
)

endlocal
