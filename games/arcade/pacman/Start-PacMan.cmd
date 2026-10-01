@echo off
set "ROOT=%~dp0..\..\..\"
cd /d "%ROOT%"
"%ROOT%.venv\Scripts\python.exe" "%ROOT%tools\cabinet_test.py" pacman %*
pause
