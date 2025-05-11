#still testing

import tkinter as tk
from tkinter import ttk
import threading
import time
import math
from binance.client import Client
from binance.enums import *

# === Configuration ===
API_KEY = 'xJYjavN1uCiKtSBD2PlkFsqIjrAU2L5rxgr1gKJreGQ67UUyYPaYWaUvBuaTuUA8'
API_SECRET = 'J4bu0rHce9lLPQ1n3NkvnC2Z2UatjhvnQrUtqyeqfm1L3vLZW9AwV3LDF0OS4puK'

PULLBACK_PERCENT = 0.001  # 0.1%
MARGIN_CALL_CONFIG = [
    (0, 1.00), (5, 1), (6, 2), (7, 4),
    (7,11), (7,28), (7, 70), (7, 168),(7, 504),
]

# === Spot Trading Bot Class ===
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

# === GUI ===
class SpotBotDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("Dual-Symbol Spot Trading Bot")

        self.client = Client(API_KEY, API_SECRET)
        self.symbols = self.get_symbols()

        self.stop_event1 = threading.Event()
        self.stop_event2 = threading.Event()

        self.bot1 = None
        self.bot2 = None

        self.build_ui()

    def get_symbols(self):
        info = self.client.get_exchange_info()
        return sorted([s['symbol'] for s in info['symbols'] if s['status'] == 'TRADING' and s['quoteAsset'] == 'USDT'])

    def build_ui(self):
        frame = ttk.Frame(self.root)
        frame.pack(padx=10, pady=10)

        for i in range(2):
            ttk.Label(frame, text=f"Symbol {i+1}:").grid(row=i*4, column=0)
            symbol_var = tk.StringVar()
            combo = ttk.Combobox(frame, textvariable=symbol_var, values=self.symbols)
            combo.current(i)
            combo.grid(row=i*4, column=1)
            
            ttk.Label(frame, text="Buy Amount (USD):").grid(row=i*4+1, column=0)
            buy_var = tk.DoubleVar(value=3)
            ttk.Entry(frame, textvariable=buy_var).grid(row=i*4+1, column=1)

            ttk.Label(frame, text="TP%:").grid(row=i*4+2, column=0)
            tp_var = tk.DoubleVar(value=1.0)
            ttk.Entry(frame, textvariable=tp_var).grid(row=i*4+2, column=1)

            tree = ttk.Treeview(frame, height=9)
            tree['columns'] = ('value',)
            tree.column('#0', width=180, anchor='w')
            tree.column('value', width=100, anchor='center')
            tree.heading('#0', text='Metric')
            tree.heading('value', text='Value')
            tree.grid(row=i*4+3, column=0, columnspan=2, pady=5)

            items = {}
            for metric in ['current_price', 'entry_price', 'weighted_average_price', 'take_profit',
                           'next_call_price', 'quantity', 'cost', 'margin_call_index', 'first_buy_amount']:
                items[metric] = tree.insert('', 'end', text=metric, values=('...',))

            setattr(self, f'symbol_var{i+1}', symbol_var)
            setattr(self, f'first_buy_var{i+1}', buy_var)
            setattr(self, f'tp_percent_var{i+1}', tp_var)
            setattr(self, f'tree{i+1}', tree)
            setattr(self, f'items{i+1}', items)

        ttk.Button(frame, text="Start Both Bots", command=self.start_bots).grid(row=10, column=0, pady=10)
        ttk.Button(frame, text="Stop Both Bots", command=self.stop_bots).grid(row=10, column=1, pady=10)

    def update_status(self, symbol, status):
        for i in range(1, 3):
            if symbol == getattr(self, f'symbol_var{i}').get():
                items = getattr(self, f'items{i}')
                tree = getattr(self, f'tree{i}')
                for key, value in status.items():
                    tree.item(items[key], values=(value,))
                break

    def start_bots(self):
        self.stop_event1.clear()
        self.stop_event2.clear()
        self._start_bot(1)
        self._start_bot(2)

    def stop_bots(self):
        self.stop_event1.set()
        self.stop_event2.set()

    def _start_bot(self, index):
        symbol = getattr(self, f'symbol_var{index}').get()
        first_buy = getattr(self, f'first_buy_var{index}').get()
        tp = getattr(self, f'tp_percent_var{index}').get() / 100
        stop_event = getattr(self, f'stop_event{index}')

        price = float(self.client.get_symbol_ticker(symbol=symbol)['price'])
        bot = SpotTradingBot(symbol, price, callback=self.update_status,
                             get_first_buy_amount=lambda: first_buy,
                             stop_event=stop_event,
                             tp_percent=tp)
        setattr(self, f'bot{index}', bot)
        threading.Thread(target=bot.run, daemon=True).start()

# === Run App ===
if __name__ == '__main__':
    root = tk.Tk()
    app = SpotBotDashboard(root)
    root.mainloop()
