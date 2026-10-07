TradePilot safe fix

This package is based on the original TradePilot web project, not the broken MutationObserver patch.

Changes:
- Removed the unsafe DOM MutationObserver patch that could cause a black screen.
- UTC time is explicit in the mobile status bar.
- CLOSE LOSERS is removed; CLOSE WINNERS remains.
- Added a safe M1 Fusion Strategy strip below the performance banner.
- M1 strip refreshes every 60 seconds and reads the existing Signal Fusion M1 endpoint.
- Added DOUBLE TRADE under Shark Grid. It sends BUY then SELL at market and requires an MT5 hedging account.
- No Line 5 is added.
- Existing Line 1-4 Fusion page remains intact.
- Service-worker cache version is bumped to 2.9.4.

Install:
1. Extract the ZIP.
2. Run INSTALL_BUILD.bat on Windows.
3. The script runs npm install and npm run build.
4. If the server is already running, restart it and hard-refresh with Ctrl+F5 once.
