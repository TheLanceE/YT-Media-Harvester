@echo off
setlocal
rem Uses .venv in this folder, or ..\.venv from the older setup. Creates .venv here if neither exists.
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%~dp0..\.venv\Scripts\python.exe"
if exist "%PY%" goto :have_venv
set "PY=%~dp0.venv\Scripts\python.exe"
echo No virtual environment found. Creating .venv in this folder...
py -3 -m venv "%~dp0.venv" 2>nul || python -m venv "%~dp0.venv"
if not exist "%PY%" (
  echo.
  echo ERROR: Python 3.10 or newer was not found. Install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH", then run install.bat again.
  goto :fail
)

:have_venv
"%PY%" -c "import sys; sys.exit(sys.version_info < (3, 10))"
if errorlevel 1 (
  echo ERROR: the .venv Python is older than 3.10. Delete that .venv folder and run install.bat again.
  goto :fail
)
echo Installing or updating Python packages (yt-dlp)...
"%PY%" -m pip install --disable-pip-version-check -q -U -r "%~dp0requirements.txt"
if errorlevel 1 (
  echo ERROR: pip could not install requirements.txt. See the messages above.
  goto :fail
)
"%PY%" "%~dp0native_host.py" install
if errorlevel 1 goto :fail
echo.
echo Done. Reload the extension in chrome://extensions.
pause
exit /b 0

:fail
echo.
echo Install did not finish.
pause
exit /b 1
