@echo off
REM NOOBRA launcher - runs the app with this folder's .venv.
REM
REM   run.bat              -> GUI (falls back to CLI if PySide6 is missing)
REM   run.bat --cli        -> terminal mode
REM   run.bat --text "..."  -> one instruction, then exit

setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo NOOBRA is not set up yet - run setup.bat first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" main.py %*
if errorlevel 1 (
    echo.
    echo NOOBRA exited with an error. Run setup.bat again if this is a fresh clone.
    pause
)
exit /b 0
