TradePilot — Line 5 exact inverse of Line 4

Behavior:
- Line 4 remains the original Trade Timeline / trade engine signal.
- Line 5 is driven ONLY by Line 4 trade_state and trade_event.
- If Line 4 = BUY, Line 5 = SELL (orange).
- If Line 4 = SELL, Line 5 = BUY (blue).
- If Line 4 = WAIT, Line 5 = WAIT/neutral.
- Entry events are inverted:
    BUY_OPEN  -> SELL_OPEN
    SELL_OPEN -> BUY_OPEN
- Close events are inverted with the SAME action type:
    BUY_CLOSE  -> SELL_CLOSE
    SELL_CLOSE -> BUY_CLOSE
- Line 5 now also displays the corresponding open/close markers.

Files changed:
- web/public/fusion.html
- web/dist/fusion.html


TradePilot — UTC + Multi-Timeframe dashboard update

Changes:
- All displayed timestamps in fusion.html now use explicit UTC formatting.
- Added a live Multi-Timeframe Trade Position panel for M1, M5, M15, H1 and H4.
- Each timeframe is fetched from the existing /local/signal-fusion/data endpoint using the existing signal engine.
- Each card shows current BUY/SELL/WAIT position, open/no-position result status, pressure and UTC time.
- No P/L is fabricated; the current backend is analysis-only and does not expose a monetary P/L field in this UI.
- Line 4 remains the original trade timeline.
- Line 5 remains an exact inverse of Line 4.
