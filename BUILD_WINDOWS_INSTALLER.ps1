$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "`n=== TradePilot Windows Installer Builder ===" -ForegroundColor Cyan

if (!(Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python 3.12 x64 is required."
}
if (!(Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw "Node.js and npm are required."
}

Write-Host "`n[1/5] Building the same-origin PWA..." -ForegroundColor Yellow
Push-Location web
$env:VITE_API_URL = "__SAME_ORIGIN__"
Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
npm.cmd install
npm.cmd approve-scripts esbuild
npm.cmd rebuild esbuild
npm.cmd run build
if (!(Test-Path "dist\analysis.html")) {
    throw "Market Lab was not copied into web\dist."
}
if (!(Test-Path "dist\premium.html")) {
    throw "Flow Pulse was not copied into web\dist."
}
if (!(Test-Path "dist\fusion.html")) {
    throw "Signal Fusion was not copied into web\dist."
}
if (!(Test-Path "dist\favicon.ico")) {
    throw "The TradePilot Market Lab icon is missing from web\dist."
}
$AnalysisHtml = Get-Content "dist\analysis.html" -Raw
if (
    $AnalysisHtml.Contains("positionOverlay") -or
    !$AnalysisHtml.Contains("marketStats") -or
    !$AnalysisHtml.Contains("/local/market-lab/positions") -or
    !$AnalysisHtml.Contains("MARKET LAB 2.9.2")
) {
    throw "The built Market Lab is stale. Delete web\dist and build again."
}
$PremiumHtml = Get-Content "dist\premium.html" -Raw
if (
    !$PremiumHtml.Contains("FLOW CHART") -or
    !$PremiumHtml.Contains("/local/premium-strategy/analyze") -or
    !$PremiumHtml.Contains("FUTURE MOVEMENT") -or
    !$PremiumHtml.Contains('id="language"') -or
    !($PremiumHtml -match "FAST[^<]{0,20}M5[^<]{0,20}M15") -or
    $PremiumHtml.Contains("alternative_points")
) {
    throw "The built Flow Pulse page is stale or incomplete."
}
$FusionHtml = Get-Content "dist\fusion.html" -Raw
if (
    !$FusionHtml.Contains("SIGNAL FUSION") -or
    !$FusionHtml.Contains("/local/signal-fusion/data") -or
    !$FusionHtml.Contains("CANDLE PRESSURE") -or
    !$FusionHtml.Contains("TRADE TIMELINE") -or
    !$FusionHtml.Contains("minimum_separation")
) {
    throw "The built Signal Fusion page is stale or incomplete."
}
$AppBundle = (
    Get-ChildItem "dist\assets\*.js" |
    ForEach-Object { Get-Content $_.FullName -Raw }
) -join ""
if (
    !$AppBundle.Contains("mobilePerformance") -or
    !$AppBundle.Contains("SHARK_BUY") -or
    !$AppBundle.Contains("SHARK_BOTH") -or
    !$AppBundle.Contains("sharkPanel") -or
    !$AppBundle.Contains("controlPanel") -or
    !$AppBundle.Contains("sharkLevelPicker") -or
    !$AppBundle.Contains("sharkSettings")
) {
    throw "The built mobile performance or Shark controls are missing."
}
Pop-Location

Write-Host "`n[2/5] Preparing Python build environment..." -ForegroundColor Yellow
if (!(Test-Path ".build-venv")) {
    python -m venv .build-venv
}
$Python = Join-Path $Root ".build-venv\Scripts\python.exe"
& $Python -m pip install --upgrade pip
& $Python -m pip install -r server\requirements.txt
& $Python -m pip install -r connector\requirements.txt
& $Python -m pip install -r windows_app\build-requirements.txt

Write-Host "`n[3/5] Creating TradePilotConnector.exe..." -ForegroundColor Yellow
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
& $Python -m PyInstaller --noconfirm --clean windows_app\TradePilotConnector.spec

Write-Host "`n[4/5] Locating Inno Setup..." -ForegroundColor Yellow
$IsccCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
$Iscc = $IsccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (!$Iscc) {
    if (!(Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Install Inno Setup 6, then run this builder again."
    }
    winget install --id JRSoftware.InnoSetup -e --accept-source-agreements --accept-package-agreements
    $Iscc = $IsccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (!$Iscc) {
    throw "Inno Setup was installed but ISCC.exe was not found. Restart PowerShell and run again."
}

Write-Host "`n[5/5] Creating TradePilotSetup.exe..." -ForegroundColor Yellow
Remove-Item -Recurse -Force release -ErrorAction SilentlyContinue
& $Iscc windows_app\installer.iss

$Installer = Join-Path $Root "release\TradePilotSetup.exe"
if (!(Test-Path $Installer)) {
    throw "Installer build did not produce $Installer"
}

Write-Host "`nSUCCESS" -ForegroundColor Green
Write-Host "Installer: $Installer" -ForegroundColor Green
Write-Host "This development installer is unsigned; Windows SmartScreen may show a warning." -ForegroundColor DarkYellow
Start-Process explorer.exe "/select,`"$Installer`""