/**
 * OHLC Data Bridge for MiniSig
 *
 * A tiny standalone service that connects to the cTrader Open API and exposes a
 * single HTTP endpoint returning candle (trendbar) data as JSON. MiniSig calls
 * this to obtain index data (e.g. US30) that Binance doesn't provide.
 *
 * Completely independent of DoochyBot — it only shares the same cTrader credentials.
 */

import "dotenv/config";
import express, { Request, Response } from "express";
import { CTraderConnection } from "@reiryoku/ctrader-layer";

// ============================================================
// ENVIRONMENT
// ============================================================

function required(name: string): string {
  const value = process.env[name];
  if (!value) {
    console.error(`Missing required environment variable: ${name}`);
    process.exit(1);
  }
  return value;
}

const HOST = required("CTRADER_HOST");
const CTRADER_PORT = Number(required("CTRADER_PORT"));
const CLIENT_ID = required("CLIENT_ID");
const CLIENT_SECRET = required("CLIENT_SECRET");
const ACCESS_TOKEN = required("ACCESS_TOKEN");
const ACCOUNT_ID = Number(required("ACCOUNT_ID")); // ctidTraderAccountId (int64, fits in JS number)
const HTTP_PORT = Number(process.env.PORT ?? 9008);

// ============================================================
// TIMEFRAME MAP
// ============================================================
//
// IMPORTANT: cTrader's `period` field is an enum (ProtoOATrendbarPeriod), NOT the
// number of minutes per bar. e.g. M15 = 7, H1 = 9, H4 = 10. We keep BOTH:
//   - `period`  -> the enum value sent in the request
//   - `minutes` -> the bar length in minutes, used to compute the lookback window
const TIMEFRAMES: Record<string, { period: number; minutes: number }> = {
  "1m": { period: 1, minutes: 1 }, // M1
  "5m": { period: 5, minutes: 5 }, // M5
  "15m": { period: 7, minutes: 15 }, // M15
  "30m": { period: 8, minutes: 30 }, // M30
  "1h": { period: 9, minutes: 60 }, // H1
  "4h": { period: 10, minutes: 240 }, // H4
  "1d": { period: 12, minutes: 1440 }, // D1
};

// Trendbar prices are sent as integers scaled by 1e5.
const PRICE_SCALE = 100000;

// ============================================================
// CONNECTION STATE
// ============================================================

let connection: CTraderConnection | null = null;
let connected = false;
const symbolMap = new Map<string, number>();

let reconnectAttempt = 0;
const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 16000, 30000]; // ms, caps at 30s

let heartbeatTimer: NodeJS.Timeout | null = null;
let lastHeartbeatResponse = 0;
// True after we've logged an unresponsive-heartbeat warning; suppresses repeats
// until a heartbeat response (or reconnect) clears it, so we warn once per event.
let heartbeatUnresponsive = false;

// ============================================================
// HELPERS
// ============================================================

/** Coerce a protobuf int64 (number | string | Long) into a JS number. */
function toNum(v: unknown): number {
  if (v === null || v === undefined) return 0;
  if (typeof v === "number") return v;
  if (typeof v === "string") return Number(v);
  if (typeof (v as { toNumber?: () => number }).toNumber === "function") {
    return (v as { toNumber: () => number }).toNumber();
  }
  return Number(v);
}

/** Extract a single string from an Express query value. */
function qstr(v: unknown): string | undefined {
  if (typeof v === "string") return v;
  if (Array.isArray(v) && typeof v[0] === "string") return v[0];
  return undefined;
}

// Brokers expose indices/commodities with a suffix (e.g. US30 -> "US30.cash").
// Callers (MiniSig) shouldn't need to know each broker's naming, so resolve a
// requested symbol against the live map: exact match, then common suffixes,
// then a case-insensitive fallback. Returns the exact symbol name, or undefined.
const SYMBOL_SUFFIXES = ["", ".cash", ".spot"];

function resolveSymbol(requested: string): string | undefined {
  for (const suffix of SYMBOL_SUFFIXES) {
    const candidate = requested + suffix;
    if (symbolMap.has(candidate)) return candidate;
  }
  const lower = requested.toLowerCase();
  for (const name of symbolMap.keys()) {
    if (name.toLowerCase() === lower) return name;
    for (const suffix of SYMBOL_SUFFIXES) {
      if (suffix && name.toLowerCase() === lower + suffix) return name;
    }
  }
  return undefined;
}

// ============================================================
// CTRADER CONNECTION
// ============================================================

