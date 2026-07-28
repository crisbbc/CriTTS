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

REM If we already tried the python.org installer and Python is STILL not on
REM PATH, give up cleanly rather than asking the user to install again.
if defined PY_INSTALL_ATTEMPTED (
    echo.
    echo [ERROR] Python is still not on PATH even after running the installer.
    echo.
    echo To recover, try one of these manually and re-run run.bat:
    echo     - Re-run the python.org installer as Administrator, ticking
    echo       "Add python.exe to PATH" (a per-user install can be blocked by policy).
    echo     - winget install Python.Python.3.12, then restart the launcher.
    echo     - choco install python
    echo     - Manual: https://www.python.org/downloads/   (enable "Add Python to PATH")
    pause
    exit /b 1
)

REM Python not on PATH.  Before giving up, offer to install Python.
echo.
echo [WARN] Python 3 was not detected on PATH.
echo.
echo How would you like to install Python?
echo   [1] Download Python 3.12 from python.org and install (per-user, with pip, adds to PATH -- recommended)
echo   [2] Install uv first, then let uv install Python (faster, lighter, no admin)
echo   [3] Cancel -- I'll install Python myself
echo.
set "PY_INSTALL_CHOICE="
set /p PY_INSTALL_CHOICE="Enter 1, 2, or 3 (default 3): "
if "%PY_INSTALL_CHOICE%"=="1" goto :py_install_python_org
if "%PY_INSTALL_CHOICE%"=="2" goto :py_install_via_uv
echo.
echo Please install Python 3.8+ from:
echo     https://www.python.org/downloads/
echo     (or `winget install Python.Python.3.12`, or `choco install python`)
echo Then re-run run.bat.
pause
exit /b 1

:py_install_python_org
set "PY_INSTALLER=%TEMP%\critts-python-installer.exe"
REM Pick the installer that matches this CPU (Surface Pro X / Snapdragon X Elite use ARM64).
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" (
    set "PY_PKG=python-3.12.7-arm64.exe"
) else (
    set "PY_PKG=python-3.12.7-amd64.exe"
)
echo [INFO] Downloading %PY_PKG% from python.org...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; ^
     $ProgressPreference = 'SilentlyContinue'; ^
     $url = 'https://www.python.org/ftp/python/3.12.7/%PY_PKG%'; ^
     $dest = '%PY_INSTALLER%'; ^
     try { ^
         Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing; ^
         if ((Get-Item $dest -ErrorAction SilentlyContinue).Length -lt 20MB) { ^
             Write-Host '[ERROR] Download appears incomplete.'; ^
             exit 3 ^
         } ^
         Write-Host '[OK] Download complete.' ^
     } catch { ^
         Write-Host ('[ERROR] Download failed: ' + $_.Exception.Message); ^
         exit 2 ^
     }"
if errorlevel 1 goto :py_install_fail
echo [INFO] Running installer (passive mode, per-user, pip + py launcher + PATH)...
"%PY_INSTALLER%" /passive InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1 Include_test=0 Include_doc=0 Include_dev=0
if errorlevel 1 goto :py_install_fail
echo [OK] Python installer finished. Refreshing current PATH...
REM Read HKCU\Environment\PATH (per-user install writes there) and prepend.
for /f "tokens=2*" %%i in ('reg query "HKCU\Environment" /v PATH 2^>nul') do set "USER_PATH=%%j"
if defined USER_PATH set "PATH=%USER_PATH%;%PATH%"
REM Mark that an install attempt just happened so the find_python retry can
REM distinguish "first run, nothing installed" from "we just installed but it
REM still didn't work" -- prevents the install prompt from re-looping.
set "PY_INSTALL_ATTEMPTED=1"
goto :find_python

:py_install_via_uv
echo [INFO] Installing uv via official installer...
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; irm https://astral.sh/uv/install.ps1 | iex"
if errorlevel 1 goto :py_install_fail
echo [INFO] Asking uv to install Python 3.12...
"%USERPROFILE%\.local\bin\uv.exe" python install 3.12
if errorlevel 1 goto :py_install_fail
REM uv does NOT drop a python.exe shim on PATH -- resolve the absolute interpreter path.
for /f "delims=" %%i in ('"%USERPROFILE%\.local\bin\uv.exe" python find 3.12 2^>nul') do set "PY_PYTHON_FINAL=%%i"
if not defined PY_PYTHON_FINAL (
    echo [ERROR] uv python find returned no path.
    goto :py_install_fail
)
set "PYTHON_CMD=!PY_PYTHON_FINAL!"
set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"
echo [OK] Python installed via uv: !PY_PYTHON_FINAL!
goto :python_found

