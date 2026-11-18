"""SmartKit Studio look: a quiet dark theme for dark studios (and a light one), built on ttk's 'clam' theme.

One set of colour tokens per theme, flat surfaces, 1 px borders, one accent colour (amber, like a lit
button on studio gear) used only for the main actions, selection and progress.
"""
import os, sys
import tkinter as tk
from tkinter import ttk, font as tkfont

PALETTES = {
    'dark': dict(
        bg='#16181b',        # window
        panel='#1d2024',     # lists, log, tables
        field='#25292e',     # inputs, buttons, headings
        hover='#2e3339',
        border='#343a41',
        text='#e4e6e9',
        muted='#9aa1a9',
        faint='#646b73',
        accent='#e3a33f',
        accent_hover='#efb75e',
        on_accent='#17130b',
        select='#4a3a1c',
        on_select='#ffffff',
    ),
    'light': dict(
        bg='#f2f3f5',
        panel='#ffffff',
        field='#ffffff',
        hover='#e7e9ec',
        border='#cfd4da',
        text='#1c1f23',
        muted='#5a6169',
        faint='#959ca4',
        accent='#b56d0c',
        accent_hover='#9a5c09',
        on_accent='#ffffff',
        select='#f5dfb8',
        on_select='#1c1f23',
    ),
}

C = dict(PALETTES['dark'])          # current colours (updated by apply)
_tk_widgets = []                    # plain tk widgets (Text, Listbox, Canvas, Menu) to recolour on a switch
_windows = []                       # toplevels whose title bar follows the theme


def _family(root, *names):
    have = set(tkfont.families(root))
    for n in names:
        if n in have:
            return n
    return tkfont.nametofont('TkDefaultFont', root=root).actual('family')


def fonts(root):
    ui = _family(root, 'Segoe UI', 'Inter', 'Helvetica Neue', 'DejaVu Sans')
    semi = _family(root, 'Segoe UI Semibold', 'Segoe UI Variable Display Semib', ui)
    mono = _family(root, 'Cascadia Mono', 'Consolas', 'JetBrains Mono', 'DejaVu Sans Mono', 'Courier New')
    return dict(ui=(ui, 10), small=(ui, 9), semi=(semi, 10, 'bold' if semi == ui else 'normal'),
                title=(semi, 12, 'bold' if semi == ui else 'normal'), mono=(mono, 9))


F = {}


