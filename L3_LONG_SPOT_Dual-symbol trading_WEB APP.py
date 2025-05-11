#L3_LONG_SPOT_Dual-symbol trading_WEB APP

import streamlit as st
import threading
import time
import math
from binance.client import Client
from binance.enums import *

# === Configuration ===
API_KEY = 'your_api_key_here'
API_SECRET = 'your_api_secret_here'

PULLBACK_PERCENT = 0.001  # 0.1%

MARGIN_CALL_CONFIG = [
    (0, 1.00), (5, 1), (6, 2), (7, 4),
    (7, 11), (7, 28), (7, 70), (7, 168), (7, 504),
]

# === Spot Trading Bot ===
class SpotTradingBot:
    def __init__(self, symbol, entry_price, callback, get_first_buy_amount, stop_event, tp_percent):
        self.client = Client(API_KEY, API_SECRET)
        self.symbol = symbol
        self.initial_price = entry_price
        self.status_callback = callback
        self.get_first_buy_amount = get_first_buy_amount
        self.stop_event = stop_event
        self.tp_percent = tp_percent
        self.step_size, self.tick_size = self.get_precisions()
        self.reset()

    def get_precisions(self):
        info = self.client.get_exchange_info()
        for s in info['symbols']:
            if s['symbol'] == self.symbol:
                step = tick = 0.001
                for f in s['filters']:
                    if f['filterType'] == 'LOT_SIZE':
                        step = float(f['stepSize'])
                    if f['filterType'] == 'PRICE_FILTER':
                        tick = float(f['tickSize'])
                return step, tick
        return 0.001, 0.01

    def adjust_quantity(self, q):
        return round(math.floor(q / self.step_size) * self.step_size, 8)

    def adjust_price(self, p):
        return round(round(p / self.tick_size) * self.tick_size, 8)

    def reset(self):
        self.positions = []
        self.total_cost = 0
        self.total_qty = 0
        self.margin_index = 0
        self.tp_triggered = False
        self.high_point = self.initial_price
        self._update_next_price()
        self.open_position(self.initial_price)

    def _update_next_price(self):
        if self.margin_index < len(MARGIN_CALL_CONFIG):
            offset = sum([p for p, _ in MARGIN_CALL_CONFIG[:self.margin_index + 1]])
            self.next_price = self.adjust_price(self.initial_price * (1 - offset / 100))

    def open_position(self, price):
        _, multiplier = MARGIN_CALL_CONFIG[self.margin_index]
        amount = self.get_first_buy_amount() * multiplier
        raw_qty = amount / price
        qty = self.adjust_quantity(raw_qty)
        self.client.create_order(
            symbol=self.symbol,
            side=SIDE_BUY,
            type=ORDER_TYPE_MARKET,
            quantity=qty
        )
        self.positions.append((price, qty))
        self.total_cost += amount
        self.total_qty += qty
        self.margin_index += 1
        self._update_next_price()

    def close_position(self):
        qty = self.adjust_quantity(self.total_qty)
        self.client.create_order(
            symbol=self.symbol,
            side=SIDE_SELL,
            type=ORDER_TYPE_MARKET,
            quantity=qty
        )

    def get_price(self):
        return float(self.client.get_symbol_ticker(symbol=self.symbol)['price'])

    def weighted_average_price(self):
        if self.total_qty == 0:
            return 0
        return sum([price * qty for price, qty in self.positions]) / self.total_qty

    def tp_price(self):
        wap = self.weighted_average_price()
        return self.adjust_price(wap * (1 + self.tp_percent))

    def should_add(self, current):
        return self.margin_index < len(MARGIN_CALL_CONFIG) and current <= self.next_price

    def run(self):
        while not self.stop_event.is_set():
            current = self.get_price()
            target_tp = self.tp_price()

            if not self.tp_triggered and current >= target_tp:
                self.tp_triggered = True
                self.high_point = current
            elif self.tp_triggered:
                self.high_point = max(self.high_point, current)
                if current <= self.high_point * (1 - PULLBACK_PERCENT):
                    self.close_position()
                    time.sleep(2)
                    self.initial_price = self.get_price()
                    self.reset()
                    continue

            if self.should_add(current):
                self.open_position(current)

            self.status_callback(self.symbol, self.status(current))
            time.sleep(10)

    def status(self, price):
        wap = self.weighted_average_price()
        return {
            'current_price': round(price, 5),
            'entry_price': round(self.initial_price, 5),
            'weighted_average_price': round(wap, 5),
            'take_profit': round(self.tp_price(), 5),
            'next_call_price': round(self.next_price, 5),
            'quantity': round(self.total_qty, 4),
            'cost': round(self.total_cost, 2),
            'margin_call_index': self.margin_index,
            'first_buy_amount': round(self.get_first_buy_amount(), 2)
        }

# === Streamlit App ===
def main():
    # Set up Streamlit UI components
    st.title("Dual Symbol Binance Spot Trading Bot")

    client = Client(API_KEY, API_SECRET)
    symbols = get_symbols(client)

    # Symbol 1 configuration
    symbol1 = st.selectbox("Select Symbol 1:", symbols)
    first_buy1 = st.number_input("First Buy Amount 1 (USD):", value=3.0, min_value=0.1)
    tp_percent1 = st.number_input("Take Profit % 1:", value=1.0, min_value=0.1)

    # Symbol 2 configuration
    symbol2 = st.selectbox("Select Symbol 2:", symbols)
    first_buy2 = st.number_input("First Buy Amount 2 (USD):", value=3.0, min_value=0.1)
    tp_percent2 = st.number_input("Take Profit % 2:", value=1.0, min_value=0.1)

    # Bot control buttons
    bot1_running = st.empty()
    bot2_running = st.empty()

    stop_event1 = threading.Event()
    stop_event2 = threading.Event()

    def run_bot1():
        stop_event1.clear()
        threading.Thread(target=run_trading_bot, args=(symbol1, first_buy1, tp_percent1 / 100, stop_event1, bot1_running), daemon=True).start()

    def run_bot2():
        stop_event2.clear()
        threading.Thread(target=run_trading_bot, args=(symbol2, first_buy2, tp_percent2 / 100, stop_event2, bot2_running), daemon=True).start()

    def stop_bot1():
        stop_event1.set()

    def stop_bot2():
        stop_event2.set()

    # Bot actions
    if st.button("Start Bot 1"):
        run_bot1()

    if st.button("Stop Bot 1"):
        stop_bot1()

    if st.button("Start Bot 2"):
        run_bot2()

    if st.button("Stop Bot 2"):
        stop_bot2()

def get_symbols(client):
    info = client.get_exchange_info()
    return sorted([s['symbol'] for s in info['symbols'] if s['status'] == 'TRADING' and s['quoteAsset'] == 'USDT'])

def update_status(symbol, status):
    st.write(f"### {symbol} Status")
    for key, val in status.items():
        st.write(f"{key}: {val}")

def run_trading_bot(symbol, first_buy, tp_percent, stop_event, status_callback):
    price = float(Client(API_KEY, API_SECRET).get_symbol_ticker(symbol=symbol)['price'])
    bot = SpotTradingBot(symbol, price, status_callback, lambda: first_buy, stop_event, tp_percent)
    bot.run()

if __name__ == '__main__':
    main()
