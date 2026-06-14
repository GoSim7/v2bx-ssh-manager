@echo off
setlocal
cd /d "%~dp0"
set PYTHONPATH=src
".venv\Scripts\python.exe" -m v2bx_manager.main
endlocal
