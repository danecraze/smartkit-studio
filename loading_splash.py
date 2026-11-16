"""Small 'Loading …' window with a progress bar, run as a separate process while the main
SmartKit window is busy loading the plugin (plugins must be loaded on the main thread)."""
import sys, time, tkinter as tk
from tkinter import ttk

title, expect = sys.argv[1], max(5.0, float(sys.argv[2]))
root = tk.Tk(); root.title('SmartKit'); root.attributes('-topmost', True); root.resizable(False, False)
ttk.Label(root, text=title, font=('Segoe UI', 10, 'bold')).pack(padx=20, pady=(14, 4))
bar = ttk.Progressbar(root, length=360, maximum=100); bar.pack(padx=20, pady=4)
lab = ttk.Label(root, text=''); lab.pack(padx=20, pady=(0, 14))
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
