#!/usr/bin/env python3
"""
Multi-Exchange RSI Alert Bot with Pivot/SR Integration
Supports: Binance Futures (XAU/USDT, XAG/USDT), Kraken, Bybit, OKX
"""

import ccxt
import pandas as pd
import time
import json
import sys
import requests
from datetime import datetime
from pathlib import Path

# ============================================================
# AUDIO SETUP
# ============================================================

def play_beep(direction):
    frequency = 1000 if direction == "buy" else 800
    duration = 500
    
    if sys.platform == "win32":
        try:
            import winsound
            winsound.Beep(frequency, duration)
        except:
            print("\a", end="", flush=True)
    else:
        print("\a", end="", flush=True)

# ============================================================
# CONFIGURATION - EDIT THESE VALUES
# ============================================================

CONFIG = {
    # Exchange Options: binance, binanceusdm (futures), kraken, bybit, okx, coinbase
    "exchange": "binance",  # binanceusdm = Binance USDT-M Futures (supports XAU/USDT, XAG/USDT)
    "exchange_type": "futures",  # 'spot' or 'futures'
    
    # Symbols for Binance Futures (use /USDT for USDT-M perpetual)
    "symbols": [
        # Precious Metals (Binance TradFi Perpetuals)
        "XAU/USDT:USDT",   # Gold
        "XAG/USDT:USDT",   # Silver
        # Cryptocurrencies
        "AAVE/USDT:USDT",
        "ADA/USDT:USDT",
        "AIXBT/USDT:USDT",
        "ALGO/USDT:USDT",
        "APT/USDT:USDT",
        "ARB/USDT:USDT",
        "ASTER/USDT:USDT",
        "ATOM/USDT:USDT",
        "AVAX/USDT:USDT",
        "BCH/USDT:USDT",
        "BNB/USDT:USDT",
        "BTC/USDT:USDT",
        "CRV/USDT:USDT",
        "DOT/USDT:USDT",
        "ETC/USDT:USDT",
        "ETH/USDT:USDT",
        "FARTCOIN/USDT:USDT",
        "FIL/USDT:USDT",
        "FLOKI/USDT:USDT",
        "GRASS/USDT:USDT",
        "HBAR/USDT:USDT",
        "INJ/USDT:USDT",
        "IP/USDT:USDT",
        "JTO/USDT:USDT",
        "JUP/USDT:USDT",
        "KAITO/USDT:USDT",
        "LDO/USDT:USDT",
        "LINK/USDT:USDT",
        "LIT/USDT:USDT",
        "LTC/USDT:USDT",
        "MOODENG/USDT:USDT",
        "NEAR/USDT:USDT",
        "ONDO/USDT:USDT",
        "OP/USDT:USDT",
        "ORDI/USDT:USDT",
        "PENGU/USDT:USDT",
        "PEPE/USDT:USDT",
        "PNUT/USDT:USDT",
        "POL/USDT:USDT",
        "PUMP/USDT:USDT",
        "RENDER/USDT:USDT",
        "S/USDT:USDT",
        "SOL/USDT:USDT",
        "STX/USDT:USDT",
        "SUI/USDT:USDT",
        "TAO/USDT:USDT",
        "TIA/USDT:USDT",
        "TON/USDT:USDT",
        "TRX/USDT:USDT",
        "UNI/USDT:USDT",
        "VIRTUAL/USDT:USDT",
        "WIF/USDT:USDT",
        "WLD/USDT:USDT",
        "XPL/USDT:USDT",
        "XRP/USDT:USDT",
        "ZEC/USDT:USDT",
        # Indices & commodities served by the local cTrader OHLC bridge. These are
        # routed to the bridge (not Binance) and scanned on bridge_timeframes.
        "US30.cash",
        "USOIL.cash",
        "US500.cash",
        "US100.cash",
    ],

    # Timeframes to monitor
    "timeframes": ["5m", "15m", "1h", "4h"],
    
    # RSI Settings
    "rsi_period": 7,
    "buy_zone_low": 40,
    "buy_zone_high": 50,
    "sell_zone_low": 50,
    "sell_zone_high": 60,
    
    # Pivot Settings
    "enable_pivot_filter": True,
    "pivot_proximity_percent": 0.5,
    "pivot_timeframe": "1d",

    # Feed Filter — suppress signals that fight the higher-timeframe trend, applied at
    # the rsi_alerts.json write point so trend-misaligned signals never reach DoochyBot.
    # Simple price comparison on data MiniSig already fetches — no extra requests.
    "trend_filter_enabled": True,
    "trend_lookback_1h": 1,   # 1H series: current vs N candles ago (1 candle ≈ 1h short-term trend)
    "trend_lookback_4h": 2,   # 4H series: current vs N candles ago (1 candle ≈ 4h main trend)

    # Confidence Boosters — these ADD points to the confidence score only. They never
    # gate, block, or suppress a signal: a signal that would publish still publishes,
    # just with a potentially higher confidence when momentum (MACD) or statistical
    # extreme (Bollinger %B) confirms what RSI and pivot already saw.
    "enable_macd_filter": True,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "macd_divergence_lookback": 5,
    "enable_bb_filter": True,
    "bb_period": 20,
    "bb_stddev": 2,
    "bb_upper_threshold": 0.8,
    "bb_lower_threshold": 0.2,

    # OHLC Bridge — symbols in bridge_symbols are fetched from the local cTrader
    # bridge instead of Binance, and scanned on bridge_timeframes. Indices return
    # empty data for intraday on the bridge, so they are scanned on 1d only.
    "bridge_enabled": True,
    "bridge_url": "http://localhost:9008",
    "bridge_symbols": ["US30.cash", "USOIL.cash", "US500.cash", "US100.cash"],
    "bridge_timeframes": ["1d"],

    # Bot Settings
    "check_interval": 15,
    "enable_audio": True,
    "audio_cooldown_seconds": 300,
    "log_to_file": True,
    "log_file": "rsi_alerts.log",
    "candle_limit": 100,
    "try_usdt_first": True,
    "try_usd_fallback": True,
}

