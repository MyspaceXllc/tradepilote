# Automatic setup QR renewal

The Windows connector requests a fresh one-time setup token 15 seconds before
the displayed QR expires. If creation temporarily fails, it retries after 15
seconds. Scanning still consumes a token once; automatic renewal does not reuse
or extend an old token.

# Pairing

1. Log into the PWA.
2. Press `PAIR DEVICE`.
3. Copy the one-time pairing token.
4. On the MT5 PC, open `connector/.env`.
5. Set:
   `PAIRING_TOKEN=<token>`
6. Restart the connector.
7. The connector registers itself and claims the token.
8. Refresh the PWA and select the device.
9. Future connector restarts skip the already-claimed one-time token.

The QR shown by the PWA contains the server URL and the same short-lived token. It is useful as a transfer/visual backup, but the current Windows connector uses the token field directly; it does not require a webcam.

For a future production UX, add a Windows QR scanner that parses the `tradepilot://pair?...` URI.

The server requires proof of the connector token when binding a device and
refuses to take over a device already paired to another user.
