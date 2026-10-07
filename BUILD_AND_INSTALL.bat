@echo off
setlocal
cd /d "%~dp0web"
echo ==========================================
echo TradePilot - Line 4 Inverse Build
 echo ==========================================
echo.
if not exist package.json (
  echo ERROR: package.json not found.
  pause
  exit /b 1
)

echo [1/2] Installing/updating dependencies...
call npm install
if errorlevel 1 (
  echo.
  echo npm install failed.
  pause
  exit /b 1
)

echo.
echo [2/2] Building production files...
call npm run build
if errorlevel 1 (
  echo.
  echo Build failed.
  pause
  exit /b 1
)

echo.
echo ==========================================
echo BUILD COMPLETE
 echo ==========================================
echo Production files are in web\dist
pause
endlocal
