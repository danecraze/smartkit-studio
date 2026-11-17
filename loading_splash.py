"""Small 'Loading …' window with a progress bar, run as a separate process while the main
SmartKit window is busy loading the plugin (plugins must be loaded on the main thread)."""
import sys, time, tkinter as tk
from tkinter import ttk
import os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import theme as T

title, expect = sys.argv[1], max(5.0, float(sys.argv[2]))
root = tk.Tk(); root.title('SmartKit'); root.attributes('-topmost', True); root.resizable(False, False)
try:
    _t = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'studio_settings.json'))).get('theme', 'dark')
except Exception:
    _t = 'dark'
T.apply(root, _t); T.title_bar(root); T.app_icon(root)
ttk.Label(root, text=title, style='Head.TLabel').pack(padx=20, pady=(14, 4))
bar = ttk.Progressbar(root, length=360, maximum=100); bar.pack(padx=20, pady=4)
lab = ttk.Label(root, text='', style='Small.TLabel'); lab.pack(padx=20, pady=(0, 14))
root.update_idletasks()
x = (root.winfo_screenwidth() - root.winfo_width()) // 2; y = (root.winfo_screenheight() - root.winfo_height()) // 3
root.geometry(f'+{x}+{y}')
t0 = time.time()

def tick():
    el = time.time() - t0
    bar['value'] = min(97, 100 * el / expect)
    lab['text'] = f'{el:.0f} s  (last time {expect:.0f} s) – the main window does not respond meanwhile'
    root.after(250, tick)
tick(); root.mainloop()
