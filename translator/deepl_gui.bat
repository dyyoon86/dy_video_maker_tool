@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM ---- Check Python ----
where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python is not installed or not in PATH.
  echo Please install Python 3.10+ from:
  echo   https://www.python.org/downloads/
  echo Make sure to check "Add Python to PATH" during installation.
  pause
  exit /b 1
)

REM ---- Check dependencies (silent import test) ----
python -c "import deepl, srt, tqdm, PyQt6" >nul 2>&1
if errorlevel 1 (
  echo ============================================================
  echo  First-time setup: installing required Python packages
  echo  - deepl, srt, tqdm, PyQt6
  echo  This may take 1-3 minutes. Please wait...
  echo ============================================================
  python -m pip install --upgrade pip --quiet --disable-pip-version-check
  python -m pip install --quiet --disable-pip-version-check deepl srt tqdm PyQt6
  if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install dependencies.
    echo Try running this command manually in a terminal:
    echo   pip install deepl srt tqdm PyQt6
    pause
    exit /b 1
  )
  echo Setup complete. Launching GUI...
  echo.
)

REM ---- Launch GUI (no console window) ----
start "" pythonw deepl_gui.py
exit /b 0
