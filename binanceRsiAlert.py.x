#!/usr/bin/env python3
"""
Binance Futures RSI Alert Bot
Monitors USDT-M perpetual futures including XAUUSDT (Gold) and XAGUSDT (Silver)
Strategy: Buy Zone 40-50 | Sell Zone 50-60
"""

import ccxt
import pandas as pd
import time
import json
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
    # Exchange - Binance Futures
    "exchange": "binanceusdm",  # binanceusdm = Binance USDT-M Futures
    "exchange_type": "futures",  # 'futures' for perpetual contracts
    
    # Symbols to monitor - Use 'USDT' suffix for USDT-M futures
    "symbols": [
        # Cryptocurrencies
        "BTC/USDT",
        "ETH/USDT",
        "BNB/USDT",
        #"LINK/USDT",
        #"CRV/USDT",
        # Precious Metals (Gold & Silver on Binance Futures)
        "XAU/USDT",  # Gold - tracks 1 troy ounce
        "XAG/USDT",  # Silver - tracks 1 troy ounce
    ],
    
    # Timeframes to monitor
    "timeframes": ["5m", "15m", "1h", "4h"],
    
    # RSI Settings
    "rsi_period": 14,
    
    # Strategy Zones (based on your decision matrix)
    "buy_zone_low": 40,
    "buy_zone_high": 50,
    "sell_zone_low": 50,
    "sell_zone_high": 60,
    
    # Higher Timeframe Filter (OPTIONAL - prevents alerts when HTF is overbought/oversold)
    "enable_htf_filter": False,  # Set to True to enable
    "htf_timeframe": "1h",
    "htf_max_rsi_for_buy": 70,   # Don't alert buy if HTF RSI > 70 (overbought)
    "htf_min_rsi_for_sell": 30,  # Don't alert sell if HTF RSI < 30 (oversold)
    
    # Check interval in seconds
    "check_interval": 60,
    
    # Audio Settings
    "enable_audio": True,
    "audio_cooldown_seconds": 300,  # Don't alert same symbol/timeframe more than once per 5 minutes
    
    # Logging
    "log_to_file": True,
    "log_file": "binance_futures_alerts.log",
    
    # Data
    "candle_limit": 100,
}

# ============================================================
# ALERT MANAGER
# ============================================================

class AlertManager:
    def __init__(self, config):
        self.config = config
        self.last_alert = {}
        self.last_rsi_state = {}  # Track RSI state per (symbol, timeframe)
        
    def should_alert(self, symbol, timeframe, direction):
        """Check cooldown to prevent spam"""
        key = f"{symbol}_{timeframe}_{direction}"
        now = time.time()
        
        if key in self.last_alert:
            if now - self.last_alert[key] < self.config["audio_cooldown_seconds"]:
                return False
        
        self.last_alert[key] = now
        return True
    
    def check_state_change(self, symbol, timeframe, new_zone):
        """Only alert when entering a zone, not while staying in it"""
        key = f"{symbol}_{timeframe}"
        old_zone = self.last_rsi_state.get(key)
        
        if new_zone is not None and new_zone != old_zone:
            self.last_rsi_state[key] = new_zone
            return True
        elif new_zone is None:
            self.last_rsi_state[key] = None
        
        return False
    
    def send_alert(self, symbol, timeframe, direction, rsi_value, price):
        """Send alert with beep and console message"""
        if not self.check_state_change(symbol, timeframe, direction):
            return
        
        if not self.should_alert(symbol, timeframe, direction):
            return
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Special note for XAU/XAG
        asset_note = ""
        if "XAU" in symbol:
            asset_note = " | Gold Futures - Check S1/PP for support"
        elif "XAG" in symbol:
            asset_note = " | Silver Futures - Check S1/PP for support"
        
        if direction == "buy":
            message = f"[{timestamp}] 🔵 BUY ZONE - {symbol} {timeframe} | RSI: {rsi_value:.2f} | Price: {price}{asset_note}"
        else:
            message = f"[{timestamp}] 🔴 SELL ZONE - {symbol} {timeframe} | RSI: {rsi_value:.2f} | Price: {price}{asset_note}"
        
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
    """Calculate RSI from a list of prices"""
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
# EXCHANGE CLIENT - BINANCE FUTURES
# ============================================================

class BinanceFuturesClient:
    def __init__(self, exchange_name):
        self.exchange_name = exchange_name
        self.exchange = self._create_exchange(exchange_name)
        
    def _create_exchange(self, name):
        """
        Create Binance Futures exchange instance.
        Use 'binanceusdm' for USDT-M perpetual futures [citation:10].
        """
        exchange_map = {
            "binanceusdm": ccxt.binanceusdm,  # USDT-M Futures
            "binancecoinm": ccxt.binancecoinm,  # COIN-M Futures
            "binance": ccxt.binance,  # Spot
        }
        
        if name not in exchange_map:
            raise ValueError(f"Unsupported exchange: {name}. Use 'binanceusdm' for USDT-M Futures")
        
        exchange = exchange_map[name]({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',  # Ensure futures market
            }
        })
        
        return exchange
    
    def fetch_ohlcv(self, symbol, timeframe, limit=100):
        """Fetch OHLCV data for a symbol and timeframe"""
        try:
            # Binance Futures uses format like "BTC/USDT:USDT" for perpetual contracts
            # But ccxt handles the conversion automatically with binanceusdm
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            closes = [candle[4] for candle in ohlcv]
            current_price = closes[-1] if closes else None
            
            return {
                "prices": closes,
                "current_price": current_price,
            }
        except Exception as e:
            print(f"Error fetching {symbol} {timeframe}: {e}")
            return None

