#KEY FIXES NEEDED
#1. Prevent premature position reset
#Currently, the bot resets and opens a new position as soon as TP is hit, without ensuring the 0.1% pullback happens from a new high (or low in SHORT).
#We need to track break-even price and hold until a pullback from peak is detected.
#2. Fix Take Profit Tracking Logic
#The bot should not re-enter until a complete sell has occurred.

#✅ Improvements Included:
#✅ first_buy_amount adjustable via GUI input
#✅ Bot uses updated amount live during margin calls
#✅ GUI shows current first_buy_amount for Long and Short bots
#✅ Start button turns into “Stop” to indicate bot is running
#✅ Basic status label shows which bot is active


#KEY FIXES NEEDED
#1. Prevent premature position reset
#Currently, the bot resets and opens a new position as soon as TP is hit, without ensuring the 0.1% pullback happens from a new high (or low in SHORT).
#We need to track break-even price and hold until a pullback from peak is detected.
#2. Fix Take Profit Tracking Logic
#The bot should not re-enter until a complete sell has occurred.

#Improvements Included:
#first_buy_amount adjustable via GUI input
#Bot uses updated amount live during margin calls
#GUI shows current first_buy_amount for Long and Short bots
#Start button turns into “Stop” to indicate bot is running
#Basic status label shows which bot is active


import tkinter as tk
from tkinter import ttk
import threading
from binance.client import Client
from binance.enums import *
import time
import math

# === Configuration ===
API_KEY = 'Lc4cWwugpGeO8FY839EuFbsxGoVs8AdPj941BeI4xaEBlVl5bHk3kXvucHllTqTO'
API_SECRET = 'y7yo9NWcxd3q4s3fSuJGnAr3GJummapaT8iXeg58k6ryzQIPmw1JvXcSdyXBgRtv'

LEVERAGE = 10
TP_PERCENT = 0.015  # 1.5%
PULLBACK_PERCENT = 0.001  # 0.1%

MARGIN_CALL_CONFIG = [
    (0, 1.00), (3.5, 1.00), (3.5, 1.30), (7, 2.6),
    (7, 7.8), (7, 17.), (7, 45), (7, 112),
    (7, 221), (7, 445)
]

# === Base Bot ===
class BaseTradingBot:
    def __init__(self, symbol, entry_price, callback, side, get_first_buy_amount):
        self.client = Client(API_KEY, API_SECRET)
        self.symbol = symbol
        self.initial_price = entry_price
        self.status_callback = callback
        self.side = side  # 'LONG' or 'SHORT'
        self.get_first_buy_amount = get_first_buy_amount
        self.client.futures_change_leverage(symbol=self.symbol, leverage=LEVERAGE)
        self.step_size, self.tick_size = self.get_precisions()
        self.reset()

    def get_precisions(self):
        info = self.client.futures_exchange_info()
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
        return math.floor(q / self.step_size) * self.step_size

    def adjust_price(self, p):
        return math.floor(p / self.tick_size) * self.tick_size

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
            if self.side == 'LONG':
                self.next_price = self.adjust_price(self.initial_price * (1 - offset / 100))
            else:
                self.next_price = self.adjust_price(self.initial_price * (1 + offset / 100))

    def open_position(self, price):
        _, multiplier = MARGIN_CALL_CONFIG[self.margin_index]
        amount = self.get_first_buy_amount() * LEVERAGE * multiplier
        raw_qty = amount / price
        qty = self.adjust_quantity(raw_qty)
        side = SIDE_BUY if self.side == 'LONG' else SIDE_SELL
        self.client.futures_create_order(symbol=self.symbol, side=side, type=ORDER_TYPE_MARKET, quantity=qty)

        self.positions.append((price, qty))
        self.total_cost += amount
        self.total_qty += qty
        self.margin_index += 1
        self._update_next_price()

    def close_position(self):
        qty = self.adjust_quantity(self.total_qty)
        side = SIDE_SELL if self.side == 'LONG' else SIDE_BUY
        self.client.futures_create_order(symbol=self.symbol, side=side, type=ORDER_TYPE_MARKET, quantity=qty)

    def get_price(self):
        return float(self.client.futures_symbol_ticker(symbol=self.symbol)['price'])

    def break_even(self):
        return self.total_cost / self.total_qty if self.total_qty > 0 else 0

    def tp_price(self):
        if self.side == 'LONG':
            return self.adjust_price(self.break_even() * (1 + TP_PERCENT))
        else:
            return self.adjust_price(self.break_even() * (1 - TP_PERCENT))

    def should_add(self, current):
        return self.margin_index < len(MARGIN_CALL_CONFIG) and (
            (self.side == 'LONG' and current <= self.next_price) or
            (self.side == 'SHORT' and current >= self.next_price)
        )

    def run(self):
        while True:
            current = self.get_price()
            target_tp = self.tp_price()

            if self.side == 'LONG':
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
            else:
                if not self.tp_triggered and current <= target_tp:
                    self.tp_triggered = True
                    self.high_point = current
                elif self.tp_triggered:
                    self.high_point = min(self.high_point, current)
                    if current >= self.high_point * (1 + PULLBACK_PERCENT):
                        self.close_position()
                        time.sleep(2)
                        self.initial_price = self.get_price()
                        self.reset()
                        continue

            if self.should_add(current):
                self.open_position(current)

            self.status_callback(self.side, self.status(current))
            time.sleep(10)

    def status(self, price):
        return {
            'current_price': round(price, 2),
            'entry_price': round(self.initial_price, 2),
            'break_even': round(self.break_even(), 4),
            'take_profit': round(self.tp_price(), 4),
            'next_call_price': round(self.next_price, 4),
            'quantity': round(self.total_qty, 4),
            'cost': round(self.total_cost, 2),
            'margin_call_index': self.margin_index,
            'first_buy_amount': round(self.get_first_buy_amount(), 2)
        }

