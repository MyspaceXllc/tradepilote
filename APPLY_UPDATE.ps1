$ErrorActionPreference = "Stop"
$Update = Split-Path -Parent $MyInvocation.MyCommand.Path
$Target = Read-Host "Enter your TradePilot installation folder path"
if (!(Test-Path (Join-Path $Target "connector\connector.py"))) { throw "TradePilot folder not found" }
Get-ChildItem $Update -Recurse -File | Where-Object { $_.Name -ne "APPLY_UPDATE.ps1" } | ForEach-Object {
  $Relative = $_.FullName.Substring($Update.Length).TrimStart('\')
  $Destination = Join-Path $Target $Relative
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
  Copy-Item $_.FullName $Destination -Force
}
Write-Host "TradePilot Smart Market Calculator v2.9.2 Flow Chart update applied." -ForegroundColor Green