def apply(root, name='dark'):
    """Set the theme on every ttk style and on the registered tk widgets."""
    C.clear(); C.update(PALETTES.get(name, PALETTES['dark']))
    if not F:
        F.update(fonts(root))
        for fn in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont', 'TkHeadingFont'):
            try:
                tkfont.nametofont(fn, root=root).configure(family=F['ui'][0], size=F['ui'][1])
            except tk.TclError:
                pass
    s = ttk.Style(root)
    s.theme_use('clam')
    flat = dict(lightcolor=C['field'], darkcolor=C['field'], bordercolor=C['border'])

    s.configure('.', background=C['bg'], foreground=C['text'], fieldbackground=C['field'],
                bordercolor=C['border'], lightcolor=C['bg'], darkcolor=C['bg'], troughcolor=C['panel'],
                focuscolor=C['accent'], selectbackground=C['select'], selectforeground=C['on_select'],
                insertcolor=C['text'], font=F['ui'], relief='flat')
    s.map('.', foreground=[('disabled', C['faint'])])

    s.configure('TFrame', background=C['bg'])
    s.configure('Bar.TFrame', background=C['panel'])
    s.configure('TLabel', background=C['bg'], foreground=C['text'])
    s.configure('Muted.TLabel', foreground=C['muted'])
    s.configure('Small.TLabel', foreground=C['muted'], font=F['small'])
    s.configure('Head.TLabel', font=F['semi'])
    s.configure('Title.TLabel', font=F['title'])
    s.configure('Bar.TLabel', background=C['panel'], foreground=C['muted'], font=F['small'])
    s.configure('BarTitle.TLabel', background=C['panel'], foreground=C['text'], font=F['semi'])
    s.configure('BarMuted.TLabel', background=C['panel'], foreground=C['faint'], font=F['small'])

    s.configure('TLabelframe', background=C['bg'], bordercolor=C['border'], lightcolor=C['bg'], darkcolor=C['bg'],
                relief='solid', borderwidth=1, padding=(10, 6, 10, 8))
    s.configure('TLabelframe.Label', background=C['bg'], foreground=C['muted'], font=F['semi'])
    s.configure('TSeparator', background=C['border'])

    # buttons
    s.configure('TButton', background=C['field'], foreground=C['text'], padding=(12, 5), anchor='center', **flat)
    s.map('TButton', background=[('pressed', C['border']), ('active', C['hover'])],
          bordercolor=[('focus', C['muted'])], lightcolor=[('active', C['hover'])], darkcolor=[('active', C['hover'])])
    s.configure('Accent.TButton', background=C['accent'], foreground=C['on_accent'], bordercolor=C['accent'],
                lightcolor=C['accent'], darkcolor=C['accent'], font=F['semi'])
    s.map('Accent.TButton', background=[('pressed', C['accent_hover']), ('active', C['accent_hover'])],
          lightcolor=[('active', C['accent_hover'])], darkcolor=[('active', C['accent_hover'])],
          bordercolor=[('active', C['accent_hover'])], foreground=[('disabled', C['faint'])])
    s.configure('Tool.TButton', background=C['bg'], bordercolor=C['bg'], lightcolor=C['bg'], darkcolor=C['bg'],
                padding=(8, 4))
    s.map('Tool.TButton', background=[('active', C['hover'])], bordercolor=[('active', C['hover'])],
          lightcolor=[('active', C['hover'])], darkcolor=[('active', C['hover'])])

    # header menus (File / View / Help) – no arrow
    s.layout('Bar.TMenubutton', [('Menubutton.border', {'sticky': 'nswe', 'children': [
        ('Menubutton.padding', {'sticky': 'nswe', 'children': [('Menubutton.label', {'sticky': 'nswe'})]})]})])
    s.configure('BarMenu.TButton', background=C['panel'], foreground=C['text'], padding=(10, 4), width=0,
                bordercolor=C['panel'], lightcolor=C['panel'], darkcolor=C['panel'], font=F['ui'])
    s.map('BarMenu.TButton', background=[('active', C['hover']), ('pressed', C['hover'])],
          bordercolor=[('active', C['hover']), ('focus', C['panel'])], lightcolor=[('active', C['hover'])],
          darkcolor=[('active', C['hover'])])
    s.configure('Bar.TMenubutton', background=C['panel'], foreground=C['text'], padding=(10, 4), width=0,
                bordercolor=C['panel'], lightcolor=C['panel'], darkcolor=C['panel'])
    s.map('Bar.TMenubutton', background=[('active', C['hover'])], bordercolor=[('active', C['hover'])],
          lightcolor=[('active', C['hover'])], darkcolor=[('active', C['hover'])])

    # inputs
    for w in ('TEntry', 'TCombobox', 'TSpinbox'):
        s.configure(w, fieldbackground=C['field'], foreground=C['text'], background=C['field'],
                    arrowcolor=C['muted'], insertcolor=C['text'], padding=(6, 3), **flat)
        s.map(w, bordercolor=[('focus', C['accent'])], lightcolor=[('focus', C['field'])],
              darkcolor=[('focus', C['field'])], fieldbackground=[('readonly', C['field']), ('disabled', C['bg'])],
              background=[('active', C['hover']), ('readonly', C['field'])], arrowcolor=[('active', C['text'])],
              foreground=[('disabled', C['faint']), ('readonly', C['text'])],
              selectbackground=[('readonly', C['field'])], selectforeground=[('readonly', C['text'])])
    s.configure('TSpinbox', arrowsize=11)
    s.configure('Kit.TCombobox', padding=(10, 4), arrowsize=14)
    s.configure('KitLabel.TLabel', background=C['panel'], foreground=C['accent'], font=F['small'])
    root.option_add('*TCombobox*Listbox.background', C['field'])
    root.option_add('*TCombobox*Listbox.foreground', C['text'])
    root.option_add('*TCombobox*Listbox.selectBackground', C['select'])
    root.option_add('*TCombobox*Listbox.selectForeground', C['on_select'])
    root.option_add('*TCombobox*Listbox.font', F['ui'])
    root.option_add('*TCombobox*Listbox.borderWidth', 0)

    s.configure('TCheckbutton', background=C['bg'], foreground=C['text'], indicatorbackground=C['field'],
                indicatorforeground=C['on_accent'], upperbordercolor=C['border'], lowerbordercolor=C['border'],
                indicatormargin=(0, 0, 6, 0))
    s.map('TCheckbutton', background=[('active', C['bg'])],
          indicatorbackground=[('selected', C['accent']), ('active', C['hover'])],
          upperbordercolor=[('selected', C['accent'])], lowerbordercolor=[('selected', C['accent'])])

    # notebook without its own tabs: the step bar (StepBar) above it switches the pages
    s.layout('Steps.TNotebook.Tab', [])
    s.configure('Steps.TNotebook', background=C['bg'], borderwidth=0, tabmargins=0,
                lightcolor=C['bg'], darkcolor=C['bg'], bordercolor=C['bg'])
    s.configure('TNotebook', background=C['bg'], lightcolor=C['bg'], darkcolor=C['bg'], bordercolor=C['border'])
    s.configure('TNotebook.Tab', background=C['bg'], foreground=C['muted'], lightcolor=C['bg'], bordercolor=C['border'])
    s.map('TNotebook.Tab', background=[('selected', C['field'])], foreground=[('selected', C['text'])])
    for name, fg, f in (('Step', C['muted'], F['ui']), ('StepOn', C['text'], F['semi'])):
        s.configure(f'{name}.TButton', background=C['panel'], foreground=fg, font=f, padding=(14, 7, 14, 5),
                    bordercolor=C['panel'], lightcolor=C['panel'], darkcolor=C['panel'])
        s.map(f'{name}.TButton', background=[('active', C['hover'])], foreground=[('active', C['text'])],
              bordercolor=[('active', C['hover'])], lightcolor=[('active', C['hover'])],
              darkcolor=[('active', C['hover'])])
    s.configure('StepOn.TFrame', background=C['accent'])
    s.configure('StepOff.TFrame', background=C['panel'])
    s.configure('Help.TLabel', foreground=C['muted'])
    s.configure('HelpHead.TLabel', foreground=C['faint'], font=F['small'])
    s.map('HelpHead.TLabel', foreground=[('active', C['text'])])

    # tables
    s.configure('Treeview', background=C['panel'], fieldbackground=C['panel'], foreground=C['text'],
                rowheight=26, bordercolor=C['border'], lightcolor=C['panel'], darkcolor=C['panel'], borderwidth=1)
    s.map('Treeview', background=[('selected', C['select'])], foreground=[('selected', C['on_select'])])
    s.configure('Treeview.Heading', background=C['field'], foreground=C['muted'], font=F['small'],
                padding=(6, 5), relief='flat', bordercolor=C['border'], lightcolor=C['field'], darkcolor=C['field'])
    s.map('Treeview.Heading', background=[('active', C['hover'])], foreground=[('active', C['text'])])

    # thin scrollbars without arrows
    for o in ('Vertical', 'Horizontal'):
        s.layout(f'{o}.TScrollbar', [(f'{o}.Scrollbar.trough', {'sticky': 'ns' if o == 'Vertical' else 'ew',
                                      'children': [(f'{o}.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})]})])
        s.configure(f'{o}.TScrollbar', troughcolor=C['bg'], background=C['border'], bordercolor=C['bg'],
                    lightcolor=C['border'], darkcolor=C['border'], gripcount=0, arrowsize=10, width=10)
        s.map(f'{o}.TScrollbar', background=[('active', C['faint'])], lightcolor=[('active', C['faint'])],
              darkcolor=[('active', C['faint'])])

    s.configure('TProgressbar', troughcolor=C['field'], background=C['accent'], bordercolor=C['field'],
                lightcolor=C['accent'], darkcolor=C['accent'], thickness=6)

    root.option_add('*Menu.background', C['field'])
    root.option_add('*Menu.foreground', C['text'])
    root.option_add('*Menu.activeBackground', C['select'])
    root.option_add('*Menu.activeForeground', C['on_select'])
    root.option_add('*Menu.disabledForeground', C['faint'])
    root.option_add('*Menu.selectColor', C['accent'])
    root.option_add('*Menu.relief', 'flat')
    root.option_add('*Menu.borderWidth', 1)
    root.option_add('*Menu.activeBorderWidth', 0)
    root.option_add('*Menu.font', F['ui'])
    root.configure(background=C['bg'])
    _tk_widgets[:] = [w for w in _tk_widgets if _alive(w)]
    for w in _tk_widgets:
        _paint(w)
    for w in [w for w in _windows if _alive(w)]:
        title_bar(w)


def _alive(w):
    try:
        return bool(w.winfo_exists())
    except tk.TclError:
        return False


def _paint(w):
    cls = w.winfo_class()
    try:
        if cls in ('Text', 'Listbox'):
            w.configure(background=C['panel'], foreground=C['text'], selectbackground=C['select'],
                        selectforeground=C['on_select'], highlightthickness=1, highlightbackground=C['border'],
                        highlightcolor=C['border'], borderwidth=0, relief='flat')
            if cls == 'Text':
                w.configure(insertbackground=C['text'], padx=10, pady=8)
            else:
                w.configure(activestyle='none')
        elif cls == 'Canvas':
            w.configure(background=C['bg'], highlightthickness=0, borderwidth=0)
        elif cls == 'Menu':
            w.configure(background=C['field'], foreground=C['text'], activebackground=C['select'],
                        activeforeground=C['on_select'], disabledforeground=C['faint'], relief='flat',
                        borderwidth=1, activeborderwidth=0)
    except tk.TclError:
        pass


def register(w):
    """Colour a plain tk widget now and on every theme switch."""
    _tk_widgets.append(w); _paint(w); return w


def title_bar(win):
    """Windows 10/11: dark or light title bar to match the theme."""
    if win not in _windows:
        _windows.append(win)
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
        dark = ctypes.c_int(1 if C['bg'] == PALETTES['dark']['bg'] else 0)
        for attr in (20, 19):                 # DWMWA_USE_IMMERSIVE_DARK_MODE (newer / older Windows 10)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(dark), ctypes.sizeof(dark)) == 0:
                break
        try:                                  # Windows 11: caption colour = window colour
            col = int(C['bg'][5:7] + C['bg'][3:5] + C['bg'][1:3], 16)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(ctypes.c_int(col)), 4)
        except Exception:
            pass
    except Exception:
        pass


def app_icon(win):
    """SmartKit's icon (icon.ico / icon.png next to the program) on a window and its taskbar button."""
    here = os.path.dirname(os.path.abspath(__file__))
    ico, png = os.path.join(here, 'icon.ico'), os.path.join(here, 'icon.png')
    try:
        if sys.platform == 'win32' and os.path.exists(ico):
            win.iconbitmap(default=ico)                  # small + big icon from the .ico
    except Exception:
        pass
    try:
        if os.path.exists(png):                          # large picture for the taskbar / Alt+Tab
            win._skicon = tk.PhotoImage(file=png)
            win.iconphoto(True, win._skicon)
    except Exception:
        pass
    if sys.platform == 'win32':
        try:                                             # also set the big/small window icons directly
            import ctypes
            win.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
            u = ctypes.windll.user32
            u.LoadImageW.restype = ctypes.c_void_p
            u.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_void_p]
            for which, size in ((1, 256), (0, 16)):      # ICON_BIG, ICON_SMALL
                h = u.LoadImageW(None, ico, 1, size if which else 16, size if which else 16, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
                if h:
                    u.SendMessageW(hwnd, 0x80, which, h)  # WM_SETICON
        except Exception:
            pass


class ScrollPage(ttk.Frame):
    """A page that scrolls when the window is smaller than its content. Put widgets in .body."""

    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self.canvas = register(tk.Canvas(self, highlightthickness=0, borderwidth=0))
        self.sb = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._sb_set)
        self.body = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window(0, 0, window=self.body, anchor='nw')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.body.bind('<Configure>', lambda e: self._update())
        self.canvas.bind('<Configure>', lambda e: (self.canvas.itemconfigure(self._win, width=e.width), self._update()))
        self.bind('<Enter>', self._wheel_on)
        self.bind('<Leave>', self._wheel_off)

    def _update(self):
        self.canvas.configure(scrollregion=(0, 0, self.body.winfo_reqwidth(), self.body.winfo_reqheight()))

    def _sb_set(self, lo, hi):
        if float(lo) <= 0 and float(hi) >= 1:
            self.sb.pack_forget()
        elif not self.sb.winfo_ismapped():
            self.sb.pack(side='right', fill='y', before=self.canvas)
        self.sb.set(lo, hi)

    def _scroll(self, e):
        if self.canvas.yview() == (0.0, 1.0):
            return
        w = e.widget
        try:                                  # leave the wheel to lists and drop-downs under the pointer
            if isinstance(w, str) or w.winfo_class() in ('Treeview', 'Listbox', 'Text', 'TCombobox', 'TSpinbox'):
                return
        except Exception:
            pass
        n = -1 if (getattr(e, 'num', 0) == 4 or e.delta > 0) else 1
        self.canvas.yview_scroll(n * 3, 'units')

    def _wheel_on(self, _e=None):
        for seq in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            self.bind_all(seq, self._scroll)

    def _wheel_off(self, _e=None):
        for seq in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            self.unbind_all(seq)


class WrapLabel(ttk.Label):
    """A label whose text wraps to the width it is given (instead of a fixed number of pixels)."""

    def __init__(self, parent, **kw):
        kw.setdefault('justify', 'left')
        kw.setdefault('wraplength', 360)          # small until the real width is known (keeps grids from growing)
        super().__init__(parent, **kw)
        self.bind('<Configure>', lambda e: self.configure(wraplength=max(200, e.width - 4)))


class StepBar(ttk.Frame):
    """The five steps as a row of flat buttons with an accent line under the open one; drives a Notebook
    whose own tabs are hidden (style Steps.TNotebook)."""

    def __init__(self, parent, nb, **kw):
        kw.setdefault('style', 'Bar.TFrame')
        super().__init__(parent, **kw)
        self.nb, self.items = nb, []
        nb.bind('<<NotebookTabChanged>>', lambda e: self.update_marks(), add='+')

    def add(self, title):
        i = len(self.items)
        f = ttk.Frame(self, style='Bar.TFrame'); f.pack(side='left', padx=(8 if i == 0 else 0, 0))
        b = ttk.Button(f, text=title, style='Step.TButton', takefocus=False, command=lambda: self.nb.select(i))
        b.pack(side='top')
        line = ttk.Frame(f, style='StepOff.TFrame', height=2); line.pack(side='top', fill='x')
        self.items.append((b, line))
        self.update_marks()

    def update_marks(self):
        try:
            cur = self.nb.index('current')
        except tk.TclError:
            cur = 0
        for i, (b, line) in enumerate(self.items):
            b.configure(style='StepOn.TButton' if i == cur else 'Step.TButton')
            line.configure(style='StepOn.TFrame' if i == cur else 'StepOff.TFrame')


class Dialog(tk.Toplevel):
    """A small themed dialog: put widgets in .body and buttons in .buttons, then call show()."""

    def __init__(self, parent, title):
        super().__init__(parent)
        self.withdraw(); self.title(title); self.transient(parent); self.resizable(False, False)
        self.configure(background=C['bg'])
        self.parent, self.result = parent, None
        self.body = ttk.Frame(self, padding=(20, 16, 20, 6)); self.body.pack(fill='both', expand=True)
        self.buttons = ttk.Frame(self, padding=(20, 10, 20, 16)); self.buttons.pack(fill='x', side='bottom')
        self.protocol('WM_DELETE_WINDOW', self.cancel)
        self.bind('<Escape>', lambda e: self.cancel())

    def button(self, text, command, accent=False):
        b = ttk.Button(self.buttons, text=text, command=command, style='Accent.TButton' if accent else 'TButton')
        b.pack(side='right', padx=(8, 0)); return b

    def show(self):
        self.update_idletasks()
        p = self.parent
        x = p.winfo_rootx() + (p.winfo_width() - self.winfo_reqwidth()) // 2
        y = p.winfo_rooty() + max(40, (p.winfo_height() - self.winfo_reqheight()) // 3)
        self.geometry(f'+{max(0, x)}+{max(0, y)}')
        self.deiconify(); title_bar(self)
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.wait_window()
        return self.result

    def ok(self, value=True):
        self.result = value; self.destroy()

    def cancel(self):
        self.result = None; self.destroy()


def ask_string(parent, title, prompt, initial='', maxlen=None):
    d = Dialog(parent, title)
    ttk.Label(d.body, text=prompt).pack(anchor='w')
    v = tk.StringVar(value=initial)
    e = ttk.Entry(d.body, textvariable=v, width=34, font=F['title']); e.pack(fill='x', pady=(6, 0))
    if maxlen:
        v.trace_add('write', lambda *a: len(v.get()) > maxlen and v.set(v.get()[:maxlen]))
    d.button('OK', lambda: d.ok(v.get().strip()), accent=True)
    d.button('Cancel', d.cancel)
    e.bind('<Return>', lambda ev: d.ok(v.get().strip()))
    e.focus_set(); e.select_range(0, 'end')
    return d.show() or None


class _MessageBox:
    """Themed stand-ins for tkinter.messagebox (same call style: showinfo(title, message, parent=…)).
    Long messages wrap; Return = the main button, Escape = cancel / no."""
    ICONS = {'info': ('i', 'accent'), 'warning': ('!', 'accent'), 'error': ('×', 'bad'), 'question': ('?', 'accent')}

    def _show(self, kind, title, message, buttons, default, cancel, parent=None, detail=None, **_):
        parent = parent or tk._default_root
        d = Dialog(parent, title or 'SmartKit')
        glyph, col = self.ICONS[kind]
        colour = C.get(col) or ('#e5534b' if col == 'bad' else C['accent'])
        row = ttk.Frame(d.body); row.pack(fill='both', expand=True)
        c = tk.Canvas(row, width=34, height=34, highlightthickness=0, background=C['bg'])
        c.create_oval(2, 2, 32, 32, outline=colour, width=2)
        c.create_text(17, 17, text=glyph, fill=colour, font=(F.get('title') or ('Segoe UI', 12))[:1] + (14, 'bold'))
        c.pack(side='left', anchor='n', padx=(0, 14))
        text = str(message) + (f'\n\n{detail}' if detail else '')
        ttk.Label(row, text=text, justify='left', wraplength=440).pack(side='left', anchor='w', fill='x')
        first = None
        for label, value in reversed(buttons):
            b = d.button(label, (lambda v=value: d.ok(v)), accent=(value == default))
            if value == default:
                first = b
        d.cancel = lambda: (setattr(d, 'result', cancel), d.destroy())
        d.protocol('WM_DELETE_WINDOW', d.cancel)
        d.bind('<Escape>', lambda e: d.cancel())
        d.bind('<Return>', lambda e: d.ok(default))
        if first is not None:
            d.after(10, first.focus_set)
        r = d.show()
        return r

    def showinfo(self, title=None, message='', **kw):
        self._show('info', title, message, [('OK', 'ok')], 'ok', 'ok', **kw); return 'ok'

    def showwarning(self, title=None, message='', **kw):
        self._show('warning', title, message, [('OK', 'ok')], 'ok', 'ok', **kw); return 'ok'

    def showerror(self, title=None, message='', **kw):
        self._show('error', title, message, [('OK', 'ok')], 'ok', 'ok', **kw); return 'ok'

    def askyesno(self, title=None, message='', **kw):
        return bool(self._show('question', title, message, [('Yes', True), ('No', False)], True, False, **kw))

    def askokcancel(self, title=None, message='', **kw):
        return bool(self._show('question', title, message, [('OK', True), ('Cancel', False)], True, False, **kw))

    def askyesnocancel(self, title=None, message='', **kw):
        return self._show('question', title, message, [('Yes', True), ('No', False), ('Cancel', None)], True, None,
                          **kw)


messagebox = _MessageBox()


def to_recycle_bin(paths):
    """Windows: move files/folders to the Recycle Bin (can be restored). Elsewhere: delete."""
    paths = [os.path.abspath(p) for p in paths if os.path.exists(p)]
    if not paths:
        return
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [('hwnd', wintypes.HWND), ('wFunc', wintypes.UINT), ('pFrom', wintypes.LPCWSTR),
                        ('pTo', wintypes.LPCWSTR), ('fFlags', ctypes.c_uint16),
                        ('fAnyOperationsAborted', wintypes.BOOL), ('hNameMappings', ctypes.c_void_p),
                        ('lpszProgressTitle', wintypes.LPCWSTR)]
        op = SHFILEOPSTRUCTW()
        op.wFunc = 3                                     # FO_DELETE
        op.pFrom = '\0'.join(paths) + '\0'               # list ends with two NULs
        op.fFlags = 0x40 | 0x10 | 0x400 | 0x4            # ALLOWUNDO, NOCONFIRMATION, NOERRORUI, SILENT
        r = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if r or op.fAnyOperationsAborted:
            raise OSError(f'Could not move to the Recycle Bin (code {r}). Is a file still open?')
    else:
        import shutil
        for p in paths:
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)


class Menu:
    """A popup menu drawn with the theme (Windows draws tk.Menu natively, light and with its own font).
    Same calls as tk.Menu for what SmartKit uses: add_command / add_checkbutton / add_radiobutton /
    add_cascade / add_separator, tk_popup(x, y)."""

    def __init__(self, master=None, tearoff=0, **_kw):
        self.master, self.items = master, []
        self._win = None

    # --- building
    def add_command(self, label='', command=None, accelerator='', state='normal', **_kw):
        self.items.append(dict(kind='command', label=label, command=command, acc=accelerator, state=state))

    def add_checkbutton(self, label='', variable=None, command=None, onvalue=None, offvalue=None, **_kw):
        self.items.append(dict(kind='check', label=label, var=variable, command=command, on=onvalue, off=offvalue))

    def add_radiobutton(self, label='', variable=None, value=None, command=None, **_kw):
        self.items.append(dict(kind='radio', label=label, var=variable, value=value, command=command))

    def add_cascade(self, label='', menu=None, **_kw):
        self.items.append(dict(kind='cascade', label=label, menu=menu))

    def add_separator(self, **_kw):
        self.items.append(dict(kind='sep'))

    def delete(self, *_a):
        self.items = []

    def index(self, which):
        """Like tk.Menu.index: 'end' = index of the last entry, None when the menu is empty."""
        if which == 'end':
            return len(self.items) - 1 if self.items else None
        return int(which)

    # --- showing
    def tk_popup(self, x, y, entry=None):
        _MenuSession(self.master).open(self, x, y)

    post = tk_popup

    def _checked(self, it):
        v = it.get('var')
        if v is None:
            return False
        try:
            cur = v.get()
        except tk.TclError:
            return False
        if it['kind'] == 'radio':
            return cur == it['value']
        return cur == it['on'] if it.get('on') is not None else bool(cur) and cur not in ('0', 'False')


class _MenuSession:
    """The chain of open popup windows (menu + submenus); one grab, closed by a click outside or Escape."""

    def __init__(self, master):
        self.root = master.winfo_toplevel() if master is not None else tk._default_root
        self.wins = []                 # [(toplevel, menu, rows)]
        self.hot = None
        self._after = None

    def open(self, menu, x, y, level=0):
        while len(self.wins) > level:
            self._close_last()
        top = tk.Toplevel(self.root)
        top.withdraw(); top.overrideredirect(True)
        top.configure(background=C['border'])
        try:
            top.attributes('-topmost', True)
        except tk.TclError:
            pass
        body = tk.Frame(top, background=C['field'], padx=0, pady=4)
        body.pack(padx=1, pady=1)
        rows = []
        for it in menu.items:
            if it['kind'] == 'sep':
                tk.Frame(body, background=C['border'], height=1).pack(fill='x', padx=8, pady=4)
                continue
            r = tk.Frame(body, background=C['field'])
            r.pack(fill='x')
            dis = it.get('state') == 'disabled'
            mark = '✓' if it['kind'] == 'check' and menu._checked(it) else \
                   '•' if it['kind'] == 'radio' and menu._checked(it) else ''
            fg = C['faint'] if dis else C['text']
            labs = [tk.Label(r, text=mark, width=2, anchor='e', background=C['field'], foreground=C['accent'], font=F['ui']),
                    tk.Label(r, text=it['label'], anchor='w', background=C['field'], foreground=fg, font=F['ui'],
                             padx=6, pady=4)]
            labs[0].pack(side='left'); labs[1].pack(side='left', fill='x', expand=True)
            right = it.get('acc') or ('›' if it['kind'] == 'cascade' else '')
            if right:
                lr = tk.Label(r, text=right, anchor='e', background=C['field'], foreground=C['muted'],
                              font=F['small'] if it['kind'] != 'cascade' else F['ui'], padx=10)
                lr.pack(side='right'); labs.append(lr)
            else:
                tk.Frame(r, width=18, background=C['field']).pack(side='right'); labs.append(r.winfo_children()[-1])
            for w in [r] + labs:
                w._menu_row = (len(self.wins), len(rows))
            rows.append((r, labs, it, dis))
        top.update_idletasks()
        w, h = top.winfo_reqwidth(), top.winfo_reqheight()
        sw, sh = top.winfo_screenwidth(), top.winfo_screenheight()
        if x + w > sw: x = max(0, (x - w - (self.wins[-1][0].winfo_width() if level else 0)) if level else sw - w)
        if y + h > sh: y = max(0, sh - h)
        top.geometry(f'+{int(x)}+{int(y)}')
        top.deiconify(); top.lift()
        self.wins.append((top, menu, rows))
        if level == 0:
            top.bind('<Motion>', self._motion)
            top.bind('<ButtonRelease-1>', self._release)
            top.bind('<ButtonPress-1>', self._press)
            top.bind('<ButtonPress-3>', self._press)
            top.bind('<Escape>', lambda e: self.close())
            top.bind('<Up>', lambda e: self._key(-1)); top.bind('<Down>', lambda e: self._key(1))
            top.bind('<Return>', lambda e: self._activate_hot())
            top.bind('<Right>', lambda e: self._open_hot_cascade())
            top.bind('<Left>', lambda e: self._close_last() if len(self.wins) > 1 else None)
            try:
                top.grab_set()
            except tk.TclError:
                top.after(50, lambda: top.winfo_exists() and top.grab_set())
            top.focus_force()
            self._watch()
        return top

    def _row_at(self, xr, yr):
        w = self.root.winfo_containing(xr, yr)
        while w is not None and not hasattr(w, '_menu_row'):
            w = getattr(w, 'master', None)
        if w is None:
            return None
        lvl, i = w._menu_row
        return (lvl, i) if lvl < len(self.wins) and i < len(self.wins[lvl][2]) else None

    def _paint(self, lvl, i, on):
        r, labs, it, dis = self.wins[lvl][2][i]
        bg = C['select'] if on and not dis else C['field']
        r.configure(background=bg)
        for l in labs:
            l.configure(background=bg)
            if l.winfo_class() == 'Label' and l.cget('text') not in ('✓', '•', '›') and not dis and l is labs[1]:
                l.configure(foreground=C['on_select'] if on else C['text'])

    def _set_hot(self, hot):
        if hot == self.hot:
            return
        if self.hot and self.hot[0] < len(self.wins):
            self._paint(*self.hot, False)
        self.hot = hot
        if hot:
            self._paint(*hot, True)
            lvl, i = hot
            while len(self.wins) > lvl + 1:                     # leave deeper submenus
                self._close_last()
            it = self.wins[lvl][2][i][2]
            if it['kind'] == 'cascade':
                if self._after: self.root.after_cancel(self._after)
                self._after = self.root.after(180, lambda h=hot: self.hot == h and self._open_cascade(*h))

    def _open_cascade(self, lvl, i):
        r = self.wins[lvl][2][i][0]
        it = self.wins[lvl][2][i][2]
        if len(self.wins) > lvl + 1 or not it['menu'] or not it['menu'].items:
            return
        self.open(it['menu'], r.winfo_rootx() + r.winfo_width() - 2, r.winfo_rooty() - 5, level=lvl + 1)

    def _motion(self, e):
        hot = self._row_at(e.x_root, e.y_root)
        if hot is not None:
            self._set_hot(hot)

    def _press(self, e):
        if self._row_at(e.x_root, e.y_root) is None:
            self.close()

    def _release(self, e):
        hot = self._row_at(e.x_root, e.y_root)
        if hot is None:
            return
        self._activate(*hot)

    def _activate(self, lvl, i):
        r, labs, it, dis = self.wins[lvl][2][i]
        if dis:
            return
        if it['kind'] == 'cascade':
            self._open_cascade(lvl, i); return
        self.close()
        v = it.get('var')
        if it['kind'] == 'check' and v is not None:
            on = it['on'] if it['on'] is not None else True
            off = it['off'] if it['off'] is not None else False
            v.set(off if self._was_checked(it) else on)
        elif it['kind'] == 'radio' and v is not None:
            v.set(it['value'])
        if it.get('command'):
            self.root.after_idle(it['command'])

    @staticmethod
    def _was_checked(it):
        try:
            cur = it['var'].get()
        except tk.TclError:
            return False
        return cur == it['on'] if it['on'] is not None else bool(cur) and cur not in ('0', 'False')

    def _key(self, d):
        lvl = len(self.wins) - 1
        rows = self.wins[lvl][2]
        if not rows: return
        i = self.hot[1] if self.hot and self.hot[0] == lvl else (-1 if d > 0 else 0)
        for _ in rows:
            i = (i + d) % len(rows)
            if not rows[i][3]:
                break
        self._set_hot((lvl, i))

    def _activate_hot(self):
        if self.hot: self._activate(*self.hot)

    def _open_hot_cascade(self):
        if self.hot and self.wins[self.hot[0]][2][self.hot[1]][2]['kind'] == 'cascade':
            self._open_cascade(*self.hot)
            if len(self.wins) > self.hot[0] + 1:
                self._set_hot((self.hot[0] + 1, 0))

    def _close_last(self):
        top = self.wins.pop()[0]
        if self.hot and self.hot[0] >= len(self.wins):
            self.hot = None
        if not self.wins:
            try:
                top.grab_release()
            except tk.TclError:
                pass
        top.destroy()

    def close(self):
        while self.wins:
            self._close_last()

    def _watch(self):
        """Close when SmartKit loses focus (click in another program) or its window moves."""
        if not self.wins:
            return
        try:
            geo = self.root.winfo_geometry()
            if self.root.focus_displayof() is None or geo != getattr(self, '_geo', geo):
                self.close(); return
            self._geo = geo
        except (tk.TclError, KeyError):
            self.close(); return
        self.root.after(250, self._watch)
