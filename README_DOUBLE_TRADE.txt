TradePilot — Double Trade UI update

Changes:
1. Added DOUBLE TRADE under Shark grid.
   - Opens BUY + SELL at MARKET using the existing BUY/SELL command path.
   - Intended for MT5 HEDGING accounts. On a netting account, the second market order may offset the first.
   - The two commands are dispatched together from the web UI. The latest source implementation waits for both results and reports each ticket/result.
2. Removed CLOSE LOSERS from the quick selective-close area.
3. Made CLOSE WINNERS larger and full-width directly under CLOSE POSITION.

Source:
- web/src/main.jsx
- web/src/styles.css

The bundled web/dist copy also contains a compatibility UI patch so the ready-to-use dist works even before a local rebuild.

Build on Windows:
- cd web
- npm install
- npm run build

The build will regenerate web/dist from the source implementation.
