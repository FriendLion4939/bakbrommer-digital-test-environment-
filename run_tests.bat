@echo off
rem Runs every automated test. Double-click, or run from a command prompt.
cd /d "%~dp0"
.venv\Scripts\python.exe -m pytest %*
pause