async function connect(): Promise<void> {
  connection = new CTraderConnection({ host: HOST, port: CTRADER_PORT });
  await connection.open();

  // Authenticate the application.
  await connection.sendCommand("ProtoOAApplicationAuthReq", {
    clientId: CLIENT_ID,
    clientSecret: CLIENT_SECRET,
  });

  // Authenticate the trading account.
  await connection.sendCommand("ProtoOAAccountAuthReq", {
    accessToken: ACCESS_TOKEN,
    ctidTraderAccountId: ACCOUNT_ID,
  });

  await loadSymbols();

  connected = true;
  reconnectAttempt = 0;
  lastHeartbeatResponse = Date.now();
  heartbeatUnresponsive = false;

  registerDisconnectHandlers();
  startHeartbeat();

  console.log("cTrader connection established and authenticated");
}

async function loadSymbols(): Promise<void> {
  const conn = connection;
  if (!conn) return;

  const res = (await conn.sendCommand("ProtoOASymbolsListReq", {
    ctidTraderAccountId: ACCOUNT_ID,
    includeArchivedSymbols: false,
  })) as { symbol?: Array<{ symbolId?: unknown; symbolName?: string; name?: string }> };

  symbolMap.clear();
  for (const s of res?.symbol ?? []) {
    const name = s.symbolName ?? s.name;
    if (name) symbolMap.set(String(name), toNum(s.symbolId));
  }

  console.log(`Loaded ${symbolMap.size} symbols from cTrader`);
}

function registerDisconnectHandlers(): void {
  const conn = connection;
  if (!conn) return;

  const onDrop = (reason?: unknown): void => {
    if (!connected) return; // already handling a drop
    console.warn(
      `cTrader connection lost${reason !== undefined ? `: ${String(reason)}` : ""}`,
    );
    handleDisconnect();
  };

  // Socket lifecycle is surfaced by the library; guarded in case a given version
  // names these differently. Drop detection drives the manual reconnect loop.
  try {
    (conn as unknown as { on?: (e: string, cb: (...a: unknown[]) => void) => void }).on?.(
      "close",
      () => onDrop("close"),
    );
  } catch {
    /* ignore */
  }
  try {
    (conn as unknown as { on?: (e: string, cb: (...a: unknown[]) => void) => void }).on?.(
      "error",
      (e: unknown) => onDrop(e),
    );
  } catch {
    /* ignore */
  }
}

function handleDisconnect(): void {
  if (!connected) return;
  connected = false;
  stopHeartbeat();
  scheduleReconnect();
}

function scheduleReconnect(): void {
  const delay = RECONNECT_DELAYS[Math.min(reconnectAttempt, RECONNECT_DELAYS.length - 1)];
  reconnectAttempt += 1;
  console.log(
    `Reconnecting to cTrader in ${delay / 1000}s (attempt ${reconnectAttempt})...`,
  );
  setTimeout(async () => {
    try {
      await connect();
    } catch (e) {
      console.warn(`Reconnect attempt ${reconnectAttempt} failed: ${String(e)}`);
      scheduleReconnect();
    }
  }, delay);
}

// ============================================================
// HEARTBEAT (liveness only — never triggers disconnect, per spec)
// ============================================================

function startHeartbeat(): void {
  stopHeartbeat();

  const conn = connection;
  if (!conn) return;

  // Inbound heartbeats from the server clear the "unresponsive" warning.
  try {
    (conn as unknown as { on?: (e: string, cb: () => void) => void }).on?.(
      "ProtoHeartbeatEvent",
      () => {
        lastHeartbeatResponse = Date.now();
        if (heartbeatUnresponsive) {
          console.log("cTrader heartbeat responses resumed");
          heartbeatUnresponsive = false;
        }
      },
    );
  } catch {
    /* ignore */
  }

  heartbeatTimer = setInterval(() => {
    const c = connection;
    if (!connected || !c) return;

    const sentAt = Date.now();
    try {
      c.sendHeartbeat();
    } catch (e) {
      console.warn(`Heartbeat send failed: ${String(e)}`);
    }

    // Warn if nothing came back within 10s, but keep the connection open —
    // the library manages reconnection.
    setTimeout(() => {
      if (connected && lastHeartbeatResponse < sentAt && !heartbeatUnresponsive) {
        heartbeatUnresponsive = true;
        console.warn("No heartbeat response from cTrader within 10s (connection kept open)");
      }
    }, 10_000);
  }, 25_000);
}

function stopHeartbeat(): void {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
}

// ============================================================
// HTTP SERVER
// ============================================================

const app = express();

// List the symbols cTrader actually exposes on this account. Useful to discover
// the exact name a broker uses for an instrument (e.g. US30 may be "WallSt30",
// "US30.0", "#US30", etc.) since /ohlc matches the name exactly.
//   GET /symbols          -> all symbol names (sorted)
//   GET /symbols?q=us30   -> names containing the query, case-insensitive
app.get("/symbols", (req: Request, res: Response): void => {
  if (!connected) {
    res.status(503).json({ error: "cTrader connection unavailable" });
    return;
  }

  const q = qstr(req.query.q)?.toLowerCase();
  let names = Array.from(symbolMap.keys());
  if (q) {
    names = names.filter((n) => n.toLowerCase().includes(q));
  }
  names.sort((a, b) => a.localeCompare(b));

  res.json({ count: names.length, symbols: names });
});

