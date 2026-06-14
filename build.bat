@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" -m PyInstaller ^
  --noconfirm ^
  --onefile ^
  --windowed ^
  --name V2bX-SSH-Manager ^
  --paths src ^
  --distpath dist ^
  --workpath build ^
  --specpath build ^
  src\v2bx_manager\main.py
endlocal
