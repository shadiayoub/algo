FROM python:3.11-slim

WORKDIR /app

# --- Node.js 20 (for the OHLC bridge) ---
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# --- Python dependencies (cached on requirements.txt) ---
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Bridge dependencies (cached on package.json/tsconfig) ---
COPY ohlc-bridge/package.json ohlc-bridge/tsconfig.json ./ohlc-bridge/
RUN cd ohlc-bridge && npm install

# --- Application source ---
COPY . .

# --- Build the bridge (compiles src/ -> dist/) ---
RUN cd ohlc-bridge && npm run build

# --- Startup script (launches bridge + dashboard + scanner) ---
RUN chmod +x ./start.sh

# Dashboard (MiniSig). The bridge stays on 127.0.0.1:9008 and is NOT exposed.
EXPOSE 8080

CMD ["./start.sh"]