app.get("/ohlc", async (req: Request, res: Response): Promise<void> => {
  const symbol = qstr(req.query.symbol);
  const timeframe = qstr(req.query.timeframe);
  const countRaw = qstr(req.query.count);

  if (!symbol) {
    res.status(400).json({ error: "Missing required parameter: symbol" });
    return;
  }
  if (!timeframe) {
    res.status(400).json({ error: "Missing required parameter: timeframe" });
    return;
  }

  const conn = connection;
  if (!connected || !conn) {
    res.status(503).json({ error: "cTrader connection unavailable" });
    return;
  }

  const resolvedSymbol = resolveSymbol(symbol);
  const symbolId = resolvedSymbol !== undefined ? symbolMap.get(resolvedSymbol) : undefined;
  if (resolvedSymbol === undefined || symbolId === undefined) {
    res.status(400).json({ error: `Symbol not found: ${symbol}` });
    return;
  }

  const tf = TIMEFRAMES[timeframe];
  if (!tf) {
    res.status(400).json({ error: `Unknown timeframe: ${timeframe}` });
    return;
  }

  const count = Math.max(1, Number(countRaw ?? 100) || 100);
  const now = Date.now();
  const from = now - count * tf.minutes * 60 * 1000;

  try {
    const response = (await conn.sendCommand("ProtoOAGetTrendbarsReq", {
      ctidTraderAccountId: ACCOUNT_ID,
      symbolId,
      period: tf.period,
      fromTimestamp: from,
      toTimestamp: now,
    })) as {
      trendbar?: Array<{
        low?: unknown;
        high?: unknown;
        open?: unknown;
        close?: unknown;
        deltaOpen?: unknown;
        deltaHigh?: unknown;
        deltaClose?: unknown;
        volume?: unknown;
      }>;
    };

    const bars = response?.trendbar ?? [];

    const opens: number[] = [];
    const highs: number[] = [];
    const lows: number[] = [];
    const closes: number[] = [];
    const volumes: number[] = [];

    for (const b of bars) {
      let open: number;
      let high: number;
      let low: number;
      let close: number;

      const hasDeltas =
        b.deltaOpen !== undefined || b.deltaHigh !== undefined || b.deltaClose !== undefined;

      if (hasDeltas) {
        // Raw ProtoOATrendbar: low plus deltas, all scaled by 1e5.
        const lowRaw = toNum(b.low);
        low = lowRaw / PRICE_SCALE;
        high = (lowRaw + toNum(b.deltaHigh)) / PRICE_SCALE;
        open = (lowRaw + toNum(b.deltaOpen)) / PRICE_SCALE;
        close = (lowRaw + toNum(b.deltaClose)) / PRICE_SCALE;
      } else {
        // Already-decoded OHLC (defensive — depends on library version).
        low = toNum(b.low);
        high = toNum(b.high);
        open = toNum(b.open);
        close = toNum(b.close);
      }

      opens.push(open);
      highs.push(high);
      lows.push(low);
      closes.push(close);
      volumes.push(toNum(b.volume));
    }

    // cTrader returns trendbars in chronological order (oldest first); keep as-is.
    const current_price = closes.length > 0 ? closes[closes.length - 1] : null;

    const resolvedNote = resolvedSymbol !== symbol ? ` (resolved to ${resolvedSymbol})` : "";
    console.log(
      `OHLC request: symbol=${symbol}${resolvedNote} timeframe=${timeframe} count=${count} → returned ${closes.length} candles`,
    );

    res.json({ closes, highs, lows, opens, volumes, current_price });
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    console.error(`OHLC fetch failed for ${symbol} ${timeframe}: ${message}`);
    res.status(500).json({ error: `Failed to fetch OHLC data: ${message}` });
  }
});

// ============================================================
// STARTUP / SHUTDOWN
// ============================================================

async function main(): Promise<void> {
  try {
    await connect();
  } catch (e) {
    console.warn(`Initial cTrader connection failed, starting in degraded mode: ${String(e)}`);
    scheduleReconnect();
  }

  const server = app.listen(HTTP_PORT, "127.0.0.1", () => {
    console.log(`OHLC bridge ready on port ${HTTP_PORT}`);
  });

  const shutdown = (): void => {
    console.log("OHLC bridge shutting down");
    stopHeartbeat();
    server.close();
    try {
      (connection as unknown as { close?: () => void })?.close?.();
    } catch {
      /* ignore */
    }
    process.exit(0);
  };

  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

main().catch((e) => {
  console.error(`Fatal startup error: ${String(e)}`);
  process.exit(1);
});
