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
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "BNB/USDT:USDT",
    "ADA/USDT:USDT",
    "DOT/USDT:USDT",
    "SOL/USDT:USDT",
    "XRP/USDT:USDT",
    "AVAX/USDT:USDT",
    "DOGE/USDT:USDT",
    "LINK/USDT:USDT",
    "MATIC/USDT:USDT",
    "NEAR/USDT:USDT",
    "ATOM/USDT:USDT",
    "LTC/USDT:USDT",
    "BCH/USDT:USDT",
    "UNI/USDT:USDT",
    "ETC/USDT:USDT",
    "FIL/USDT:USDT",
    "APT/USDT:USDT",
    "ARB/USDT:USDT",
    "OP/USDT:USDT",
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
        
    def export_alerts(self):
        try:
            with open(self.alert_file, "w") as f:
                json.dump(self.alert_history, f, indent=2)
        except Exception as e:
            pass
    
    def should_alert(self, symbol, timeframe, direction):
        key = f"{symbol}_{timeframe}_{direction}"
        now = time.time()
        
        if key in self.last_alert:
            if now - self.last_alert[key] < self.config["audio_cooldown_seconds"]:
                return False
        
        self.last_alert[key] = now
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
        
        self.export_alerts()
        
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
        
    def check_rsi_zone(self, rsi_value):
        buy_zone = (self.config["buy_zone_low"] <= rsi_value <= self.config["buy_zone_high"])
        sell_zone = (self.config["sell_zone_low"] <= rsi_value <= self.config["sell_zone_high"])
        
        if buy_zone:
            return "buy"
        elif sell_zone:
            return "sell"
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
            for timeframe in self.config["timeframes"]:
                result = self.exchange.fetch_ohlcv_with_fallback(
                    original_symbol, timeframe, self.config["candle_limit"]
                )
                
                if result is None or len(result["prices"]) < self.config["rsi_period"] + 1:
                    continue
                
                rsi = calculate_rsi(result["prices"], self.config["rsi_period"])
                
                if rsi is None:
                    continue
                
                zone = self.check_rsi_zone(rsi)
                key = self.get_state_key(original_symbol, timeframe)
                
                pivot_info = None
                pivot_allowed = True
                
                if zone and self.config["enable_pivot_filter"]:
                    pivot_info, pivot_allowed = self.check_pivot_alignment(
                        original_symbol, result["actual_symbol"], 
                        result["current_price"], zone
                    )
                
                if self.should_alert_state_change(key, zone) and pivot_allowed:
                    self.alert_manager.send_alert(
                        symbol=original_symbol,
                        timeframe=timeframe,
                        direction=zone,
                        rsi_value=rsi,
                        price=result["current_price"],
                        actual_symbol=result["actual_symbol"],
                        pivot_info=pivot_info
                    )
                
                zone_str = zone.upper() if zone else "---"
                display = result["actual_symbol"] if result["actual_symbol"] != original_symbol else original_symbol
                
                pivot_display = ""
                if pivot_info and pivot_info.get("nearest_level"):
                    pivot_display = f" | 📍 {pivot_info['nearest_level']}"
                
                print(f"  {display:12} {timeframe:4} | RSI: {rsi:6.2f} | Zone: {zone_str:4} | Price: {result['current_price']}{pivot_display}")
        
        print(f"Next check in {self.config['check_interval']} seconds...")
    
    def run(self):
        print("\n" + "="*60)
        print("MULTI-EXCHANGE RSI ALERT BOT (with Pivot/SR Integration)")
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
