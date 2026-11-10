@echo off
REM AI Reference Retriever - portable launcher (Windows)
REM Needs Python 3.11+ from python.org installed with "Add python.exe to PATH".
cd /d %~dp0
REM Warm starts skip straight to the GUI. Delete .deps_ok to force a re-check.
if not exist .deps_ok goto :setup
goto :launch
:setup
py -3 -c "import requests, PIL.Image, reportlab" 2>nul
if errorlevel 1 (
  echo Installing libraries - first run only...
  py -3 -m pip install requests pillow reportlab
)
py -3 -c "import requests, PIL.Image, reportlab" 2>nul
if errorlevel 1 (
  echo.
  echo [!] Could not install libraries. Install Python from https://www.python.org/downloads/
  echo     and tick "Add python.exe to PATH", then double-click run.bat again.
  pause
  exit /b 1
)
echo ok> .deps_ok
:launch
REM start the GUI detached with no lingering terminal;
REM the app itself keeps exactly one copy running.
start "" pyw -3 app.py
exit
