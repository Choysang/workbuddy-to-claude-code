@echo off
chcp 65001 >nul
python "%~dp0scripts\harness.py" build %*
if errorlevel 1 (
  echo Build failed. See the error above and README.md.
  pause
  exit /b 1
)
pause