:py_install_fail
echo.
echo [ERROR] Python installation failed.
echo.
echo Please install Python 3.8+ manually and re-run run.bat:
echo     - python.org:  https://www.python.org/downloads/
echo     - winget:      winget install Python.Python.3.12
echo     - choco:       choco install python
pause
exit /b 1

:python_found
for /f "tokens=2" %%i in ('"!PYTHON_CMD!" --version 2^>^&1') do set "PYTHON_VERSION=%%i"
echo [OK] Python %PYTHON_VERSION% found.

REM ---------------------------------------------------------------------------
REM [2b] Auto-create virtual environment when none exists
REM
REM Microsoft Store Python and system-managed installs (PEP 668) block direct
REM package installs.  We create a venv so install_deps.py has a writable
REM site-packages.  Prefer ``uv venv`` when available (faster); fall back to
REM ``python -m venv``.
REM ---------------------------------------------------------------------------
if exist "%SCRIPT_DIR%.venv\Scripts\activate.bat" goto :skip_venv_create
if exist "%SCRIPT_DIR%venv\Scripts\activate.bat" goto :skip_venv_create

echo [INFO] No virtual environment found -- creating one...

REM Try uv first (fast, modern)
where uv >nul 2>&1
if not errorlevel 1 (
    uv venv --python "!PYTHON_CMD!" "%SCRIPT_DIR%.venv"
    if not errorlevel 1 goto :venv_created
    echo [WARN] uv venv failed, falling back to python -m venv...
    rmdir /s /q "%SCRIPT_DIR%.venv" 2>nul
)

REM Fall back to stdlib venv
"!PYTHON_CMD!" -m venv "%SCRIPT_DIR%.venv"
if errorlevel 1 (
    echo [ERROR] Could not create virtual environment with python -m venv.
    echo   Reinstall Python from python.org (includes venv) and retry.
    pause
    exit /b 1
)

:venv_created
call "%SCRIPT_DIR%.venv\Scripts\activate.bat" >nul 2>&1
if errorlevel 1 (
    echo [WARN] Virtual environment created but activation failed.
)
set "PYTHON_CMD=python"
echo [OK] Virtual environment created and activated at %SCRIPT_DIR%.venv

:skip_venv_create

REM ---------------------------------------------------------------------------
REM [3] Install dependencies -- only when requirements.txt changed
REM     No hard pip gate: install_deps.py tries pip -> pip.exe -> uv -> ensurepip
REM ---------------------------------------------------------------------------
if not exist "%SCRIPT_DIR%scripts\fingerprint.py" goto :install_deps_no_check

"!PYTHON_CMD!" "%SCRIPT_DIR%scripts\fingerprint.py" --check >nul 2>&1
if errorlevel 1 goto :install_deps_update
echo [OK] Dependencies up to date.
goto :check_updates

:install_deps_update
echo [INFO] Dependencies need updating...
"!PYTHON_CMD!" "%SCRIPT_DIR%scripts\install_deps.py"
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
"!PYTHON_CMD!" "%SCRIPT_DIR%scripts\fingerprint.py" --write >nul 2>&1
echo [OK] Dependencies updated.
goto :check_updates

:install_deps_no_check
echo [INFO] Installing dependencies (first run)...
"!PYTHON_CMD!" "%SCRIPT_DIR%scripts\install_deps.py"
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
    "!PYTHON_CMD!" "%SCRIPT_DIR%scripts\fingerprint.py" --write >nul 2>&1
)
echo [OK] Dependencies installed.

REM ---------------------------------------------------------------------------
REM [4] Background update check -- fire and forget
REM ---------------------------------------------------------------------------
:check_updates
if exist "%SCRIPT_DIR%scripts\update_check.py" (
    start /b "" "!PYTHON_CMD!" "%SCRIPT_DIR%scripts\update_check.py" >nul 2>&1
)

REM ---------------------------------------------------------------------------
REM [5] Launch
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo   Launching CriTTS...
echo ========================================
echo.

"!PYTHON_CMD!" "%SCRIPT_DIR%main.py"
set "APP_RC=!ERRORLEVEL!"
if "!APP_RC!"=="0" goto :launcher_done

echo.
echo [ERROR] Application exited with an error.
pause

:launcher_done
endlocal
