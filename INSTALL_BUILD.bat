@echo off
setlocal
cd /d "%~dp0web"
echo ================================================
echo TradePilot - Safe M1 Fusion Build
 echo ================================================
if not exist package.json (
  echo ERROR: web\package.json not found.
  pause
  exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
  echo ERROR: Node.js / npm is not installed or not in PATH.
  pause
  exit /b 1
)
echo Installing dependencies...
npm install
if errorlevel 1 (
  echo ERROR: npm install failed.
  pause
  exit /b 1
)
echo Building production app...
npm run build
if errorlevel 1 (
  echo ERROR: npm run build failed.
  pause
  exit /b 1
)
echo.
echo BUILD COMPLETE.
echo Production files are in web\dist
pause