# ============================================================
# PIVOT CALCULATOR
# ============================================================

class PivotCalculator:
    @staticmethod
    def calculate_pivots(high, low, close):
        pp = (high + low + close) / 3
        r1 = (2 * pp) - low
        r2 = pp + (high - low)
        r3 = high + 2 * (pp - low)
        s1 = (2 * pp) - high
        s2 = pp - (high - low)
        s3 = low - 2 * (high - pp)
        
        return {
            "PP": pp, "R1": r1, "R2": r2, "R3": r3,
            "S1": s1, "S2": s2, "S3": s3
        }
    
    @staticmethod
    def is_near_level(price, level, proximity_percent):
        if level == 0 or level is None:
            return False
        distance = abs(price - level) / price * 100
        return distance <= proximity_percent
    
    @staticmethod
    def get_nearest_level(price, pivots, proximity_percent):
        levels = {
            "R3": pivots["R3"], "R2": pivots["R2"], "R1": pivots["R1"],
            "PP": pivots["PP"],
            "S1": pivots["S1"], "S2": pivots["S2"], "S3": pivots["S3"]
        }
        
        nearest = None
        min_distance = float('inf')
        
        for name, level in levels.items():
            if level is None:
                continue
            distance = abs(price - level) / price * 100
            if distance <= proximity_percent and distance < min_distance:
                min_distance = distance
                nearest = name
        
        return nearest, min_distance

# ============================================================
# ALERT MANAGER
# ============================================================

