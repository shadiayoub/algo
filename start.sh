#!/bin/bash
# Entry point for the combined Signals container: OHLC bridge + dashboard + scanner,
# all sharing one network namespace so MiniSig can reach the bridge on localhost:9008.

# Persist rsi_alerts.json into the mounted data/ volume without changing app code:
# the scanner writes ./rsi_alerts.json and the dashboard fetches it from the web root,
# so we point both at the volume via a symlink.
mkdir -p /app/data
ln -sf /app/data/rsi_alerts.json /app/rsi_alerts.json

# Start OHLC bridge in background (listens on 127.0.0.1:9008)
cd /app/ohlc-bridge && node dist/index.js &

# Serve the dashboard (index.html polls rsi_alerts.json) on port 8080 in background
cd /app && python -m http.server 8080 &

# Start MiniSig in foreground (keeps the container alive)
cd /app && python -u alertPivotRsi.py
