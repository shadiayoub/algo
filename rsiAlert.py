#!/usr/bin/env python3
"""
Kraken RSI Alert Bot - No external audio libraries required
Works with winsound (Windows) or console beep (Linux/Mac)
Automatically tries USD if USDT pair is not found
"""

import ccxt
import pandas as pd
import time
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# ============================================================
# AUDIO SETUP - Platform specific, no extra packages needed
# ============================================================

def play_beep(direction):
    """Play different beeps for buy vs sell"""
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
    # Exchange (kraken, binance, bybit, coinbase, okx)
    "exchange": "kraken",
    
    # Symbols to monitor - Can be USD or USDT format
    "symbols": [
        "AAVE/USD",
        "ADA/USDT",
       "AIXBT/USDT",
        "ALGO/USDT",
        "APT/USDT",
        "ARB/USDT",
        "ASTER/USDT",
        "ATOM/USDT",
        "AVAX/USDT",
        "BCH/USDT",
        "BNB/USDT",
        "BONK/USDT",
        "BTC/USDT",
        "CRV/USDT",
        "DOGE/USDT",
        "DOT/USDT",
        "ETC/USDT",
        "ETH/USDT",
        "FARTCOIN/USDT",
        "FIL/USDT",
        "FLOKI/USDT",
        "GRASS/USDT",
        "HBAR/USDT",
        "HYPE/USDT",
        "INJ/USDT",
        "IP/USDT",
        "JTO/USDT",
        "JUP/USDT",
        "KAITO/USDT",
        "LDO/USDT",
        "LINK/USDT",
        "LIT/USDT",
        "LTC/USDT",
        "MOODENG/USDT",
        "NEAR/USDT",
        "ONDO/USDT",
        "OP/USDT",
        "ORDI/USDT",
        "PENGU/USDT",
        "PEPE/USDT",
        "PNUT/USDT",
        "POL/USDT",
        "POPCAT/USDT",
        "PUMP/USDT",
        "RENDER/USDT",
        "S/USDT",
        "SHIB/USDT",
        "SOL/USDT",
        "STX/USDT",
        "SUI/USDT",
        "TAO/USDT",
        "TIA/USDT",
        "TON/USDT",
        "TRUMP/USDT",
        "TRX/USDT",
        "UNI/USDT",
        "VIRTUAL/USDT",
        "WIF/USDT",
        "WLD/USDT",
        "XPL/USDT",
        "XRP/USDT",
        "ZEC/USDT"
    ],
    
    # Timeframes to monitor
    "timeframes": ["5m", "15m", "1h", "4h"],
    
    # RSI Settings
    "rsi_period": 7,
    
    # Strategy Zones
    "buy_zone_low": 40,
    "buy_zone_high": 50,
    "sell_zone_low": 50,
    "sell_zone_high": 60,
    
    # Check interval in seconds
    "check_interval": 60,
    
    # Audio Settings
    "enable_audio": True,
    "audio_cooldown_seconds": 300,
    
    # Logging
    "log_to_file": True,
    "log_file": "rsi_alerts.log",
    
    # Data
    "candle_limit": 100,
    
    # Symbol Fallback Settings
    "try_usdt_first": True,
    "try_usd_fallback": True,
}

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
        """Export alerts to JSON file for web display"""
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
    
    def send_alert(self, symbol, timeframe, direction, rsi_value, price, actual_symbol=None):
        if not self.should_alert(symbol, timeframe, direction):
            return
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        display_symbol = actual_symbol if actual_symbol else symbol
        
        # Create alert record
        alert_record = {
            "timestamp": timestamp,
            "symbol": display_symbol,
            "timeframe": timeframe,
            "direction": direction,
            "rsi": round(rsi_value, 2),
            "price": price
        }
        
        # Store in history (keep last 1000 alerts)
        self.alert_history.append(alert_record)
        if len(self.alert_history) > 1000:
            self.alert_history.pop(0)
        
        # Export to file
        self.export_alerts()
        
        # Console output
        if direction == "buy":
            message = f"[{timestamp}] 🔵 BUY ZONE - {display_symbol} {timeframe} | RSI: {rsi_value:.2f} | Price: {price}"
        else:
            message = f"[{timestamp}] 🔴 SELL ZONE - {display_symbol} {timeframe} | RSI: {rsi_value:.2f} | Price: {price}"
        
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
# EXCHANGE CLIENT WITH SYMBOL-LEVEL CACHING
# ============================================================