class AlertManager:
    def __init__(self, config):
        self.config = config
        self.last_alert = {}
        self.alert_history = []
        self.alert_file = "rsi_alerts.json"
        self.last_tp_alert = {}  # For take profit cooldown
        
    def export_alerts(self):
        try:
            with open(self.alert_file, "w") as f:
                json.dump(self.alert_history, f, indent=2)
        except Exception as e:
            pass
    
    def append_alert_immediately(self, alert_record):
        """Write a single alert to JSON without rewriting the entire history"""
        try:
            from pathlib import Path
            # Load existing alerts
            existing = []
            if Path(self.alert_file).exists():
                with open(self.alert_file, 'r') as f:
                    try:
                        existing = json.load(f)
                    except json.JSONDecodeError:
                        existing = []
            
            # Add new alert at the beginning (newest first)
            existing.insert(0, alert_record)
            
            # Keep last 500 (prevents file bloat and slow writes)
            existing = existing[:500]
            
            # Write immediately
            with open(self.alert_file, 'w') as f:
                json.dump(existing, f, indent=2)
        except Exception as e:
            pass  # Silent fail so bot continues
    
    def should_alert(self, symbol, timeframe, direction):
        key = f"{symbol}_{timeframe}_{direction}"
        now = time.time()
        
        if key in self.last_alert:
            if now - self.last_alert[key] < self.config["audio_cooldown_seconds"]:
                return False
        
        self.last_alert[key] = now
        return True
    
    def should_alert_take_profit(self, symbol, timeframe):
        """Prevent take profit spam (1 hour cooldown)"""
        key = f"tp_{symbol}_{timeframe}"
        now = time.time()
        
        if key in self.last_tp_alert:
            if now - self.last_tp_alert[key] < 3600:  # 1 hour cooldown
                return False
        
        self.last_tp_alert[key] = now
        return True
    
    def _confluence_score(self, direction, rsi_value, pivot_level, pivot_distance,
                          closes=None, highs=None, lows=None):
        """Score signal quality 0–6 based on RSI zone, pivot alignment, and momentum.

        +2 if RSI is in the ideal zone (buy 40-50, sell 50-60)
        +1 if a pivot level is present
        +1 if pivot_distance < 0.5%
        +1 if MACD divergence confirms the direction (when enable_macd_filter)
        +1 if Bollinger %B is at a confirming extreme (when enable_bb_filter)

        The MACD/BB boosters only ADD points — they never block a signal. Returns
        (score, parts) where parts is the per-component breakdown for logging.
        """
        parts = {"RSI": 0, "pivot": 0, "dist": 0, "MACD": 0, "BB": 0}

        if direction == "buy" and self.config["buy_zone_low"] <= rsi_value <= self.config["buy_zone_high"]:
            parts["RSI"] = 2
        elif direction == "sell" and self.config["sell_zone_low"] <= rsi_value <= self.config["sell_zone_high"]:
            parts["RSI"] = 2
        if pivot_level is not None:
            parts["pivot"] = 1
        if pivot_distance is not None and pivot_distance < 0.5:
            parts["dist"] = 1

        if self.config.get("enable_macd_filter", True) and closes is not None:
            if _macd_divergence(
                closes, highs, lows, direction,
                lookback=self.config.get("macd_divergence_lookback", 5),
                fast=self.config.get("macd_fast", 12),
                slow=self.config.get("macd_slow", 26),
                signal=self.config.get("macd_signal", 9),
            ):
                parts["MACD"] = 1

        if self.config.get("enable_bb_filter", True) and closes is not None:
            if _bb_extreme(
                closes, direction,
                period=self.config.get("bb_period", 20),
                stddev=self.config.get("bb_stddev", 2),
                upper=self.config.get("bb_upper_threshold", 0.8),
                lower=self.config.get("bb_lower_threshold", 0.2),
            ):
                parts["BB"] = 1

        score = sum(parts.values())
        return score, parts

    def send_alert(self, symbol, timeframe, direction, rsi_value, price,
                   actual_symbol=None, pivot_info=None,
                   publish_to_feed=True, suppress_reason=None,
                   closes=None, highs=None, lows=None):
        # The cooldown only throttles published (actionable) alerts. A suppressed signal
        # must not consume it, or it could block a later trend-aligned publish of the same
        # symbol/timeframe/direction within the cooldown window.
        if publish_to_feed and not self.should_alert(symbol, timeframe, direction):
            return
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        display_symbol = actual_symbol if actual_symbol else symbol
        
        pivot_str = ""
        pivot_level = None
        pivot_distance = None
        
        if pivot_info and pivot_info.get("nearest_level"):
            pivot_level = pivot_info['nearest_level']
            pivot_distance = round(pivot_info['distance'], 2)
            pivot_str = f" | 📍 At {pivot_level} ({pivot_distance}%)"

        score, score_parts = self._confluence_score(
            direction, rsi_value, pivot_level, pivot_distance,
            closes=closes, highs=highs, lows=lows
        )
        score_breakdown = (
            f"RSI:{score_parts['RSI']} pivot:{score_parts['pivot']} "
            f"dist:{score_parts['dist']} MACD:{score_parts['MACD']} BB:{score_parts['BB']}"
        )

        alert_record = {
            "timestamp": timestamp,
            "symbol": display_symbol,
            "timeframe": timeframe,
            "direction": direction,
            "rsi": round(rsi_value, 2),
            "price": price,
            "pivot_level": pivot_level,
            "pivot_distance": pivot_distance,
            "confidence": score
        }
        
        # Feed gate: only trend-aligned signals reach rsi_alerts.json (dashboard + DoochyBot).
        # Suppressed signals are still printed and logged for diagnostics, just not published.
        if publish_to_feed:
            self.alert_history.append(alert_record)
            if len(self.alert_history) > 1000:
                self.alert_history.pop(0)

            # Write immediately using the new method
            self.append_alert_immediately(alert_record)

        suppress_tag = "" if publish_to_feed else f"  ⛔ SUPPRESSED ({suppress_reason})"
        conf_str = f" | confidence={score} ({score_breakdown})"
        if direction == "buy":
            message = f"[{timestamp}] 🔵 BUY ZONE - {display_symbol} {timeframe} | RSI: {rsi_value:.2f} | Price: {price}{pivot_str}{conf_str}{suppress_tag}"
        else:
            message = f"[{timestamp}] 🔴 SELL ZONE - {display_symbol} {timeframe} | RSI: {rsi_value:.2f} | Price: {price}{pivot_str}{conf_str}{suppress_tag}"

        print(message)

        if self.config["log_to_file"]:
            with open(self.config["log_file"], "a") as f:
                f.write(message + "\n")

        if self.config["enable_audio"] and publish_to_feed:
            play_beep(direction)

# ============================================================
# RSI CALCULATION
# ============================================================

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    
    series = pd.Series(prices)
    delta = series.diff()
    
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi.iloc[-1]

# ============================================================
# CONFIDENCE BOOSTERS (MACD DIVERGENCE + BOLLINGER %B)
# ============================================================
# These are confidence-only helpers: they return True/False to award +1 each,
# and they NEVER raise. Anything they can't compute (too little data, mismatched
# arrays, zero variance) returns False silently so the scanner keeps running.

def _ema(values, period):
    """Exponential moving average, returned as a list the same length as `values`.

    Warmup positions (before `period` candles exist) are None. The seed is the SMA
    of the first `period` values, then standard EMA smoothing. Manual implementation
    so no external indicator library is required (matches the project's RSI approach).
    """
    if not values or len(values) < period or period < 1:
        return None
    k = 2 / (period + 1)
    ema = [None] * len(values)
    seed = sum(values[:period]) / period
    ema[period - 1] = seed
    for i in range(period, len(values)):
        ema[i] = values[i] * k + ema[i - 1] * (1 - k)
    return ema