# === GUI Dashboard ===
class DualBotDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("Dual Trading Bot Dashboard")

        # Symbol selector
        ttk.Label(root, text="Select Symbol:").pack()
        self.symbol_var = tk.StringVar()
        self.symbol_menu = ttk.Combobox(root, textvariable=self.symbol_var)
        self.symbol_menu['values'] = self.get_symbols()
        self.symbol_menu.current(0)
        self.symbol_menu.pack(pady=5)

        # First Buy Amount Entry
        ttk.Label(root, text="First Buy Amount (USD):").pack()
        self.first_buy_var = tk.DoubleVar(value=2.1)
        ttk.Entry(root, textvariable=self.first_buy_var).pack(pady=5)

        # Status label
        self.status_label = ttk.Label(root, text="Bot Status: IDLE")
        self.status_label.pack(pady=5)

        # Start/Stop Buttons
        self.btn_long = ttk.Button(root, text="Start Long Bot", command=self.start_long)
        self.btn_short = ttk.Button(root, text="Start Short Bot", command=self.start_short)
        self.btn_long.pack(pady=5)
        self.btn_short.pack(pady=5)

        self.long_bot_running = False
        self.short_bot_running = False

        # Stats Table
        self.tree = ttk.Treeview(root)
        self.tree['columns'] = ('long', 'short')
        self.tree.column('#0', width=180, anchor='w')
        self.tree.column('long', width=100, anchor='center')
        self.tree.column('short', width=100, anchor='center')
        self.tree.heading('#0', text='Metric')
        self.tree.heading('long', text='Long')
        self.tree.heading('short', text='Short')

        self.items = {}
        for metric in ['current_price', 'entry_price', 'break_even', 'take_profit',
                       'next_call_price', 'quantity', 'cost', 'margin_call_index', 'first_buy_amount']:
            self.items[metric] = self.tree.insert('', 'end', text=metric, values=('...', '...'))

        self.tree.pack(padx=10, pady=10)

    def get_symbols(self):
        client = Client(API_KEY, API_SECRET)
        info = client.futures_exchange_info()
        return sorted([s['symbol'] for s in info['symbols'] if s['contractType'] == 'PERPETUAL'])

    def update(self, side, status):
        for key, value in status.items():
            existing = self.tree.item(self.items[key], 'values')
            if side == 'LONG':
                self.tree.item(self.items[key], values=(value, existing[1]))
            else:
                self.tree.item(self.items[key], values=(existing[0], value))

    def start_long(self):
        if not self.long_bot_running:
            self.long_bot_running = True
            self.btn_long.config(text="Stop Long Bot")
            self.status_label.config(text="Bot Status: LONG Running")
            threading.Thread(target=self._run_bot, args=('LONG',), daemon=True).start()

    def start_short(self):
        if not self.short_bot_running:
            self.short_bot_running = True
            self.btn_short.config(text="Stop Short Bot")
            self.status_label.config(text="Bot Status: SHORT Running")
            threading.Thread(target=self._run_bot, args=('SHORT',), daemon=True).start()

    def _run_bot(self, side):
        symbol = self.symbol_var.get()
        get_first_buy = lambda: max(0.01, min(self.first_buy_var.get(), 10000))
        client = Client(API_KEY, API_SECRET)
        price = float(client.futures_symbol_ticker(symbol=symbol)['price'])
        bot = BaseTradingBot(symbol, price, callback=self.update, side=side, get_first_buy_amount=get_first_buy)
        bot.run()

# === Run App ===
if __name__ == '__main__':
    root = tk.Tk()
    app = DualBotDashboard(root)
    root.mainloop()
