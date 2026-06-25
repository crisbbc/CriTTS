@echo off
setlocal enabledelayedexpansion

REM ==============================================================================
REM  CriTTS Launcher for Windows
REM
REM  Robust to:
REM  - Microsoft Store Python (pip.exe alias without pip module)
REM  - pip-less venvs (uv venv without --seed)
REM  - PATH pollution (another app's python.exe first on PATH)
REM
REM  Fast path: skips redundant work on repeated launches.
REM  - Venv activated first
REM  - pip install only runs when requirements.txt changed (fingerprint)
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
goto :find_python

:activate_venv
call "%SCRIPT_DIR%venv\Scripts\activate.bat" >nul 2>&1
if not errorlevel 1 (
    echo [OK] Virtual environment ready.
) else (
    echo [WARN] Virtual environment exists but activation failed.
)
goto :find_python

:activate_dotvenv
call "%SCRIPT_DIR%.venv\Scripts\activate.bat" >nul 2>&1
if not errorlevel 1 (
    echo [OK] Virtual environment ready.
) else (
    echo [WARN] .venv exists but activation failed.
)

REM ---------------------------------------------------------------------------
REM [2] Find a working Python interpreter
REM     Try `python` first; if it fails, try `py -3` (python.org launcher).
REM     We do NOT require pip here -- install_deps.py handles pip-less envs.
REM ---------------------------------------------------------------------------
:find_python
python --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    goto :python_found
)

echo [INFO] `python` not found on PATH. Trying `py -3` launcher...
py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
    goto :python_found
)

echo [ERROR] Python is not installed or not in PATH.
echo.
echo Please install Python 3.8+ from:
echo     https://www.python.org/downloads/
echo     (or search "Python" in the Microsoft Store)
echo.
pause
exit /b 1

:python_found
for /f "tokens=2" %%i in ('!PYTHON_CMD! --version 2^>^&1') do set "PYTHON_VERSION=%%i"
echo [OK] Python %PYTHON_VERSION% found.

REM ---------------------------------------------------------------------------
REM [3] Install dependencies -- only when requirements.txt changed
REM     No hard pip gate: install_deps.py tries pip -> pip.exe -> uv -> ensurepip
REM ---------------------------------------------------------------------------
if not exist "%SCRIPT_DIR%scripts\fingerprint.py" goto :install_deps_no_check

!PYTHON_CMD! "%SCRIPT_DIR%scripts\fingerprint.py" --check >nul 2>&1
if errorlevel 1 goto :install_deps_update
echo [OK] Dependencies up to date.
goto :check_updates

:install_deps_update
echo [INFO] Dependencies need updating...
!PYTHON_CMD! "%SCRIPT_DIR%scripts\install_deps.py"
set "INSTALL_RC=!ERRORLEVEL!"
if "!INSTALL_RC!"=="0" goto :deps_updated

echo [ERROR] Failed to install dependencies.
echo.
echo   Tried pip, pip.exe, uv, and ensurepip. To resolve:
echo     - Install uv:  https://docs.astral.sh/uv/
echo     - Or reinstall Python from python.org (includes pip)
echo     - Or recreate the venv with pip:  python -m venv --clear .venv
pause
exit /b 1

:deps_updated
!PYTHON_CMD! "%SCRIPT_DIR%scripts\fingerprint.py" --write >nul 2>&1
echo [OK] Dependencies updated.
goto :check_updates

:install_deps_no_check
echo [INFO] Installing dependencies (first run)...
!PYTHON_CMD! "%SCRIPT_DIR%scripts\install_deps.py"
set "INSTALL_RC=!ERRORLEVEL!"
if "!INSTALL_RC!"=="0" goto :deps_installed

echo [ERROR] Failed to install dependencies.
echo.
echo   Tried pip, pip.exe, uv, and ensurepip. To resolve:
echo     - Install uv:  https://docs.astral.sh/uv/
echo     - Or reinstall Python from python.org (includes pip)
echo     - Or recreate the venv with pip:  python -m venv --clear .venv
pause
exit /b 1

:deps_installed
if exist "%SCRIPT_DIR%scripts\fingerprint.py" (
    !PYTHON_CMD! "%SCRIPT_DIR%scripts\fingerprint.py" --write >nul 2>&1
)
echo [OK] Dependencies installed.

REM ---------------------------------------------------------------------------
REM [4] Background update check -- fire and forget
REM ---------------------------------------------------------------------------
:check_updates
if exist "%SCRIPT_DIR%scripts\update_check.py" (
    start /b !PYTHON_CMD! "%SCRIPT_DIR%scripts\update_check.py" >nul 2>&1
)

REM ---------------------------------------------------------------------------
REM [5] Launch
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo   Launching CriTTS...
echo ========================================
echo.

!PYTHON_CMD! "%SCRIPT_DIR%main.py"
set "APP_RC=!ERRORLEVEL!"
if "!APP_RC!"=="0" goto :launcher_done

echo.
echo [ERROR] Application exited with an error.
pause

:launcher_done
endlocal
