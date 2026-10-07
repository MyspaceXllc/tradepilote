# TradePilot Windows Installer Prototype

## What it does

The installed application starts all local components together:

- FastAPI server on private-network port `8765`
- Premium TradePilot PWA
- MetaTrader 5 Connector
- Windows tray icon and status window
- One-time passwordless setup QR

The user experience is:

```text
Install → Open MT5 Demo → Scan QR → TradePilot opens on the phone
```

No PowerShell, `.env` editing, username, or password is needed after the
installer has been built.

## Build the installer

The MetaTrader5 Python module contains a Windows-only native extension, so the
installer must be compiled on a Windows x64 computer.

Requirements:

- Python 3.12 x64
- Node.js and npm
- Windows `winget` (normally included)
- Internet access during the build

Double-click:

```text
BUILD_INSTALLER.bat
```

The script builds the web application, creates the Windows executable, installs
Inno Setup through `winget` if needed, and writes:

```text
release\TradePilotSetup.exe
```

## Install and test

1. Stop the old development Server, Web, and Connector windows.
2. Open MT5 and log into a Demo account.
3. Run `release\TradePilotSetup.exe`.
4. Accept the Windows private-network firewall rule.
5. Launch TradePilot Connector.
6. Scan the displayed QR with the phone camera.
7. The phone opens the local web app and receives a one-time session.

The phone and Windows computer must be on the same private Wi-Fi/LAN. The QR
expires after five minutes and can be regenerated.

## Optional remote access with Tailscale

Install and sign into Tailscale on Windows and the phone using the same
Tailscale account. When Tailscale is connected, TradePilot detects the Windows
`100.x.x.x` address and generates the setup QR with that address. The web app
then works from another Wi-Fi or mobile data while the Tailscale VPN is active
on both devices.

The installer adds a firewall rule limited to the Tailscale address range
`100.64.0.0/10`. It does not expose port `8765` to the public internet.

## Data and security

Application data is stored under:

```text
%LOCALAPPDATA%\TradePilot
```

The prototype is locked to Demo mode:

```text
DEMO_ONLY=true
ALLOW_LIVE_TRADING=false
```

The generated installer is unsigned. Windows SmartScreen may show a warning.
A production release needs a code-signing certificate, independent security
testing, HTTPS/cloud deployment for remote access, secure OS credential
storage, and broker-by-broker execution testing.