class ExchangeClient:
    def __init__(self, exchange_name, config):
        self.exchange_name = exchange_name
        self.config = config
        self.exchange = self._create_exchange(exchange_name)
        # Symbol-level cache: stores (actual_symbol, fallback_notified)
        self.symbol_cache = {}
        
    def _create_exchange(self, name):
        exchange_map = {
            "kraken": ccxt.kraken,
            "binance": ccxt.binance,
            "bybit": ccxt.bybit,
            "coinbase": ccxt.coinbase,
            "okx": ccxt.okx,
        }
        
        if name not in exchange_map:
            raise ValueError(f"Unsupported exchange: {name}")
        
        exchange = exchange_map[name]({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        
        return exchange
    
    def _try_symbol_format(self, base_symbol, quote, timeframe, limit):
        """Try a specific symbol format"""
        test_symbol = f"{base_symbol}/{quote}"
        try:
            ohlcv = self.exchange.fetch_ohlcv(test_symbol, timeframe=timeframe, limit=limit)
            if ohlcv and len(ohlcv) > 0:
                return test_symbol, ohlcv
        except:
            pass
        return None, None
    
    def get_or_discover_symbol(self, original_symbol, timeframe, limit):
        """
        Discover the correct symbol format once per symbol.
        Returns (actual_symbol, should_notify_fallback)
        """
        # Parse the original symbol
        if '/' not in original_symbol:
            return original_symbol, False
        
        base, quote = original_symbol.split('/')
        
        # Check cache first (symbol-level, not timeframe-level)
        if base in self.symbol_cache:
            cached_data = self.symbol_cache[base]
            # Return cached symbol and whether we've already notified
            return cached_data["actual_symbol"], not cached_data.get("notified", False)
        
        # Need to discover the correct format
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
        
        # Try each attempt
        for attempt_quote, attempt_symbol in attempts:
            try:
                ohlcv = self.exchange.fetch_ohlcv(attempt_symbol, timeframe=timeframe, limit=limit)
                if ohlcv and len(ohlcv) > 0:
                    # Cache the successful format
                    self.symbol_cache[base] = {
                        "actual_symbol": attempt_symbol,
                        "notified": False
                    }
                    # Return with notification flag = True (first time)
                    return attempt_symbol, True
            except Exception as e:
                continue
        
        # All attempts failed - cache the original and don't notify
        self.symbol_cache[base] = {
            "actual_symbol": original_symbol,
            "notified": True  # Already "notified" (no need to show error repeatedly)
        }
        return original_symbol, False
    
    def mark_notified(self, original_symbol):
        """Mark that fallback notification has been shown for this symbol"""
        base = original_symbol.split('/')[0] if '/' in original_symbol else original_symbol
        if base in self.symbol_cache:
            self.symbol_cache[base]["notified"] = True
    
    def fetch_ohlcv_with_fallback(self, original_symbol, timeframe, limit=100):
        """Fetch OHLCV with symbol discovery and single notification"""
        # Discover correct symbol format (once per symbol)
        actual_symbol, should_notify = self.get_or_discover_symbol(original_symbol, timeframe, limit)
        
        # Show notification only once per symbol
        if should_notify and actual_symbol != original_symbol:
            print(f"  ℹ️  {original_symbol} → using {actual_symbol}")
            self.mark_notified(original_symbol)
        
        # Fetch data
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
    
    def fetch_ohlcv(self, symbol, timeframe, limit=100):
        """Original method maintained for compatibility"""
        result = self.fetch_ohlcv_with_fallback(symbol, timeframe, limit)
        if result:
            return {
                "prices": result["prices"],
                "current_price": result["current_price"],
            }
        return None

# ============================================================
# MAIN BOT
# ============================================================

class KrakenRSIBot:
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
                
                if self.should_alert_state_change(key, zone):
                    self.alert_manager.send_alert(
                        symbol=original_symbol,
                        timeframe=timeframe,
                        direction=zone,
                        rsi_value=rsi,
                        price=result["current_price"],
                        actual_symbol=result["actual_symbol"]
                    )
                
                zone_str = zone.upper() if zone else "---"
                display = result["actual_symbol"] if result["actual_symbol"] != original_symbol else original_symbol
                print(f"  {display:12} {timeframe:4} | RSI: {rsi:6.2f} | Zone: {zone_str:4} | Price: {result['current_price']}")
        
        print(f"Next check in {self.config['check_interval']} seconds...")
    
    def run(self):
        print("\n" + "="*60)
        print("KRAKEN RSI ALERT BOT (with USD/USDT fallback)")
        print("="*60)
        print(f"Exchange: {self.config['exchange']}")
        print(f"Symbols: {len(self.config['symbols'])} pairs configured")
        print(f"Timeframes: {', '.join(self.config['timeframes'])}")
        print(f"Buy Zone: {self.config['buy_zone_low']} - {self.config['buy_zone_high']}")
        print(f"Sell Zone: {self.config['sell_zone_low']} - {self.config['sell_zone_high']}")
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
    
    bot = KrakenRSIBot(CONFIG)
    bot.run()
