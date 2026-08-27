@echo off
setlocal enabledelayedexpansion

REM CriTTS Launcher for Windows — slim wrapper around `uv run`
REM uv path:  uv run python main.py  (auto-creates .venv, syncs uv.lock)
REM fallback: python + .venv + pip (for hosts without uv)

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo.
echo ========================================
echo   CriTTS Launcher
echo ========================================
echo.

where uv >nul 2>&1
if not errorlevel 1 (
  if exist "%SCRIPT_DIR%scripts\update_check.py" start /b "" uv run python "%SCRIPT_DIR%scripts\update_check.py" >nul 2>&1
  uv run python "%SCRIPT_DIR%main.py"
  exit /b !ERRORLEVEL!
)

REM --- fallback: find python ---
set "PYTHON_CMD="
python --version >nul 2>&1 && set "PYTHON_CMD=python"
if not defined PYTHON_CMD py -3 --version >nul 2>&1 && set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD (
  echo [ERROR] Python 3.10+ not found. Install from https://www.python.org/downloads/ or https://docs.astral.sh/uv/
  pause
  exit /b 1
)

if not exist "%SCRIPT_DIR%.venv\Scripts\activate.bat" if not exist "%SCRIPT_DIR%venv\Scripts\activate.bat" (
  echo [INFO] Creating .venv...
  "!PYTHON_CMD!" -m venv "%SCRIPT_DIR%.venv"
  if errorlevel 1 (
    echo [ERROR] python -m venv failed. Reinstall Python with venv support.
    pause
    exit /b 1
  )
)
if exist "%SCRIPT_DIR%.venv\Scripts\activate.bat" (
  call "%SCRIPT_DIR%.venv\Scripts\activate.bat" >nul 2>&1
) else (
  call "%SCRIPT_DIR%venv\Scripts\activate.bat" >nul 2>&1
)
set "PYTHON_CMD=python"

REM install deps only when needed
"!PYTHON_CMD!" -c "import customtkinter" >nul 2>&1
if errorlevel 1 goto :install_deps
"!PYTHON_CMD!" "%SCRIPT_DIR%scripts\fingerprint.py" --check >nul 2>&1
if not errorlevel 1 goto :deps_ok
:install_deps
echo [INFO] Installing dependencies...
"!PYTHON_CMD!" "%SCRIPT_DIR%scripts\install_deps.py"
if errorlevel 1 pause & exit /b 1
"!PYTHON_CMD!" "%SCRIPT_DIR%scripts\fingerprint.py" --write >nul 2>&1
:deps_ok
echo [OK] Dependencies up to date.

if exist "%SCRIPT_DIR%scripts\update_check.py" start /b "" "!PYTHON_CMD!" "%SCRIPT_DIR%scripts\update_check.py" >nul 2>&1

"!PYTHON_CMD!" "%SCRIPT_DIR%main.py"
exit /b !ERRORLEVEL!
