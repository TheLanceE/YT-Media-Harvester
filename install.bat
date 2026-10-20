@echo off
"%~dp0..\.venv\Scripts\python.exe" "%~dp0native_host.py" install
echo.
echo Done. Reload the extension in chrome://extensions. You no longer need start.bat.
pause
