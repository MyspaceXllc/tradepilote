TradePilot final patch 2.9.4

Changes:
- DOUBLE TRADE is now a native TradePilot control. One click sends exactly one BUY and one SELL at market using the current lot size. No confirmation popup.
- Removed the old overlay Double Trade implementation that could trigger only one order.
- Fusion Strategy timeframe switcher includes 1M, 5M, 15M, 1H and 4H. 1M is the default.
- Fusion candle rail uses the selected timeframe and refreshes every 60 seconds.
- Line 5 is not added; Fusion remains the four-line design.
- Close Winners is preserved and Close Losers remains removed.
- UTC clock preserved.

Install: run INSTALL_BUILD.bat, then restart TradePilot and hard-refresh with Ctrl+F5.