# ============================================================
# MAIN BOT
# ============================================================

class BinanceFuturesRSIBot:
    def __init__(self, config):
        self.config = config
        self.exchange = BinanceFuturesClient(config["exchange"])
        self.alert_manager = AlertManager(config)
        self.htf_cache = {}  # Cache for higher timeframe RSI values
        
    def check_rsi_zone(self, rsi_value):
        """Determine which zone RSI is in"""
        buy_zone = (self.config["buy_zone_low"] <= rsi_value <= self.config["buy_zone_high"])
        sell_zone = (self.config["sell_zone_low"] <= rsi_value <= self.config["sell_zone_high"])
        
        if buy_zone:
            return "buy"
        elif sell_zone:
            return "sell"
        return None
    
    def get_htf_rsi(self, symbol):
        """Get higher timeframe RSI for filtering (cached per cycle)"""
        if not self.config["enable_htf_filter"]:
            return None
        
        cache_key = f"{symbol}_{self.config['htf_timeframe']}"
        if cache_key in self.htf_cache:
            return self.htf_cache[cache_key]
        
        data = self.exchange.fetch_ohlcv(symbol, self.config["htf_timeframe"], self.config["candle_limit"])
        if data and len(data["prices"]) >= self.config["rsi_period"] + 1:
            htf_rsi = calculate_rsi(data["prices"], self.config["rsi_period"])
            self.htf_cache[cache_key] = htf_rsi
            return htf_rsi
        
        return None
    
    def htf_filter_allows(self, symbol, zone):
        """Apply higher timeframe filter"""
        if not self.config["enable_htf_filter"]:
            return True
        
        htf_rsi = self.get_htf_rsi(symbol)
        if htf_rsi is None:
            return True  # If can't get HTF data, allow alert
        
        if zone == "buy":
            # Don't alert buy if higher timeframe is overbought
            if htf_rsi > self.config["htf_max_rsi_for_buy"]:
                return False
        elif zone == "sell":
            # Don't alert sell if higher timeframe is oversold
            if htf_rsi < self.config["htf_min_rsi_for_sell"]:
                return False
        
        return True
    
    def run_once(self):
        """Run one monitoring cycle"""
        print(f"\n{'='*60}")
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking {len(self.config['symbols'])} symbols on Binance Futures")
        print(f"{'='*60}")
        
        # Clear HTF cache each cycle
        self.htf_cache = {}
        
        for symbol in self.config["symbols"]:
            for timeframe in self.config["timeframes"]:
                data = self.exchange.fetch_ohlcv(symbol, timeframe, self.config["candle_limit"])
                
                if data is None or len(data["prices"]) < self.config["rsi_period"] + 1:
                    continue
                
                rsi = calculate_rsi(data["prices"], self.config["rsi_period"])
                
                if rsi is None:
                    continue
                
                zone = self.check_rsi_zone(rsi)
                
                # Apply higher timeframe filter if enabled
                if zone and not self.htf_filter_allows(symbol, zone):
                    zone_str = zone.upper() if zone else "---"
                    filter_msg = f" (HTF RSI {self.get_htf_rsi(symbol):.2f} blocked)"
                    print(f"  {symbol:12} {timeframe:4} | RSI: {rsi:6.2f} | Zone: {zone_str:4} | Price: {data['current_price']}{filter_msg}")
                    continue
                
                # Send alert if entering zone
                if zone:
                    self.alert_manager.send_alert(
                        symbol=symbol,
                        timeframe=timeframe,
                        direction=zone,
                        rsi_value=rsi,
                        price=data["current_price"]
                    )
                
                zone_str = zone.upper() if zone else "---"
                print(f"  {symbol:12} {timeframe:4} | RSI: {rsi:6.2f} | Zone: {zone_str:4} | Price: {data['current_price']}")
        
        print(f"Next check in {self.config['check_interval']} seconds...")
    
    def run(self):
        """Main loop"""
        print("\n" + "="*60)
        print("BINANCE FUTURES RSI ALERT BOT")
        print("="*60)
        print(f"Exchange: Binance USDT-M Perpetual Futures")
        print(f"Symbols: {', '.join(self.config['symbols'])}")
        print(f"Timeframes: {', '.join(self.config['timeframes'])}")
        print(f"Buy Zone: {self.config['buy_zone_low']} - {self.config['buy_zone_high']}")
        print(f"Sell Zone: {self.config['sell_zone_low']} - {self.config['sell_zone_high']}")
        print(f"Check Interval: {self.config['check_interval']} seconds")
        print(f"Audio Alerts: {'ON' if self.config['enable_audio'] else 'OFF'}")
        if self.config["enable_htf_filter"]:
            print(f"HTF Filter: ON ({self.config['htf_timeframe']} - Buy only if RSI < {self.config['htf_max_rsi_for_buy']}, Sell only if RSI > {self.config['htf_min_rsi_for_sell']})")
        else:
            print(f"HTF Filter: OFF")
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
    # Load config from file if exists
    config_file = Path("binance_config.json")
    if config_file.exists():
        with open(config_file, "r") as f:
            user_config = json.load(f)
            CONFIG.update(user_config)
    
    bot = BinanceFuturesRSIBot(CONFIG)
    bot.run()
