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
        "TRUMP/USDT:USDT",
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

    # DoochyBot Webhook Settings
    "enable_doochybot_webhook": True,
    "doochybot_webhook_url": "https://aprhunter.route07.com/webhook",
    "sl_buffer_percent": 0.25,
    "tp_buffer_percent": 0.15,
    "min_confidence_for_webhook": 3,

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
    
    def send_alert(self, symbol, timeframe, direction, rsi_value, price, 
                   actual_symbol=None, pivot_info=None):
        if not self.should_alert(symbol, timeframe, direction):
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
        
        alert_record = {
            "timestamp": timestamp,
            "symbol": display_symbol,
            "timeframe": timeframe,
            "direction": direction,
            "rsi": round(rsi_value, 2),
            "price": price,
            "pivot_level": pivot_level,
            "pivot_distance": pivot_distance
        }
        
        self.alert_history.append(alert_record)
        if len(self.alert_history) > 1000:
            self.alert_history.pop(0)
        
        # Write immediately using the new method
        self.append_alert_immediately(alert_record)
        
        if direction == "buy":
            message = f"[{timestamp}] 🔵 BUY ZONE - {display_symbol} {timeframe} | RSI: {rsi_value:.2f} | Price: {price}{pivot_str}"
        else:
            message = f"[{timestamp}] 🔴 SELL ZONE - {display_symbol} {timeframe} | RSI: {rsi_value:.2f} | Price: {price}{pivot_str}"
        
        print(message)
        
        if self.config["log_to_file"]:
            with open(self.config["log_file"], "a") as f:
                f.write(message + "\n")
        
        if self.config["enable_audio"]:
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
        self._webhook_last_sent = {}  # symbol → timestamp of last webhook

    def _format_symbol(self, symbol):
        """Convert exchange symbol to DoochyBot format (e.g. BTC/USDT:USDT → BTCUSD)."""
        s = symbol.split(":")[0]   # drop ":USDT" perpetual suffix
        s = s.replace("/", "")     # "BTC/USDT" → "BTCUSDT"
        if s.endswith("USDT"):
            s = s[:-4] + "USD"     # "BTCUSDT" → "BTCUSD"
        return s

    def _get_sl_tp_decimals(self, symbol, price):
        if "XAU" in symbol or "XAG" in symbol:
            return 2
        if price > 1000:
            return 0
        if price > 100:
            return 2
        if price > 1:
            return 4
        return 6

    def send_to_doochybot(self, alert_data, pivots):
        """Format a valid RSI+pivot signal and POST it to the DoochyBot webhook."""
        if not self.config.get("enable_doochybot_webhook", False):
            return

        symbol    = alert_data["symbol"]
        direction = alert_data["direction"]
        price     = alert_data["price"]
        rsi       = alert_data.get("rsi", 0)
        pivot_level = alert_data.get("pivot_level")

        # Step 1 — Validate signal quality
        if not pivot_level:
            return
        if direction not in ("buy", "sell"):
            return
        if direction == "buy" and not (35 <= rsi <= 55):
            return
        if direction == "sell" and not (45 <= rsi <= 65):
            return

        # Rate limit: one webhook per symbol per 5 minutes
        now = time.time()
        if now - self._webhook_last_sent.get(symbol, 0) < 300:
            return

        if not pivots:
            return

        # Step 2 — Find which two pivot levels price sits between
        level_names = ["R3", "R2", "R1", "PP", "S1", "S2", "S3"]
        level_pairs = [(n, pivots[n]) for n in level_names if pivots.get(n) is not None]
        level_pairs.sort(key=lambda x: x[1])  # ascending by price

        lower = None   # highest level at or below price
        upper = None   # lowest level above price

        for name, lp in level_pairs:
            if lp <= price:
                lower = (name, lp)
            elif upper is None:
                upper = (name, lp)

        # Edge cases: price outside all levels
        if lower is None and len(level_pairs) >= 2:
            lower, upper = level_pairs[0], level_pairs[1]
        elif upper is None and len(level_pairs) >= 2:
            lower, upper = level_pairs[-2], level_pairs[-1]

        if not lower or not upper:
            return

        lower_name, lower_price = lower
        upper_name, upper_price = upper

        # Step 3 — Calculate SL and TP
        sl_buf = self.config.get("sl_buffer_percent", 0.25) / 100
        tp_buf = self.config.get("tp_buffer_percent", 0.15) / 100

        if direction == "buy":
            sl = lower_price * (1 - sl_buf)
            tp = upper_price * (1 - tp_buf)
        else:
            sl = upper_price * (1 + sl_buf)
            tp = lower_price * (1 + tp_buf)

        decimals = self._get_sl_tp_decimals(symbol, price)
        sl = round(sl, decimals)
        tp = round(tp, decimals)

        # Step 4 — Format signal string
        doochybot_symbol = self._format_symbol(symbol)
        direction_str = "BUY" if direction == "buy" else "SELL"
        signal = f"{direction_str} {doochybot_symbol} SL={sl} TP={tp}"

        # Step 5 — POST to DoochyBot
        url = self.config.get("doochybot_webhook_url", "")
        if not url:
            return

        try:
            resp = requests.post(
                url,
                data=signal,
                headers={"Content-Type": "text/plain"},
                timeout=5
            )
            if resp.status_code < 300:
                print(f"  🚀 Webhook sent: {signal}")
                self._webhook_last_sent[symbol] = now
            else:
                print(f"  ❌ Webhook failed [{resp.status_code}]: {resp.text[:120]}")
        except Exception as e:
            print(f"  ❌ Webhook error: {e}")

    def determine_trend(self, symbol, timeframe="1h"):
        """Determine if market is trending up, down, or ranging based on higher timeframe"""
        try:
            # Fetch 20 candles of higher timeframe (1h or 4h)
            higher_tf = "1h" if timeframe == "5m" or timeframe == "15m" else "4h"
            result = self.exchange.fetch_ohlcv_with_fallback(
                symbol, higher_tf, 20
            )
            
            if result is None or len(result["prices"]) < 20:
                return "neutral"
            
            prices = result["prices"]
            
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
            # Determine trend for this symbol (using 1h timeframe)
            trend = self.determine_trend(original_symbol)
            
            for timeframe in self.config["timeframes"]:
                result = self.exchange.fetch_ohlcv_with_fallback(
                    original_symbol, timeframe, self.config["candle_limit"]
                )
                
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
                        self.alert_manager.send_alert(
                            symbol=original_symbol,
                            timeframe=timeframe,
                            direction="buy",
                            rsi_value=rsi,
                            price=result["current_price"],
                            actual_symbol=result["actual_symbol"],
                            pivot_info=pivot_info
                        )
                        if pivot_info and pivot_info.get("nearest_level"):
                            pivots = self.exchange.get_daily_pivots(
                                original_symbol, result["actual_symbol"]
                            )
                            self.send_to_doochybot({
                                "symbol": result["actual_symbol"],
                                "direction": "buy",
                                "price": result["current_price"],
                                "rsi": rsi,
                                "timeframe": timeframe,
                                "pivot_level": pivot_info["nearest_level"],
                            }, pivots)
                    elif zone in ["sell", "sell_cautious", "momentum_sell"] and self.should_alert_state_change(key, zone):
                        self.alert_manager.send_alert(
                            symbol=original_symbol,
                            timeframe=timeframe,
                            direction="sell",
                            rsi_value=rsi,
                            price=result["current_price"],
                            actual_symbol=result["actual_symbol"],
                            pivot_info=pivot_info
                        )
                        if pivot_info and pivot_info.get("nearest_level"):
                            pivots = self.exchange.get_daily_pivots(
                                original_symbol, result["actual_symbol"]
                            )
                            self.send_to_doochybot({
                                "symbol": result["actual_symbol"],
                                "direction": "sell",
                                "price": result["current_price"],
                                "rsi": rsi,
                                "timeframe": timeframe,
                                "pivot_level": pivot_info["nearest_level"],
                            }, pivots)
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
