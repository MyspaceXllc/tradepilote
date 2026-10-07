@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0BUILD_WINDOWS_INSTALLER.ps1"
if errorlevel 1 (
  echo.
  echo Build failed. Review the error above.
  pause
)