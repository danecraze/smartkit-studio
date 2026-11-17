"""Small always-on-top 'Kit loaded – continue' window shown while the plugin window is open
(run as a separate process: the main SmartKit window is blocked while the plugin window is open).
Exit code 0 = continue, 1 = cancelled/closed."""
import sys, tkinter as tk
from tkinter import ttk
import os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import theme as T

root = tk.Tk(); root.title('SmartKit'); root.attributes('-topmost', True); root.resizable(False, False)
try:
    _t = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'studio_settings.json'))).get('theme', 'dark')
except Exception:
    _t = 'dark'
T.apply(root, _t); T.title_bar(root); T.app_icon(root)
code = {'v': 1}
ttk.Label(root, text='SmartKit – choose your kit', style='Title.TLabel').pack(padx=18, pady=(12, 2))
ttk.Label(root, justify='left', wraplength=330, style='Muted.TLabel', text=(
    '1. In the plugin window, load the kit / preset you want.\n'
    '2. Wait until the plugin has finished loading its samples.\n'
    '3. Press the button below. The plugin window closes and SmartKit goes on to "Find sounds".')
          ).pack(padx=18, pady=4, anchor='w')


def go():
    code['v'] = 0; root.destroy()


ttk.Button(root, text='✔  Kit loaded – continue', style='Accent.TButton', command=go).pack(padx=18, pady=(8, 14), fill='x')
root.protocol('WM_DELETE_WINDOW', root.destroy)
root.update_idletasks()
x = root.winfo_screenwidth() - root.winfo_width() - 40
root.geometry(f'+{x}+60')
root.mainloop()
sys.exit(code['v'])
