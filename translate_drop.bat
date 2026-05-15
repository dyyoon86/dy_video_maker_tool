@echo off
REM Drag an .srt file onto this .bat to translate it via DeepL (ja -> ko).
chcp 65001 >nul
cd /d "%~dp0"

if "%~1"=="" (
  echo Drag an SRT file onto this batch file to translate.
  pause
  exit /b 1
)

REM ---- Check Python ----
where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python is not installed or not in PATH.
  echo Install Python 3.10+ from https://www.python.org/downloads/
  pause
  exit /b 1
)

REM ---- Check dependencies (silent import test) ----
python -c "import deepl, srt, tqdm" >nul 2>&1
if errorlevel 1 (
  echo ============================================================
  echo  First-time setup: installing required Python packages
  echo  - deepl, srt, tqdm
  echo  This may take 1-2 minutes. Please wait...
  echo ============================================================
  python -m pip install --upgrade pip --quiet --disable-pip-version-check
  python -m pip install --quiet --disable-pip-version-check deepl srt tqdm
  if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install dependencies.
    echo Try running this command manually:
    echo   pip install deepl srt tqdm
    pause
    exit /b 1
  )
  echo Setup complete.
  echo.
)

REM ---- Run translator ----
python "%~dp0deepl_translate_srt.py" "%~1"

echo.
pause
