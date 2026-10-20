@echo off
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%~dp0..\.venv\Scripts\python.exe"
"%PY%" "%~dp0native_host.py" uninstall
pause
