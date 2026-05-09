@echo off
setlocal EnableExtensions

chcp 65001 >nul
cd /d "%~dp0"

title tunnelgram

echo ==================================================
echo   tunnelgram - setup and run
echo ==================================================
echo.

set "PYTHON_CMD="

where python >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON_CMD=python"
    goto :python_found
)

where python3 >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON_CMD=python3"
    goto :python_found
)

echo Python was not found.
echo Trying to install Python 3.12 via winget...
echo.

where winget >nul 2>nul
if not %errorlevel%==0 (
    echo winget was not found.
    echo Please install Python manually from https://www.python.org/downloads/
    echo During installation enable: Add python.exe to PATH
    pause
    exit /b 1
)

winget install -e --id Python.Python.3.12

echo.
echo Python installation finished.
echo Close this window, open run_windows.bat again.
pause
exit /b 0

:python_found
echo Found Python:
%PYTHON_CMD% --version
echo.

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PYTHON_CMD% -m venv .venv

    if not exist ".venv\Scripts\python.exe" (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip

echo.
echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt

echo.
echo Starting tunnelgram...
start "" ".venv\Scripts\pythonw.exe" -m tunnelgram.gui
exit /b 0