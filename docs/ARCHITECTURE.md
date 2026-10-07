# Architecture

Phone PWA → HTTPS/WSS → FastAPI → WSS → Windows Connector → MetaTrader 5 → Broker.

Command flow:
1. PWA creates a unique command ID.
2. API authenticates user/device and applies demo/rate checks.
3. API stores the command.
4. Connector receives it over WebSocket.
5. Connector validates symbol/volume and calls MT5.
6. Connector returns a result using the same command ID.
7. API stores and forwards the result.

`command_id` prevents the API from creating duplicate command records on retries. For live money, broker-side execution after a network failure must still be tested carefully.
