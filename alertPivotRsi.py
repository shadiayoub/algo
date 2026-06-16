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
        "BONK/USDT:USDT",
        "BTC/USDT:USDT",
        "CRV/USDT:USDT",
        "DOGE/USDT:USDT",
        "DOT/USDT:USDT",
        "ETC/USDT:USDT",
        "ETH/USDT:USDT",
        "FARTCOIN/USDT:USDT",
        "FIL/USDT:USDT",
        "FLOKI/USDT:USDT",
        "GRASS/USDT:USDT",
        "HBAR/USDT:USDT",
        "HYPE/USDT:USDT",
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
        "POPCAT/USDT:USDT",
        "PUMP/USDT:USDT",
        "RENDER/USDT:USDT",
        "S/USDT:USDT",
        "SHIB/USDT:USDT",
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
    
    def _confluence_score(self, direction, rsi_value, pivot_level, pivot_distance):
        """Score signal quality 0–4 based on RSI zone depth and pivot alignment.

        +2 if RSI is in the ideal zone (buy 40-50, sell 50-60)
        +1 if a pivot level is present
        +1 if pivot_distance < 0.5%
        """
        score = 0
        if direction == "buy" and self.config["buy_zone_low"] <= rsi_value <= self.config["buy_zone_high"]:
            score += 2
        elif direction == "sell" and self.config["sell_zone_low"] <= rsi_value <= self.config["sell_zone_high"]:
            score += 2
        if pivot_level is not None:
            score += 1
        if pivot_distance is not None and pivot_distance < 0.5:
            score += 1
        return score

    def send_alert(self, symbol, timeframe, direction, rsi_value, price,
                   actual_symbol=None, pivot_info=None,
                   publish_to_feed=True, suppress_reason=None):
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

        score = self._confluence_score(direction, rsi_value, pivot_level, pivot_distance)

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
        if direction == "buy":
            message = f"[{timestamp}] 🔵 BUY ZONE - {display_symbol} {timeframe} | RSI: {rsi_value:.2f} | Price: {price}{pivot_str}{suppress_tag}"
        else:
            message = f"[{timestamp}] 🔴 SELL ZONE - {display_symbol} {timeframe} | RSI: {rsi_value:.2f} | Price: {price}{pivot_str}{suppress_tag}"

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
                current_price = closes[-1] if closes else None
                return {
                    "prices": closes,
                    "current_price": current_price,
                    "actual_symbol": actual_symbol
                }
        except Exception as e:
            pass
        
        return None

# ============================================================
# MAIN BOT
# ============================================================

class RSIBot:
    def __init__(self, config):
        self.config = config
        self.exchange = ExchangeClient(config["exchange"], config)
        self.alert_manager = AlertManager(config)
        self.last_rsi = {}

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
            # Fetch every timeframe once up front so the 1H/4H close series are in memory
            # for the trend filter, no matter which timeframe fires.
            tf_data = {}
            for timeframe in self.config["timeframes"]:
                tf_data[timeframe] = self.exchange.fetch_ohlcv_with_fallback(
                    original_symbol, timeframe, self.config["candle_limit"]
                )

            # 4H trend classification for RSI-zone shaping — reuses the cached 4H series.
            trend = self.determine_trend(
                tf_data["4h"]["prices"] if tf_data.get("4h") else None
            )

            for timeframe in self.config["timeframes"]:
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
