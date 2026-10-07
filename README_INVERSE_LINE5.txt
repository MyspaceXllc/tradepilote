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
