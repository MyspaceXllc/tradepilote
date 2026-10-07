TradePilot Signal Fusion — PRO 5-Lane Update

Changes:
1. Lane 4 restored to the original trade timeline (BUY green / SELL red).
2. New Lane 5: CONTRARIAN SIGNAL, driven from Lane 3 pressure:
   - Lane 3 BUY/BULLISH  -> Lane 5 SELL (orange)
   - Lane 3 SELL/BEARISH -> Lane 5 BUY (blue)
   - Neutral -> WAIT/neutral
3. Default timeframe is restored to M1 on first launch of this UI version.
4. UI refreshed with a more professional glass/neon dashboard treatment,
   lane chips, stronger hierarchy, hover/focus states, and a PRO signal-engine card.
5. Both web/public/fusion.html and web/dist/fusion.html are updated.

Build:
- On Windows, double-click INSTALL_BUILD.bat.
- It runs npm install and npm run build.
- The public/fusion.html file is copied into dist by Vite.

No backend/API logic was changed.
