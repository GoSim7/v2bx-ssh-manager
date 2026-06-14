@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" -m PyInstaller ^
  --noconfirm ^
  --onefile ^
  --windowed ^
  --name Bananas_V2bx ^
  --paths src ^
  --distpath dist ^
  --workpath build ^
  --specpath build ^
  src\v2bx_manager\main.py
endlocal
