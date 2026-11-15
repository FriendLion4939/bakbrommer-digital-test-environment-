@echo off
rem One-click start for Windows. Double-click this file.
rem First run: creates a private Python environment in .venv and installs the
rem program (needs internet once). Later runs start immediately.
cd /d "%~dp0"

set PYTHON=
where py >nul 2>nul && set PYTHON=py -3
if "%PYTHON%"=="" where python >nul 2>nul && set PYTHON=python
if "%PYTHON%"=="" (
    echo Python 3.12 or newer is required.
    echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
    pause
    exit /b 1
)
%PYTHON% -c "import sys; sys.exit(sys.version_info < (3, 12))"
if errorlevel 1 (
    echo Python 3.12 or newer is required. Install it from https://www.python.org/downloads/
    pause
    exit /b 1
)

if not exist .venv\Scripts\python.exe (
    echo First start: installing, this takes a few minutes...
    %PYTHON% -m venv .venv
    .venv\Scripts\python.exe -m pip install --quiet --upgrade pip
    .venv\Scripts\python.exe -m pip install --quiet -e ".[dev]"
    if errorlevel 1 (
        echo Installation failed. Check your internet connection and try again.
        pause
        exit /b 1
    )
)

echo Starting Bakbrommer Twin. Open http://localhost:8501 in your browser.
echo Close this window to stop.
.venv\Scripts\python.exe -m bakbrommer_twin.cli ui %*
pause
