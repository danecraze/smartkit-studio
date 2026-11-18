@echo off
rem Double-click once: installs the add-ons SmartKit needs and puts a SmartKit Studio icon on the Desktop and in the Start menu.
title Install SmartKit Studio
cd /d "%~dp0"
echo Installing add-ons (numpy, pedalboard, dawdreamer) ...
python -m pip install --user numpy pedalboard dawdreamer
if errorlevel 1 (echo. & echo Python or pip was not found. Install Python 3 from python.org, tick "Add python.exe to PATH", then run this again. & pause & exit /b 1)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0extras\make_shortcut.ps1"
echo.
echo Done. Start SmartKit Studio from the icon on your Desktop or from the Start menu.
pause
