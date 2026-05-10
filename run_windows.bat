@echo off
setlocal

cd /d "%~dp0"

set "APP_NAME=tunnelgram"
set "VENV_DIR=.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "VENV_PYW=%VENV_DIR%\Scripts\pythonw.exe"

echo Starting %APP_NAME%...

REM If virtual environment already exists, use it immediately.
if exist "%VENV_PY%" (
    goto run_app
)

REM Find Python only when .venv does not exist yet.
set "PYTHON_CMD="

where py >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
    goto create_venv
)

where python >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    goto create_venv
)

where python3 >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=python3"
    goto create_venv
)

echo.
echo ERROR: Python was not found.
echo Install Python 3.10+ and make sure "Add Python to PATH" is enabled.
echo.
echo If you already have Python installed, try opening a new terminal and run:
echo   python --version
echo   py -3 --version
goto error

:create_venv
echo Creating virtual environment...
%PYTHON_CMD% -m venv "%VENV_DIR%"
if errorlevel 1 goto error

echo Installing dependencies...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 goto error

"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 goto error

:run_app
echo Checking app files...

"%VENV_PY%" -m py_compile tunnelgram\gui.py
if errorlevel 1 goto error

"%VENV_PY%" -m py_compile tunnelgram\local_proxy.py
if errorlevel 1 goto error

"%VENV_PY%" -m py_compile tunnelgram\diagnostics.py
if errorlevel 1 goto error

echo Launching %APP_NAME%...

if exist "%VENV_PYW%" (
    start "" "%VENV_PYW%" -m tunnelgram.gui
) else (
    start "" "%VENV_PY%" -m tunnelgram.gui
)

if errorlevel 1 goto error

exit /b 0

:error
echo.
echo ============================================================
echo %APP_NAME% failed to start.
echo.
echo The console will stay open so you can copy the error above.
echo ============================================================
echo.
pause
exit /b 1