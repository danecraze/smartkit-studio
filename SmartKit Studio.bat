@echo off
rem Double-click to start SmartKit Studio. The first start installs the Python add-ons it needs.
cd /d "%~dp0"
python -c "import numpy, pedalboard" 2>nul || (echo Installing add-ons, please wait... & python -m pip install --user numpy pedalboard)
start "" pythonw smartkit_app.py
