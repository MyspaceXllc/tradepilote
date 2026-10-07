# MT5 notes

Install MetaTrader 5 separately and log into a Demo account.

The connector uses the MetaTrader5 Python integration:
- initialize
- symbol_info / symbol_select
- symbol_info_tick
- positions_get / orders_get
- order_send

Broker symbols may be `XAUUSD`, `XAUUSDm`, `XAUUSD.a`, etc. TradePilot now
loads the tradeable symbol list directly from the connected terminal so the
phone uses the broker's exact symbol names. The list can be refreshed from the
symbol field.


This prototype sends absolute SL/TP prices, not distances.

Broker/symbol filling modes can differ. The connector retries a different
filling mode only when MT5 explicitly returns `INVALID_FILL`; it must never
retry after an ambiguous network failure because that could duplicate a trade.

The connector derives Demo/Live mode from `account_info().trade_mode`, not
from a user-provided mode label. It also blocks live-account commands unless
`ALLOW_LIVE_TRADING=true`.
