# TradePilot v1 review

## v1.3 Windows all-in-one prototype

- Added a Windows desktop launcher with a simple status and setup-QR interface.
- The launcher starts FastAPI, the PWA, and the MT5 Connector together.
- Added passwordless one-time QR setup for a phone on the same private network.
- Added tray controls, auto-start installer shortcuts, and a private-network
  firewall rule for the local web app.
- Added PyInstaller and Inno Setup build configuration.
- The Windows installer must be compiled on Windows because MetaTrader5 ships
  a Windows-only native Python extension.

## v1.2 premium trading interface

- Compact device and symbol controls share one row.
- SELL is red, BUY is green, and CLOSE is a larger gold action.
- Limit, SL, and TP controls live in a collapsible Advanced order section.
- The header shows live entry price, current price, direction, volume, and P/L.
- Winning P/L is blue and losing P/L is red.
- Account numbers are masked in the interface.
- A read-only MT5 snapshot endpoint updates the header without writing command
  or audit rows every few seconds.

## Fixed in this reviewed copy

- Pairing no longer fails on every connector restart after a one-time token is used.
- Pairing bind now requires connector proof and blocks cross-user device takeover.
- Pairing secrets are sent in the HTTPS request body instead of the URL query.
- Command ID lookup no longer exposes another user's result.
- Connector results are accepted only from the device assigned to the command.
- Demo/Live mode is derived from MT5 account information.
- The connector has an independent live-trading lock.
- Limit orders now require an explicit BUY LIMIT or SELL LIMIT direction.
- Broker filling-mode fallback occurs only after MT5 reports INVALID_FILL.
- Partial CLOSE failures are returned instead of reporting unconditional success.
- Connector application heartbeats update device presence.
- The PWA displays MT5 device state instead of only server WebSocket state.
- The PWA polls command status if the result WebSocket notification is missed.
- SQLite uses WAL, a busy timeout, and foreign-key enforcement.
- Docker files claimed by the README are now present.
- PWA service worker and install icons are now present.
- Emergency Stop now locks further server commands, closes positions, and
  cancels pending orders; unlocking requires an explicit confirmed action.

## Still intentionally incomplete

- Real camera-based QR scanning is not implemented.
- The connector is not packaged or signed as a Windows installer/service.
- JWT is still stored in browser localStorage; production should use a hardened
  session design plus passkeys/2FA.
- Authentication rate limiting, password reset, email verification, device
  approval, risk/exposure limits, and a production database are not implemented.
- Multi-instance backend WebSocket routing requires Redis or an equivalent broker.
- Real MT5 execution must be tested on Windows against each target broker.

## Validation constraints

Python and frontend dependencies were not available in the review environment,
and internet access was not enabled by the host permission layer. Source syntax
and project structure can be checked locally, but dependency-backed FastAPI/Vite
tests and real MT5 tests remain release blockers.