def _macd_divergence(closes, highs, lows, direction, lookback=5,
                     fast=12, slow=26, signal=9):
    """Detect MACD-vs-price divergence over the last `lookback` candles.

    MACD line = EMA(fast) - EMA(slow) on closes (signal kept for sizing the warmup).
    The lookback window is split into an older reference half and a recent half:

      Bearish (confirms SELL): recent high > older high, but recent MACD < older MACD
                               (price climbing while momentum weakens)
      Bullish (confirms BUY):  recent low < older low, but recent MACD > older MACD
                               (price falling while momentum quietly strengthens)

    Returns True only when divergence aligns with `direction`. Returns False silently
    on any shortfall of data — never raises, never warns.
    """
    try:
        if not closes or highs is None or lows is None:
            return False
        n = len(closes)
        if len(highs) != n or len(lows) != n:
            return False
        # Enough candles for EMA warmup plus a full lookback window.
        if n < slow + signal + lookback:
            return False

        ema_fast = _ema(closes, fast)
        ema_slow = _ema(closes, slow)
        if ema_fast is None or ema_slow is None:
            return False
        macd_line = [
            (ema_fast[i] - ema_slow[i])
            if (ema_fast[i] is not None and ema_slow[i] is not None) else None
            for i in range(n)
        ]

        window = list(range(n - lookback, n))
        if any(macd_line[i] is None for i in window):
            return False

        # Split the lookback window: older reference vs recent peak/trough.
        recent_len = max(1, lookback // 2)
        recent = window[-recent_len:]
        older = window[:-recent_len]
        if not older:
            return False

        if direction == "sell":
            r_idx = max(recent, key=lambda i: highs[i])
            o_idx = max(older, key=lambda i: highs[i])
            price_higher_high = highs[r_idx] > highs[o_idx]
            macd_lower_high = macd_line[r_idx] < macd_line[o_idx]
            return bool(price_higher_high and macd_lower_high)

        if direction == "buy":
            r_idx = min(recent, key=lambda i: lows[i])
            o_idx = min(older, key=lambda i: lows[i])
            price_lower_low = lows[r_idx] < lows[o_idx]
            macd_higher_low = macd_line[r_idx] > macd_line[o_idx]
            return bool(price_lower_low and macd_higher_low)

        return False
    except Exception:
        return False


def _bb_extreme(closes, direction, period=20, stddev=2, upper=0.8, lower=0.2):
    """Check whether the latest close sits at a Bollinger Bands %B extreme.

    %B = (close - lower_band) / (upper_band - lower_band), where the bands are
    SMA(period) ± stddev * population standard deviation over the last `period` closes.

      BUY  confirmed when %B < `lower` (near the lower band — statistically cheap)
      SELL confirmed when %B > `upper` (near the upper band — statistically expensive)

    Returns False silently when there isn't enough data or the band has zero width.
    """
    try:
        if not closes or len(closes) < period or period < 1:
            return False
        window = closes[-period:]
        mid = sum(window) / period
        variance = sum((c - mid) ** 2 for c in window) / period
        sd = variance ** 0.5
        if sd == 0:
            return False
        upper_band = mid + stddev * sd
        lower_band = mid - stddev * sd
        band_width = upper_band - lower_band
        if band_width == 0:
            return False
        pct_b = (closes[-1] - lower_band) / band_width
        if direction == "buy":
            return pct_b < lower
        if direction == "sell":
            return pct_b > upper
        return False
    except Exception:
        return False

# ============================================================
# EXCHANGE CLIENT - SUPPORTS MULTIPLE EXCHANGES
# ============================================================

class ExchangeClient:
    def __init__(self, exchange_name, config):
        self.config = config
        self.exchange = self._create_exchange(exchange_name)
        self.symbol_cache = {}
        self.pivot_cache = {}
        self.last_pivot_date = {}
        
    def _create_exchange(self, name):
        """Create exchange instance with appropriate settings"""
        exchange_map = {
            "binance": ccxt.binance,
            "binanceusdm": ccxt.binanceusdm,  # USDT-M Futures (XAU/USDT, XAG/USDT)
            "binancecoinm": ccxt.binancecoinm,  # COIN-M Futures
            "kraken": ccxt.kraken,
            "krakenfutures": ccxt.krakenfutures,
            "bybit": ccxt.bybit,
            "okx": ccxt.okx,
            "coinbase": ccxt.coinbase,
        }
        
        if name not in exchange_map:
            raise ValueError(f"Unsupported exchange: {name}. Options: {list(exchange_map.keys())}")
        
        # Configure based on exchange type
        options = {'enableRateLimit': True}
        
        if name == "binanceusdm":
            options['defaultType'] = 'future'
        elif name == "binancecoinm":
            options['defaultType'] = 'future'
        elif name == "krakenfutures":
            options['defaultType'] = 'future'
        elif name == "bybit":
            options['defaultType'] = 'linear'  # USDT perpetual
        
        exchange = exchange_map[name](options)
        
        # Print exchange info
        print(f"✅ Connected to {exchange.name} ({exchange.options.get('defaultType', 'spot')})")
        
        return exchange
    
    def get_daily_pivots(self, symbol, actual_symbol):
        """Get daily pivot levels for a symbol"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        if symbol in self.pivot_cache and self.last_pivot_date.get(symbol) == today:
            return self.pivot_cache[symbol]
        
        try:
            ohlcv = self.exchange.fetch_ohlcv(actual_symbol, timeframe="1d", limit=2)
            if ohlcv and len(ohlcv) >= 2:
                yesterday = ohlcv[-2]
                high = yesterday[2]
                low = yesterday[3]
                close = yesterday[4]
                
                pivots = PivotCalculator.calculate_pivots(high, low, close)
                self.pivot_cache[symbol] = pivots
                self.last_pivot_date[symbol] = today
                return pivots
        except Exception as e:
            pass
        
        return None
    
    def get_or_discover_symbol(self, original_symbol, timeframe, limit):
        if '/' not in original_symbol:
            return original_symbol, False
        
        base, quote = original_symbol.split('/')
        
        if base in self.symbol_cache:
            cached_data = self.symbol_cache[base]
            return cached_data["actual_symbol"], not cached_data.get("notified", False)
        
        attempts = []
        if self.config.get("try_usdt_first", True):
            if quote != "USDT":
                attempts.append(("USDT", f"{base}/USDT"))
            attempts.append((quote, original_symbol))
            if self.config.get("try_usd_fallback", True) and quote != "USD":
                attempts.append(("USD", f"{base}/USD"))
        else:
            attempts.append((quote, original_symbol))
            alt_quote = "USD" if quote == "USDT" else "USDT"
            if self.config.get("try_usd_fallback", True):
                attempts.append((alt_quote, f"{base}/{alt_quote}"))
        
        for attempt_quote, attempt_symbol in attempts:
            try:
                ohlcv = self.exchange.fetch_ohlcv(attempt_symbol, timeframe=timeframe, limit=limit)
                if ohlcv and len(ohlcv) > 0:
                    self.symbol_cache[base] = {
                        "actual_symbol": attempt_symbol,
                        "notified": False
                    }
                    return attempt_symbol, True
            except:
                continue
        
        self.symbol_cache[base] = {
            "actual_symbol": original_symbol,
            "notified": True
        }
        return original_symbol, False
    
    def mark_notified(self, original_symbol):
        base = original_symbol.split('/')[0] if '/' in original_symbol else original_symbol
        if base in self.symbol_cache:
            self.symbol_cache[base]["notified"] = True
    
    def fetch_ohlcv_with_fallback(self, original_symbol, timeframe, limit=100):
        actual_symbol, should_notify = self.get_or_discover_symbol(original_symbol, timeframe, limit)
        
        if should_notify and actual_symbol != original_symbol:
            print(f"  ℹ️  {original_symbol} → using {actual_symbol}")
            self.mark_notified(original_symbol)
        
        try:
            ohlcv = self.exchange.fetch_ohlcv(actual_symbol, timeframe=timeframe, limit=limit)
            if ohlcv and len(ohlcv) > 0:
                closes = [candle[4] for candle in ohlcv]
                highs = [candle[2] for candle in ohlcv]
                lows = [candle[3] for candle in ohlcv]
                current_price = closes[-1] if closes else None
                return {
                    "prices": closes,
                    "highs": highs,
                    "lows": lows,
                    "current_price": current_price,
                    "actual_symbol": actual_symbol
                }
        except Exception as e:
            pass

        return None

# ============================================================
# OHLC BRIDGE CLIENT (cTrader indices/commodities)
# ============================================================

class BridgeClient:
    """Data source backed by the local OHLC bridge (cTrader).

    Implements only the subset of ExchangeClient's interface that RSIBot uses
    (fetch_ohlcv_with_fallback, get_daily_pivots) so it can be dropped in for the
    bridge-routed symbols. Pure data fetching — no signal logic. The bridge
    returns JSON: {closes, highs, lows, opens, volumes, current_price}.
    """

    def __init__(self, config):
        self.config = config
        self.base_url = config.get("bridge_url", "http://localhost:9008").rstrip("/")
        self.pivot_cache = {}
        self.last_pivot_date = {}

    def _get(self, symbol, timeframe, count):
        try:
            resp = requests.get(
                f"{self.base_url}/ohlc",
                params={"symbol": symbol, "timeframe": timeframe, "count": count},
                timeout=10,
            )
            if resp.status_code != 200:
                return None
            return resp.json()
        except Exception:
            return None

    def fetch_ohlcv_with_fallback(self, original_symbol, timeframe, limit=100):
        data = self._get(original_symbol, timeframe, limit)
        if not data:
            return None
        closes = data.get("closes") or []
        if not closes:
            return None
        return {
            "prices": closes,
            "highs": data.get("highs") or [],
            "lows": data.get("lows") or [],
            "current_price": data.get("current_price", closes[-1]),
            "actual_symbol": original_symbol,
        }

    def get_daily_pivots(self, symbol, actual_symbol):
        """Daily pivots from the bridge's 1d candles (yesterday's H/L/C)."""
        today = datetime.now().strftime("%Y-%m-%d")
        if symbol in self.pivot_cache and self.last_pivot_date.get(symbol) == today:
            return self.pivot_cache[symbol]

        data = self._get(actual_symbol, "1d", 2)
        if not data:
            return None

        highs = data.get("highs") or []
        lows = data.get("lows") or []
        closes = data.get("closes") or []
        if len(highs) >= 2 and len(lows) >= 2 and len(closes) >= 2:
            pivots = PivotCalculator.calculate_pivots(highs[-2], lows[-2], closes[-2])
            self.pivot_cache[symbol] = pivots
            self.last_pivot_date[symbol] = today
            return pivots

        return None

# ============================================================
# MULTI-SOURCE ROUTER
# ============================================================

class MultiSourceClient:
    """Routes each symbol to the right data source: bridge symbols to the OHLC
    bridge, everything else to the configured ccxt exchange. Exposes the same
    interface RSIBot calls, so the scan loop stays source-agnostic.
    """

    def __init__(self, config):
        self.config = config
        self.exchange_client = ExchangeClient(config["exchange"], config)
        if config.get("bridge_enabled"):
            self.bridge_symbols = set(config.get("bridge_symbols", []))
        else:
            self.bridge_symbols = set()
        self.bridge_client = BridgeClient(config) if self.bridge_symbols else None

    def _client_for(self, symbol):
        if symbol in self.bridge_symbols and self.bridge_client is not None:
            return self.bridge_client
        return self.exchange_client

    def fetch_ohlcv_with_fallback(self, original_symbol, timeframe, limit=100):
        return self._client_for(original_symbol).fetch_ohlcv_with_fallback(
            original_symbol, timeframe, limit
        )

    def get_daily_pivots(self, symbol, actual_symbol):
        return self._client_for(symbol).get_daily_pivots(symbol, actual_symbol)

# ============================================================
# MAIN BOT
# ============================================================

class RSIBot:
    def __init__(self, config):
        self.config = config
        self.exchange = MultiSourceClient(config)
        self.alert_manager = AlertManager(config)
        self.last_rsi = {}

    def _timeframes_for(self, symbol):
        """Bridge-routed symbols scan their own timeframes (1d); all others use the
        global timeframe list. Keeps indices off the intraday frames the bridge can't
        serve, without touching the scan logic itself.
        """
        if self.config.get("bridge_enabled") and symbol in set(self.config.get("bridge_symbols", [])):
            return self.config.get("bridge_timeframes", ["1d"])
        return self.config["timeframes"]

    @staticmethod
    def _series_trend(prices, lookback):
        """Simple price-comparison trend: compare latest close to the one `lookback` candles ago.

        Returns 'up', 'down', or 'flat'. No indicator, no extra fetch — just the data
        MiniSig already holds for this series.
        """
        if not prices or lookback < 1 or len(prices) <= lookback:
            return "flat"
        now = prices[-1]
        past = prices[-1 - lookback]
        if now > past:
            return "up"
        if now < past:
            return "down"
        return "flat"

    def _trend_filter_ok(self, direction, tf_data):
        """Block signals that fight the higher-timeframe trend.

        Uses the 1H (short-term) and 4H (main) close series already fetched this cycle.
        BUY is blocked if either series is trending down; SELL if either is trending up.
        Flat/missing data passes (fail-open). Returns (ok, reason).
        """
        if not self.config.get("trend_filter_enabled", True):
            return True, None

        d1 = tf_data.get("1h")
        d4 = tf_data.get("4h")
        t1 = self._series_trend(d1["prices"], self.config.get("trend_lookback_1h", 1)) if d1 else "flat"
        t4 = self._series_trend(d4["prices"], self.config.get("trend_lookback_4h", 1)) if d4 else "flat"

        if direction == "buy" and ("down" in (t1, t4)):
            return False, f"trend 1h={t1}/4h={t4}"
        if direction == "sell" and ("up" in (t1, t4)):
            return False, f"trend 1h={t1}/4h={t4}"
        return True, None

    def determine_trend(self, prices_4h):
        """Classify the 4H trend (uptrend/downtrend/ranging/neutral) for RSI-zone shaping.

        Uses the 4H close series already fetched this cycle — no extra request.
        """
        try:
            if not prices_4h or len(prices_4h) < 20:
                return "neutral"

            prices = prices_4h

            # Simple trend detection using moving averages
            sma_short = sum(prices[-10:]) / 10
            sma_long = sum(prices[-20:]) / 20
            
            # Check slope of recent prices
            recent_slope = (prices[-1] - prices[-5]) / prices[-5] * 100
            
            # Calculate ADX or simple volatility
            price_range = (max(prices[-10:]) - min(prices[-10:])) / min(prices[-10:]) * 100
            
            if sma_short > sma_long and recent_slope > 0.1:
                return "uptrend"
            elif sma_short < sma_long and recent_slope < -0.1:
                return "downtrend"
            elif price_range < 2.0:  # Less than 2% range = ranging
                return "ranging"
            else:
                return "neutral"
        except:
            return "neutral"
    
    def check_rsi_zone(self, rsi_value, trend_direction="neutral"):
        """
        Enhanced RSI zone detection with trend context
        
        For trending markets:
        - RSI 40-50 = buy zone (healthy pullback in uptrend)
        - RSI 50-60 = sell zone (healthy bounce in downtrend)
        - RSI > 70 = take profit (not sell)
        - RSI < 30 = warning (trend may be failing)
        
        For ranging markets:
        - RSI > 70 = sell signal (reversal)
        - RSI < 30 = buy signal (reversal)
        """
        
        # Original zone definitions
        buy_zone = (self.config["buy_zone_low"] <= rsi_value <= self.config["buy_zone_high"])
        sell_zone = (self.config["sell_zone_low"] <= rsi_value <= self.config["sell_zone_high"])
        
        # Extreme zones
        extreme_overbought = rsi_value > 70
        extreme_oversold = rsi_value < 30
        
        # Trend-following logic
        if trend_direction == "uptrend":
            if extreme_overbought:
                return "take_profit_buy"  # Don't sell, just take profits on longs
            elif buy_zone:
                return "buy"
            elif rsi_value > 60 and rsi_value <= 70:
                return "momentum_buy"  # Strong momentum, can add to position
            elif extreme_oversold:
                return "warning"  # Trend may be failing, be cautious
            else:
                return None
            
        elif trend_direction == "downtrend":
            if extreme_oversold:
                return "take_profit_sell"  # Don't buy, just cover shorts
            elif sell_zone:
                return "sell"
            elif rsi_value < 40 and rsi_value >= 30:
                return "momentum_sell"  # Strong momentum down, can add to short
            elif buy_zone:
                return "warning"  # Don't buy in downtrend - wait for better setup
            elif extreme_overbought:
                return "warning"  # RSI > 70 in downtrend - trend may be failing
            else:
                return None
                
        elif trend_direction == "ranging":
            # In ranging markets, extremes become valid reversal signals
            if extreme_overbought:
                return "sell"
            elif extreme_oversold:
                return "buy"
            elif buy_zone:
                return "buy_cautious"  # Valid but less strong in ranging
            elif sell_zone:
                return "sell_cautious"
            else:
                return None
        
        # Neutral or no clear trend
        if buy_zone:
            return "buy"
        elif sell_zone:
            return "sell"
        else:
            return None
    
    def get_state_key(self, symbol, timeframe):
        return f"{symbol}_{timeframe}"
    
    def should_alert_state_change(self, key, new_zone):
        last_zone = self.last_rsi.get(key)
        
        if new_zone is not None and new_zone != last_zone:
            self.last_rsi[key] = new_zone
            return True
        elif new_zone is None:
            self.last_rsi[key] = None
        
        return False
    
    def check_pivot_alignment(self, symbol, actual_symbol, current_price, direction):
        if not self.config["enable_pivot_filter"]:
            return None, True
        
        pivots = self.exchange.get_daily_pivots(symbol, actual_symbol)
        if not pivots:
            return None, True
        
        proximity = self.config["pivot_proximity_percent"]
        
        if direction == "buy":
            favorable_levels = ["PP", "S1", "S2"]
            for level in favorable_levels:
                level_price = pivots.get(level)
                if level_price and PivotCalculator.is_near_level(current_price, level_price, proximity):
                    distance = abs(current_price - level_price) / current_price * 100
                    return {"nearest_level": level, "distance": distance, "level_price": level_price}, True
        
        elif direction == "sell":
            favorable_levels = ["PP", "R1", "R2"]
            for level in favorable_levels:
                level_price = pivots.get(level)
                if level_price and PivotCalculator.is_near_level(current_price, level_price, proximity):
                    distance = abs(current_price - level_price) / current_price * 100
                    return {"nearest_level": level, "distance": distance, "level_price": level_price}, True
        
        nearest, distance = PivotCalculator.get_nearest_level(current_price, pivots, proximity)
        if nearest:
            level_price = pivots.get(nearest)
            return {"nearest_level": nearest, "distance": distance, "level_price": level_price}, True
        
        return None, False
    
    def run_once(self):
        print(f"\n{'='*60}")
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking {len(self.config['symbols'])} symbols")
        print(f"{'='*60}")
        
        for original_symbol in self.config["symbols"]:
            # Bridge symbols (indices) scan 1d only; everything else scans the global list.
            timeframes = self._timeframes_for(original_symbol)

            # Fetch every timeframe once up front so the 1H/4H close series are in memory
            # for the trend filter, no matter which timeframe fires.
            tf_data = {}
            for timeframe in timeframes:
                tf_data[timeframe] = self.exchange.fetch_ohlcv_with_fallback(
                    original_symbol, timeframe, self.config["candle_limit"]
                )

            # 4H trend classification for RSI-zone shaping — reuses the cached 4H series.
            trend = self.determine_trend(
                tf_data["4h"]["prices"] if tf_data.get("4h") else None
            )

            for timeframe in timeframes:
                result = tf_data.get(timeframe)

                if result is None or len(result["prices"]) < self.config["rsi_period"] + 1:
                    continue

                rsi = calculate_rsi(result["prices"], self.config["rsi_period"])
                
                # Skip invalid RSI values
                if rsi is None or rsi <= 0.01 or rsi >= 99.99:
                    print(f"  ⚠️ {original_symbol} {timeframe} | Invalid RSI: {rsi}")
                    continue
    
                # Pass trend to zone detection
                zone = self.check_rsi_zone(rsi, trend)
                key = self.get_state_key(original_symbol, timeframe)
                
                # Skip warning signals (just for monitoring, not alerts)
                if zone == "warning":
                    continue
                
                pivot_info = None
                pivot_allowed = True
                
                # Only check pivot alignment for primary buy/sell signals
                if zone in ["buy", "sell"] and self.config["enable_pivot_filter"]:
                    pivot_info, pivot_allowed = self.check_pivot_alignment(
                        original_symbol, result["actual_symbol"], 
                        result["current_price"], zone
                    )
                
                # Handle different signal types
                if pivot_allowed:
                    if zone in ["buy", "buy_cautious", "momentum_buy"] and self.should_alert_state_change(key, zone):
                        publish, reason = self._trend_filter_ok("buy", tf_data)
                        self.alert_manager.send_alert(
                            symbol=original_symbol,
                            timeframe=timeframe,
                            direction="buy",
                            rsi_value=rsi,
                            price=result["current_price"],
                            actual_symbol=result["actual_symbol"],
                            pivot_info=pivot_info,
                            publish_to_feed=publish,
                            suppress_reason=reason,
                            closes=result["prices"],
                            highs=result.get("highs"),
                            lows=result.get("lows"),
                        )
                    elif zone in ["sell", "sell_cautious", "momentum_sell"] and self.should_alert_state_change(key, zone):
                        publish, reason = self._trend_filter_ok("sell", tf_data)
                        self.alert_manager.send_alert(
                            symbol=original_symbol,
                            timeframe=timeframe,
                            direction="sell",
                            rsi_value=rsi,
                            price=result["current_price"],
                            actual_symbol=result["actual_symbol"],
                            pivot_info=pivot_info,
                            publish_to_feed=publish,
                            suppress_reason=reason,
                            closes=result["prices"],
                            highs=result.get("highs"),
                            lows=result.get("lows"),
                        )
                    elif zone in ["take_profit_buy", "take_profit_sell"]:
                        # Check cooldown before printing take profit
                        if self.alert_manager.should_alert_take_profit(original_symbol, timeframe):
                            profit_direction = "buy" if zone == "take_profit_buy" else "sell"
                            print(f"  💰 TAKE PROFIT: {original_symbol} {timeframe} | RSI: {rsi:.2f} | Price: {result['current_price']}")
                
                # Display formatting
                zone_display = {
                    "buy": "BUY",
                    "sell": "SELL",
                    "buy_cautious": "BUY-C",
                    "sell_cautious": "SELL-C",
                    "momentum_buy": "MOM↑",
                    "momentum_sell": "MOM↓",
                    "take_profit_buy": "TP-B",
                    "take_profit_sell": "TP-S",
                    "warning": "WARN",
                    None: "---"
                }.get(zone, "---")
                
                display = result["actual_symbol"] if result["actual_symbol"] != original_symbol else original_symbol
                
                pivot_display = ""
                if pivot_info and pivot_info.get("nearest_level"):
                    pivot_display = f" | 📍 {pivot_info['nearest_level']}"
                
                trend_symbol = "📈" if trend == "uptrend" else "📉" if trend == "downtrend" else "➖"
                print(f"  {trend_symbol} {display:12} {timeframe:4} | RSI: {rsi:6.2f} | Zone: {zone_display:6} | Price: {result['current_price']}{pivot_display}")
        
        print(f"Next check in {self.config['check_interval']} seconds...")
    
    def run(self):
        print("\n" + "="*60)
        print("MULTI-EXCHANGE RSI ALERT BOT (with Pivot/SR Integration)")
        print("ENHANCED: Trend Detection + Extreme RSI Handling")
        print("="*60)
        print(f"Exchange: {self.config['exchange']}")
        print(f"Symbols: {len(self.config['symbols'])} pairs configured")
        print(f"Timeframes: {', '.join(self.config['timeframes'])}")
        print(f"Buy Zone: {self.config['buy_zone_low']} - {self.config['buy_zone_high']}")
        print(f"Sell Zone: {self.config['sell_zone_low']} - {self.config['sell_zone_high']}")
        print(f"Pivot Filter: {'ON' if self.config['enable_pivot_filter'] else 'OFF'}")
        print(f"Pivot Proximity: {self.config['pivot_proximity_percent']}%")
        print(f"Check Interval: {self.config['check_interval']} seconds")
        print(f"Audio Alerts: {'ON' if self.config['enable_audio'] else 'OFF'}")
        print("="*60)
        print("\nSignal Types:")
        print("  📈 Uptrend: BUY (40-50) | MOM↑ (60-70) | TP-B (>70)")
        print("  📉 Downtrend: SELL (50-60) | MOM↓ (30-40) | TP-S (<30)")
        print("  ➖ Ranging: BUY (<30) | SELL (>70)")
        print("="*60)
        print("\nBot running. Press Ctrl+C to stop.\n")
        
        try:
            while True:
                self.run_once()
                time.sleep(self.config["check_interval"])
        except KeyboardInterrupt:
            print("\n\nBot stopped by user.")

# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    config_file = Path("config.json")
    if config_file.exists():
        with open(config_file, "r") as f:
            user_config = json.load(f)
            CONFIG.update(user_config)
    
    bot = RSIBot(CONFIG)
    bot.run()
