@echo off
REM NOOBRA - one-click Windows setup.
REM
REM Double-click this file (or run it in a terminal) once after cloning.
REM It checks Python, creates .venv, installs the core packages first,
REM then installs the optional browser / voice packages separately so a
REM single heavy failure cannot leave you with a broken app.
REM
REM Re-running it is safe: it reuses .venv, keeps your .env and only
REM re-installs packages.

setlocal
cd /d "%~dp0"

echo ============================================
echo  NOOBRA setup
echo ============================================
echo  Folder: %CD%
echo.

REM --- 1. Python present? -------------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo [X] "python" is not on your PATH.
    echo     Install Python 3.11 or 3.12 from
    echo       https://www.python.org/downloads/
    echo     and TICK "Add python.exe to PATH" during setup, then re-run this file.
    goto end_fail
)

REM --- 2. Supported Python version? --------------------------------------
REM PySide6 and the voice packages do not have wheels for 3.14+ yet, so a
REM newer interpreter would make the install fail halfway through.
python -c "import sys; v=sys.version_info[:2]; sys.exit(0 if (3,10) <= v <= (3,13) else 1)"
if errorlevel 1 (
    echo [X] Unsupported Python version:
    python -V
    echo     NOOBRA needs Python 3.10 - 3.13.
    echo     Install 3.12, then run this file again.
    goto end_fail
)
echo [ok] Python:
python -V
echo.

REM --- 3. Virtual environment -------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo [1/6] Creating virtual environment in .venv ...
    python -m venv .venv
    if errorlevel 1 goto end_fail
) else (
    echo [1/6] Reusing the existing .venv
)
set "PY=.venv\Scripts\python.exe"

echo [2/6] Updating pip ...
"%PY%" -m pip install --upgrade pip --quiet

REM --- 4. Core packages (the app cannot start without these) -------------
echo [3/6] Installing core packages: PySide6, python-dotenv, requests ...
"%PY%" -m pip install "PySide6>=6.7" "python-dotenv>=1.0" "requests>=2.32"
if errorlevel 1 (
    echo [X] Core install failed. Scroll up: usually no internet, a proxy,
    echo     or a Python version outside 3.10 - 3.13.
    goto end_fail
)

REM --- 5. Optional: desktop automation -----------------------------------
echo [4/6] Installing desktop helpers: pyautogui, send2trash ...
"%PY%" -m pip install "pyautogui>=0.9.54" "send2trash>=1.8"
if errorlevel 1 echo     [warn] Desktop helpers failed to install - the app still runs,
if errorlevel 1 echo            but mouse/keyboard tools and Recycle Bin deletes are limited.

REM --- 6. Optional: browser automation -----------------------------------
echo [5/6] Installing Playwright and the Chromium it needs ...
"%PY%" -m pip install "playwright>=1.44"
if errorlevel 1 (
    echo     [warn] Playwright failed to install - web/YouTube search tools will be disabled.
) else (
    "%PY%" -m playwright install chromium
    if errorlevel 1 echo     [warn] Chromium download failed - run "python -m playwright install chromium" later.
)

REM --- 7. Optional: voice (large; never fatal) ---------------------------
echo [6/6] Installing optional voice packages (this downloads a lot) ...
"%PY%" -m pip install "faster-whisper>=1.0" "edge-tts>=6.1" "sounddevice>=0.4"
if errorlevel 1 echo     [warn] Voice skipped - typing works fine without it.

REM --- 8. .env ----------------------------------------------------------
echo.
if not exist ".env" (
    copy /y ".env.example" ".env" >nul
    echo [ok] Created .env from .env.example
    echo      Open .env in Notepad and paste a free API key
    echo      (Gemini: https://aistudio.google.com/app/apikey).
) else (
    echo [ok] Kept your existing .env
)

REM --- 9. Smoke test ----------------------------------------------------
echo.
echo Verifying the install ...
"%PY%" -c "import sys; sys.path.insert(0,'.'); from core.agent import NoobraAgent; NoobraAgent(); print('  [ok] NOOBRA core loads')"
if errorlevel 1 (
    echo [X] The app does not import correctly. Copy the error above when asking for help.
    goto end_fail
)

echo.
echo ============================================
echo  Setup complete.
echo ============================================
echo  Start the app:   run.bat
echo  Or:              .venv\Scripts\python main.py
echo  Auto-updates:    powershell -ExecutionPolicy Bypass -File .\scripts\setup-auto-update.ps1
echo.
pause
exit /b 0

:end_fail
echo.
echo ============================================
echo  Setup did NOT finish.
echo ============================================
echo  Fix the message above, then run setup.bat again.
echo.
pause
exit /b 1
