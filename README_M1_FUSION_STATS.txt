TradePilot M1 Fusion + UTC update

Changes in this package:
1. Removed Line 5 / contrarian lane. The Fusion matrix is 4 lanes only.
2. Added M1 as a selectable Fusion Strategy timeframe and made M1 the default.
3. Fusion refreshes on the M1 cycle (60 seconds) and uses closed MT5 M1 candles.
4. Added a compact M1 Fusion Strategy strip below the account performance banner in the mobile control UI.
5. The M1 strip refreshes every 60 seconds and shows signal, pressure, result now, and last M1 bar time.
6. Mobile clock is displayed in UTC.
7. Existing Double Trade and Close Winners changes are preserved; Close Losers remains removed.
8. The M1 strip uses the existing /local/signal-fusion/data endpoint; no fake trading results are generated.

Build:
- On Windows, run INSTALL_BUILD.bat.
- npm install may be required before npm run build.

Note:
The provided environment did not have the Vite executable installed, so a production React bundle could not be rebuilt here. The source changes are included in web/src, the static Fusion page is updated in web/public and web/dist, and the runtime UI patch is updated in web/public and web/dist so the existing production build receives the M1 strip/UTC behavior.
