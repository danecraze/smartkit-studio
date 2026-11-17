"""SmartKit Studio v0.4 – turn any drum VST3 kit (Superior Drummer 3, Steven Slate Drums ...) into an
Alesis Strike / Strike Pro kit that fits the module's 200 MB sample memory.

Double-click "SmartKit Studio.bat" to start.
"""
import os, sys, json, re, threading, queue, time, traceback, types
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
import host as H
import smartkit as SK
import sd3state, sd3names
import sources as SRC
import theme as T
import levelcal

if sys.platform == 'win32':                     # own taskbar entry (with SmartKit's icon, not Python's) –
    try:                                        # must be set before the first window exists
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('SmartKitStudio.App')
    except Exception:
        pass
from analyse import load_articulation, dedupe, read_wav, measure, guess_role
from plan import Artic, WEIGHT

VERSION = '0.13'
PROJECTS = os.path.join(HERE, 'Projects')
PRESETS = os.path.join(HERE, 'Presets')
SETTINGS_DIR = os.path.join(HERE, 'Settings')
SETTINGS_FILE = os.path.join(HERE, 'studio_settings.json')
ROLES = ['kick', 'snare', 'rim', 'tom', 'hihat', 'pedal', 'crash', 'ride', 'other']
PADS = ['K1H', 'K2H', 'S1H', 'S1R', 'T1H', 'T1R', 'T2H', 'T2R', 'T3H', 'T3R', 'T4H', 'T4R',
        'C1B', 'C1E', 'C2B', 'C2E', 'C3B', 'C3E', 'R1B', 'R1E', 'R1D']
PAD_NAMES = {'K1H': 'Kick', 'K2H': 'Kick 2', 'S1H': 'Snare head', 'S1R': 'Snare rim', 'T1H': 'Tom 1', 'T1R': 'Tom 1 rim',
             'T2H': 'Tom 2', 'T2R': 'Tom 2 rim', 'T3H': 'Tom 3', 'T3R': 'Tom 3 rim', 'T4H': 'Tom 4', 'T4R': 'Tom 4 rim',
             'C1B': 'Crash 1 bow', 'C1E': 'Crash 1 edge', 'C2B': 'Crash 2 bow', 'C2E': 'Crash 2 edge',
             'C3B': 'Crash 3 bow', 'C3E': 'Crash 3 edge', 'R1B': 'Ride bow', 'R1E': 'Ride edge', 'R1D': 'Ride bell'}
HAT_SLOTS = (['H1B closed'] + [f'H1B open {i}' for i in range(1, 6)] +
             ['H1E closed'] + [f'H1E open {i}' for i in range(1, 6)] + ['H1F chick', 'H1F splash'])
INST_ONLY = 'INST'          # 'pad' value: build the instrument but don't put it in the kit
HAT_SLOT_NAMES = {'H1B': 'Hi-hat bow', 'H1E': 'Hi-hat edge', 'H1F': 'Hi-hat pedal'}
STEREO_MODES = ['mono', 'stereo if wide', 'stereo']
DEFAULT_STEREO = {'crash': 'stereo if wide', 'ride': 'stereo if wide', 'hihat': 'stereo if wide'}
TYPE_NAMES = {'kick': 'Kick', 'snare': 'Snare', 'rim': 'Rim / sidestick', 'tom': 'Toms', 'hihat': 'Hi-hat',
              'pedal': 'Hi-hat pedal', 'crash': 'Crash / china / splash', 'ride': 'Ride', 'other': 'Other'}
MEMORY_HELP = (
    "How the memory is used: the Strike loads every sample of a kit into its 200 MB sample memory before the "
    "kit plays, so everything has to fit at once. SmartKit starts every sound at the smallest setting (3 velocity "
    "layers, 1 take, short tails), then hands out upgrades one at a time: more velocity layers (smoother "
    "dynamics), more takes per layer (round robin, less machine-gun) and longer tails (more natural decay). Each "
    "upgrade goes to the sound where it buys the most sound quality per MB, multiplied by that type's priority, "
    "until the memory is full.\n"
    "Priority: 10 = upgraded first, 5 = half as keen, 0 = always the smallest setting.  Stereo doubles a sound's "
    "memory; 'stereo if wide' keeps stereo only when the recording really is wide (cymbals, overheads).")
COMBINE_MODES = ['Combine into one instrument', 'Layer A + Layer B']
FOLDER_MODES = ['A folder per type: <kit> KICKS, <kit> SNARES …', 'One folder for the whole kit',
                'Shared type folders: all KICKS, all SNARES …',
                'Kit folder with type subfolders: <kit>\\CRASH, <kit>\\SNARE …']
FOLDER_NESTED = FOLDER_MODES[3]
COMP_MODES = ['More layers for the hard hits + restore loudness steps', 'More layers for the hard hits only', 'Off']
LEVEL_MODES = ['Keep the kit balance (one gain for all)', 'Maximise every instrument (each to -1 dBFS)',
               "Every instrument at full level, kit pads keep the plugin's mix"]

# ---- Strike settings (tab 4): per type layer defaults, written into each instrument and the kit pads
REVERB_TYPES = ['OFF', 'AmbBrite', 'BdSpring', 'BigGate', 'CloseMic', 'FxGate', 'HugeSpac', 'LgSpacy', 'Md80sRm',
                'MdHardRm', 'MdSoftRm', 'MetalCav', 'RmSmlDrk', 'RoomGate', 'SeaWolf', 'Slapper', 'SmBathRm', 'SmPlate',
                'SmlBrite', 'Studio', 'Warehous', 'WoodRM', 'WrmStudio']
COMP_TYPES = ['OFF', 'Master 1', 'Radio 1', 'Radio 2', 'Soft Hyper', 'Bright', 'Country', 'Crunch', 'Dance', 'Hip Hop',
              'Jazz', 'Lo Boost', 'Rock 1', 'Rock 2', 'Rock 3']
EQ_FREQS = ('20 22 24 26 28 32 36 40 44 50 58 66 76 86 98 110 120 140 160 180 210 230 260 290 320 360 400 440 490 '
            '530 580 640 700 760 820 890 970 1.0k 1.1k 1.2k 1.3k 1.4k 1.5k 1.6k 1.7k 1.8k 1.9k 2.0k 2.2k 2.3k 2.4k '
            '2.6k 2.7k 2.9k 3.0k 3.2k 3.4k 3.6k 3.8k 4.0k 4.2k 4.4k 4.6k 4.8k 5.0k 5.3k 5.5k 5.8k 6.0k 6.3k 6.6k '
            '6.9k 7.2k 7.5k 7.8k 8.1k 8.4k 8.7k 9.1k 9.4k 9.8k 10.2k 10.5k 10.9k 11.3k 11.7k 12.1k 12.6k 13.0k '
            '13.4k 13.9k 14.4k 14.8k 15.3k 15.8k 16.3k 16.9k 17.4k 17.9k 18.5k').split()
# (key, column title, layer_bytes keyword or pad offset, min, max, default)
LAYER_COLS = [('level', 'Level', 'level', 0, 99, 90), ('pan', 'Pan', 'pan', -50, 50, 0),
              ('decay', 'Decay', 'decay', 0, 99, 98), ('semi', 'Semi', 'semitone', -12, 12, 0),
              ('fine', 'Fine', 'fine', -50, 50, 0), ('cutoff', 'Cutoff', 'cutoff', 0, 99, 99),
              ('vlevel', 'Vel→Level', 'vel_level', 0, 99, 0), ('vdecay', 'Vel→Decay', 'vel_decay', -99, 99, 0),
              ('vfilter', 'Vel→Filter', 'vel_filter', -99, 99, 0), ('vtune', 'Vel→Pitch', 'vel_tune', -99, 99, 0),
              ('vlo', 'Vel low', 'vel_lo', 0, 127, 0), ('vhi', 'Vel high', 'vel_hi', 127, 127, 127),
              ('rev', 'Reverb send', 44, 0, 99, 0)]
LAYER_COLS[-2] = ('vhi', 'Vel high', 'vel_hi', 0, 127, 127)
STRIKE_HELP = (
    "Written into every instrument (its defaults) and into the kit pads. Level, Decay (99 = full length), "
    "Semi/Fine (pitch), Cutoff (99 = filter open). Vel→Level 0 = the loudness changes come only from the "
    "recorded samples, as in the plugin (recommended); higher values make soft hits softer still. "
    "Vel low/high limit the velocities a pad answers to. Reverb send uses the kit reverb below.")
# MIDI notes the module sends for the hi-hat (factory kits: bow 8, edge 7, pedal 22)
HAT_NOTES = {'H1B': 8, 'H1E': 7, 'H1F': 22}

STEP_TEXT = {
    'plugin': "Sounds can come from a drum plugin (top) and/or from samples you already have (bottom) – or both "
              "mixed in one kit.\n"
              "KIT: everything belongs to the kit named top right – type to rename it, pick another from the list, File → New kit for a fresh one.\n"
              "PLUGIN: 1. Pick your drum plugin.   2. Press Load plugin (Superior Drummer takes about "
              "a minute).   3. Press Open plugin window, load the kit/preset you want, wait until it has finished "
              "loading, then press  ✔ Kit loaded – continue  in the small SmartKit window (top right). "
              "Turn off humanize/randomising in the plugin.\n"
              "Next time you can press Use saved kit instead of opening the window.\n"
              "SAMPLES: add a sample folder (e.g. a folder in Samples on the SD card), a sampler instrument (SFZ, "
              "Decent Sampler, Hydrogen kit), Strike instruments (.sin) to rebuild with the new codes and memory "
              "plan, or long recordings (one drum played soft to loud) that are cut into single hits. No plugin "
              "and no recording needed for these – their sounds appear on tab 2.",
    'sounds': "Press Find sounds for the plugin's sounds (Superior Drummer / EZdrummer: read from the plugin; other "
              "plugins: every MIDI note is tried). Sounds from sample sources (tab 1) are listed too and stay when you "
              "press Find sounds again.\n"
              "Click ☐ to switch a sound on/off · double-click a name to rename · right-click the type or Strike pad "
              "to change it · Space or ▶ to listen. Values marked * were chosen automatically – check them by ear.\n"
              "'Sound in the plugin' = articulation · drum (SD3 code). Strike names = 5-letter code + drum "
              "(type first, then articulation: SNRHD_ snare head, SNRRI_ rimshot, SNRXS_ cross-stick, TOMHD_, KCKHD_, "
              "HHBCL_ hi-hat bow closed, HHBO1_ bow open 1, HHECL_ edge closed, HHPCL_ pedal chick, CRSED_, RIDBW_ …). "
              "Articulations switched off in the plugin are left out. Pad 'Instrument only' saves a sound as a user instrument without putting it in the kit "
              "(e.g. a rimshot you may swap in later). Type sets memory priority, stereo for cymbals and hi-hat building.",
    'settings': "Defaults are a good start. More velocities and takes give the memory planner more to choose from "
                "but take longer to record. Memory is the total sample memory the kit may use (the Strike Pro has "
                "200 MB; 196 leaves a small safety margin). Below: which drums get memory first, and which "
                "may stay stereo.",
    'strike': "How the instruments and the kit are set up on the module: amp, pitch, filter and velocity settings per "
              "type of drum, and the kit effects. Everything can still be changed on the module or in the editor.",
    'build': "Record + build does both in one go. Record plays every used sound at every chosen velocity (sounds already recorded are skipped unless "
             "you tick re-record). Build then plans the memory and writes Kits, Instruments and Samples to the "
             "output folder – pick the SD card to put it straight on the module.\n"
             "When the card goes back into the module it re-reads the user kits, which takes a moment.",
}


def safe_name(s):
    """Kit / project folder name (never '.', '..' or empty, so it always stays inside Projects)."""
    return SK.safe(s, 26, fallback='Kit')


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f'SmartKit Studio {VERSION} – drum VST to Alesis Strike')
        self.geometry('1080x790'); self.minsize(900, 620)
        self.host = H.DrumHost()
        self.q = queue.Queue()
        self.busy = False
        self.cancel_flag = False
        self.rows = {}
        self.layout = []          # articulations read from the plugin
        self.sources = []         # sample sources (folders, SFZ, Strike instruments …) added on tab 1
        self.editor = None
        try:
            self.st = json.load(open(SETTINGS_FILE))
        except Exception:
            self.st = {}
        self.v_theme = tk.StringVar(value=self.st.get('theme', 'dark'))
        T.apply(self, self.v_theme.get())
        T.title_bar(self)
        self.set_icon()
        self.make_menu()
        sb = ttk.Frame(self, style='Bar.TFrame'); sb.pack(fill='x', side='bottom')
        ttk.Separator(sb).pack(fill='x', side='top')
        self.status = tk.StringVar(value='Ready.')
        ttk.Label(sb, textvariable=self.status, anchor='w', style='Bar.TLabel').pack(side='left', fill='x', expand=True,
                                                                                    padx=12, pady=5)
        self.busybar = ttk.Progressbar(sb, mode='indeterminate', length=160)
        nb = ttk.Notebook(self, style='Steps.TNotebook')
        self.steps = T.StepBar(self, nb); self.steps.pack(fill='x', side='top')
        ttk.Separator(self).pack(fill='x', side='top')
        nb.pack(fill='both', expand=True)
        _add = nb.add
        nb.add = lambda child, **kw: (_add(child, **kw), self.steps.add(kw.get('text', '')))
        self.nb = nb
        self.tab_plugin(nb); self.tab_sounds(nb); self.tab_settings(nb); self.tab_strike(nb); self.tab_build(nb)
        self.retag()
        self.after(100, self.pump)
        self.protocol('WM_DELETE_WINDOW', self.on_close)
        self.refresh_project()

    # ============================================================ helpers
    def instructions(self, parent, key):
        """The help text at the top of a step; click 'What to do' to fold it away (remembered)."""
        f = ttk.Frame(parent); f.pack(fill='x', padx=16, pady=(12, 6))
        head = ttk.Label(f, style='HelpHead.TLabel', cursor='hand2')
        head.pack(anchor='w')
        body = T.WrapLabel(f, text=STEP_TEXT[key], style='Help.TLabel')
        if not hasattr(self, 'help_parts'):
            self.help_parts = []
        self.help_parts.append((head, body))
        self.show_help()

        def toggle(_e=None):
            self.st['help'] = not self.st.get('help', True); self.show_help(); self.save_settings()
        head.bind('<Button-1>', toggle)
        head.bind('<Enter>', lambda e: head.state(['active'])); head.bind('<Leave>', lambda e: head.state(['!active']))

    def show_help(self):
        on = self.st.get('help', True)
        for h, b in self.help_parts:
            h.configure(text=('▾  WHAT TO DO' if on else '▸  WHAT TO DO  (click to show)'))
            if on: b.pack(fill='x', anchor='w', pady=(4, 0))
            else: b.pack_forget()

    def page(self, nb, title):
        """A notebook page that scrolls when the window is too small for it."""
        p = T.ScrollPage(nb); nb.add(p, text=title)
        return p.body

    def set_icon(self):
        T.app_icon(self)

    def set_theme(self):
        T.apply(self, self.v_theme.get())
        self.retag(); self.save_settings()

    def retag(self):
        if hasattr(self, 'tree'):
            self.tree.tag_configure('off', foreground=T.C['faint'])
            self.tree.tag_configure('group', font=T.F['semi'])

    def project_dir(self):
        return os.path.join(PROJECTS, safe_name(self.v_kit.get()))

    def save_settings(self):
        keys = ['plugin', 'kit', 'notes', 'vstep', 'reps', 'budget', 'curve', 'gain', 'hat', 'out',
                'template', 'combine', 'extra_mb', 'levels', 'fill_empty', 'loadwait', 'inst_only', 'folders',
                'comp', 'comp_db']
        d = {k: getattr(self, 'v_' + k).get() for k in keys if hasattr(self, 'v_' + k)}
        if hasattr(self, 'v_prio'):
            d['priority'] = {r: v.get() for r, v in self.v_prio.items()}
            d['stereo_by_type'] = {r: v.get() for r, v in self.v_ster.items()}
        d['load_seconds'] = self.st.get('load_seconds', 70)
        d['folders_v10'] = True
        if hasattr(self, 'v_theme'): d['theme'] = self.v_theme.get()
        d['help'] = self.st.get('help', True)
        if hasattr(self, 'v_layer'):
            d['layer'] = {r: {k: v.get() for k, v in cols.items()} for r, cols in self.v_layer.items()}
            d['kitfx'] = {k: v.get() for k, v in self.v_fx.items()}
        try:
            json.dump(d, open(SETTINGS_FILE, 'w'), indent=1)
        except Exception:
            pass

    def settings_dict(self):
        self.save_settings()
        try:
            return json.load(open(SETTINGS_FILE))
        except Exception:
            return {}

    def save_settings_as(self):
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        p = filedialog.asksaveasfilename(initialdir=SETTINGS_DIR, defaultextension='.json',
                                         filetypes=[('SmartKit settings', '*.json')], title='Save settings')
        if not p: return
        d = self.settings_dict()
        for k in ('plugin', 'kit', 'out', 'load_seconds'):     # machine / project specific: not part of a settings file
            d.pop(k, None)
        json.dump(d, open(p, 'w'), indent=1)
        self.status.set(f'Settings saved: {os.path.basename(p)}')

    def load_settings_from(self):
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        p = filedialog.askopenfilename(initialdir=SETTINGS_DIR, filetypes=[('SmartKit settings', '*.json')],
                                       title='Load settings')
        if not p: return
        try:
            d = json.load(open(p))
        except Exception as e:
            messagebox.showerror('SmartKit', f'Could not read {p}:\n{e}'); return
        for k, v in d.items():
            if hasattr(self, 'v_' + k) and isinstance(v, str):
                getattr(self, 'v_' + k).set(v)
        for r, v in d.get('priority', {}).items():
            if r in getattr(self, 'v_prio', {}): self.v_prio[r].set(v)
        for r, v in d.get('stereo_by_type', {}).items():
            if r in getattr(self, 'v_ster', {}): self.v_ster[r].set(v)
        for r, cols in d.get('layer', {}).items():
            for k, v in cols.items():
                if r in getattr(self, 'v_layer', {}) and k in self.v_layer[r]: self.v_layer[r][k].set(v)
        for k, v in d.get('kitfx', {}).items():
            if k in getattr(self, 'v_fx', {}): self.v_fx[k].set(v)
        self.save_settings()
        self.status.set(f'Settings loaded: {os.path.basename(p)}')

    def var(self, name, default):
        val = self.st.get(name, default)
        if name == 'folders' and val == FOLDER_MODES[0] and not self.st.get('folders_v10'):
            val = FOLDER_NESTED                  # v0.10: new default, <kit>\CRASH, <kit>\SNARE …
        v = tk.StringVar(value=val); setattr(self, 'v_' + name, v); return v

    def log(self, s):
        self.q.put(('log', s))
        try:                                     # also keep a log file in the project folder
            d = getattr(self, 'proj_dir', None) or self.project_dir()   # plain attribute: safe from worker threads
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, 'log.txt'), 'a', encoding='utf-8') as f:
                f.write(time.strftime('%H:%M:%S ') + s + '\n')
        except Exception:
            pass

    def set_busy(self, on, text=None):
        if on:
            self.busybar.pack(side='right', padx=12, pady=5); self.busybar.start(12)
        else:
            self.busybar.stop(); self.busybar.pack_forget()
        if text:
            self.status.set(text)

    def run_bg(self, fn, done=None, text='Working …'):
        if self.busy:
            messagebox.showinfo('SmartKit', 'Still busy – wait or press Stop.'); return
        self.busy = True; self.cancel_flag = False
        self.set_busy(True, text)

        def work():
            try:
                r = fn()
                self.q.put(('done', (done, r)))
            except H.Cancelled:
                self.q.put(('log', 'Stopped.')); self.q.put(('done', (None, None)))
            except Exception:
                self.log('ERROR:\n' + traceback.format_exc()); self.q.put(('done', (None, None)))
                self.q.put(('error', 'Something went wrong – see the log on the Record & build tab\n(also saved as log.txt in '
                           + str(getattr(self, 'proj_dir', '') or PROJECTS) + ').'))
        threading.Thread(target=work, daemon=True).start()

    def progress(self, i, n, text):
        self.q.put(('progress', (i, n, text)))

    def pump(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == 'log':
                    self.logbox.insert('end', val + '\n'); self.logbox.see('end')
                elif kind == 'status':
                    self.status.set(val)
                elif kind == 'progress':
                    i, n, text = val
                    for pb in (self.pbar, self.pbar2):
                        pb['maximum'] = max(n, 1); pb['value'] = i
                    self.status.set(text)
                elif kind == 'done':
                    self.busy = False
                    self.set_busy(False)
                    for pb in (self.pbar, self.pbar2):
                        pb['value'] = 0
                    self.status.set('Ready.')
                    cb, r = val
                    if cb: cb(r)
                elif kind == 'error':
                    messagebox.showerror('SmartKit', val)
        except queue.Empty:
            pass
        self.after(100, self.pump)

    def make_menu(self):
        bar = ttk.Frame(self, style='Bar.TFrame'); bar.pack(fill='x', side='top')
        ttk.Label(bar, text='SmartKit Studio', style='BarTitle.TLabel').pack(side='left', padx=(14, 4), pady=6)
        ttk.Label(bar, text=VERSION, style='BarMuted.TLabel').pack(side='left', padx=(0, 14), pady=(8, 6))

        def menu(label):
            m = T.Menu(self)
            b = ttk.Button(bar, text=label, style='BarMenu.TButton', takefocus=False,
                           command=lambda: m.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height()))
            b.pack(side='left')
            return m
        # the kit = the project: its name sits in the header, on every step
        kb = ttk.Frame(bar, style='Bar.TFrame'); kb.pack(side='right', padx=(0, 14), pady=6)
        ttk.Label(kb, text='KIT', style='KitLabel.TLabel').pack(side='left', padx=(0, 8))
        self.v_kit = self.var('kit', 'My SD3 Kit')
        self.v_kit.trace_add('write', lambda *a: len(self.v_kit.get()) > 26 and self.v_kit.set(self.v_kit.get()[:26]))
        self.kit_box = ttk.Combobox(kb, textvariable=self.v_kit, width=26, font=T.F['title'], style='Kit.TCombobox',
                                    postcommand=self.fill_kit_list)
        self.kit_box.pack(side='left')
        self.kit_box.bind('<FocusOut>', lambda ev: self.kit_renamed())
        self.kit_box.bind('<Return>', lambda ev: (self.kit_renamed(), self.focus_set()))
        self.kit_box.bind('<<ComboboxSelected>>', lambda ev: self.open_kit())
        self.kit_tip = ttk.Label(kb, text='', style='BarMuted.TLabel'); self.kit_tip.pack(side='left', padx=(10, 0))
        fm = menu('File')
        fm.add_command(label='New kit…', command=self.new_kit)
        fm.add_command(label='Clean up this kit\'s project files…', command=self.cleanup_project)
        fm.add_separator()
        fm.add_command(label='Open preset…', command=self.load_preset, accelerator='Ctrl+O')
        fm.add_command(label='Save preset…', command=self.save_preset, accelerator='Ctrl+S')
        fm.add_separator()
        fm.add_command(label='Save settings…', command=self.save_settings_as)
        fm.add_command(label='Load settings…', command=self.load_settings_from)
        fm.add_separator()
        fm.add_command(label='Open project folder', command=lambda: self.open_path(self.project_dir()))
        fm.add_command(label='Open log file', command=lambda: self.open_path(os.path.join(self.project_dir(), 'log.txt')))
        fm.add_command(label='Open output folder / SD card', command=lambda: self.open_path(self.v_out.get()))
        fm.add_separator()
        fm.add_command(label='Close', command=self.on_close, accelerator='Alt+F4')
        vm = menu('View')
        vm.add_radiobutton(label='Dark', variable=self.v_theme, value='dark', command=self.set_theme)
        vm.add_radiobutton(label='Light', variable=self.v_theme, value='light', command=self.set_theme)
        hm = menu('Help')
        hm.add_command(label='Read me', command=lambda: self.open_path(os.path.join(HERE, 'USER_GUIDE.txt')))
        hm.add_command(label='About', command=lambda: messagebox.showinfo(
            'SmartKit Studio', f'SmartKit Studio {VERSION}\nTurns a drum VST3 kit or your own samples into an Alesis Strike / '
            'Strike Pro kit.\n\nFree, open source (MIT licence). Not affiliated with or endorsed by Alesis, inMusic or '
            'Toontrack; all trademarks belong to their owners. Use it only with sounds you are licensed to use.'))
        self.bind_all('<Control-o>', lambda e: self.load_preset())
        self.bind_all('<Control-s>', lambda e: self.save_preset())

    def notify(self, title, text):
        """Finished: bring SmartKit to the front, beep and show a message (even if another window is on top)."""
        try:
            self.deiconify(); self.lift(); self.attributes('-topmost', True)
            self.after(500, lambda: self.attributes('-topmost', False))
            self.bell()
            if sys.platform == 'win32':
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass
        messagebox.showinfo(f'SmartKit – {title}', text, parent=self)

    def open_path(self, p):
        if not p or not os.path.exists(p):
            messagebox.showinfo('SmartKit', f'Not found yet:\n{p}'); return
        try:
            os.startfile(p)
        except Exception as e:
            messagebox.showinfo('SmartKit', f'{p}\n\n{e}')

    def on_close(self):
        if self.busy and not messagebox.askyesno('SmartKit', 'SmartKit is still working. Close anyway?'):
            return
        try:
            self.save_settings(); self.save_map()
        except Exception:
            pass
        self.destroy()

    def stop(self):
        self.cancel_flag = True

    # ============================================================ tab 1: plugin
    def tab_plugin(self, nb):
        t = self.page(nb, '1 · Sources')
        self.instructions(t, 'plugin')
        f = ttk.Frame(t); f.pack(fill='x', padx=12, pady=6)
        self.plugins = H.find_plugins()
        names = [os.path.basename(p) for p in self.plugins]
        ttk.Label(f, text='Drum plugin (VST3)').grid(row=0, column=0, sticky='w')
        self.v_plugin = self.var('plugin', names[0] if names else '')
        ttk.Combobox(f, textvariable=self.v_plugin, values=names, state='readonly', width=50).grid(row=0, column=1, sticky='w')
        b = ttk.Frame(t); b.pack(fill='x', padx=12, pady=8)
        ttk.Button(b, text='Load plugin', style='Accent.TButton', command=self.do_load).pack(side='left', padx=4)
        ttk.Button(b, text='Open plugin window (choose kit)', command=self.do_editor).pack(side='left', padx=4)
        self.btn_restore = ttk.Button(b, text='Use saved kit', command=self.do_restore)
        self.btn_restore.pack(side='left', padx=4)
        self.plugin_info = tk.StringVar(value='No plugin loaded.')
        ttk.Label(t, textvariable=self.plugin_info, style='Head.TLabel').pack(anchor='w', padx=14, pady=(6, 2))
        self.loadbar = ttk.Progressbar(t, length=500)
        self.loadbar.pack(anchor='w', padx=14, pady=4)
        T.WrapLabel(t, style='Small.TLabel', text=(
            "About 'Audio Engine Inactive': a plugin only shows that when no audio is flowing. SmartKit now feeds "
            "it silent audio while its window is open, so the message should be gone. It never affects the "
            "recordings, because audio always flows while SmartKit records.")).pack(fill='x', anchor='w', padx=14, pady=8)
        if not self.plugins:
            self.plugin_info.set('No VST3 plugins found in ' + ' or '.join(H.VST3_DIRS))
        sf = ttk.LabelFrame(t, text='Sample sources – sounds you already have (no plugin, no recording needed)')
        sf.pack(fill='both', expand=True, padx=12, pady=8)
        sb = ttk.Frame(sf); sb.pack(fill='x', padx=6, pady=4)
        ttk.Button(sb, text='Add folder…', command=self.add_folder).pack(side='left', padx=3)
        ttk.Button(sb, text='Add SFZ / Decent Sampler / Hydrogen…', command=self.add_sampler).pack(side='left', padx=3)
        ttk.Button(sb, text='Add Strike instruments…', command=self.add_sin).pack(side='left', padx=3)
        ttk.Button(sb, text='Add recordings to cut…', command=self.add_long).pack(side='left', padx=3)
        ttk.Button(sb, text='Remove', command=self.remove_source).pack(side='right', padx=3)
        self.src_list = T.register(tk.Listbox(sf, height=6, font=T.F['ui']))
        self.src_list.pack(fill='both', expand=True, padx=6, pady=(0, 6))
        T.WrapLabel(sf, style='Small.TLabel', text=(
            "File names are read the way common drum converters name them ('<drum>_<id> <CODE> <number>v<velocity>', "
            "e.g. Sn, SnR, SnSS, T1, HBC, HEO2, HCH, HSP, Ri1B, C1E), or by their words (kick, snare, rim, tom, hat, "
            "open, pedal, crash, ride, bell, china, splash, choke …). Left/right file pairs become stereo; 44.1/96 kHz "
            "samples are converted to 48 kHz. Check the type and code on tab 2 (right-click a sound).")
                  ).pack(fill='x', anchor='w', padx=8, pady=(0, 6))

    # ---------- kits (= projects)
    def kit_names(self):
        try:
            return sorted((d for d in os.listdir(PROJECTS)
                           if os.path.isdir(os.path.join(PROJECTS, d)) and not d.startswith('_')), key=str.lower)
        except OSError:
            return []

    def fill_kit_list(self):
        self.kit_box['values'] = self.kit_names()

    def open_kit(self):
        """A kit picked from the list: save the open one, then open the picked one."""
        if os.path.normcase(self.project_dir()) == os.path.normcase(getattr(self, 'proj_dir', '') or ''):
            return
        if self.busy:
            self.v_kit.set(os.path.basename(self.proj_dir))
            messagebox.showinfo('SmartKit', 'Still busy – wait or press Stop.'); return
        self.save_map()                                  # goes to the kit that was open
        self.refresh_project(); self.save_settings()
        self.status.set(f'Opened kit "{self.v_kit.get()}".')
        self.focus_set()

    def new_kit(self):
        if self.busy:
            messagebox.showinfo('SmartKit', 'Still busy – wait or press Stop.'); return
        name = T.ask_string(self, 'New kit', 'Name of the new kit (max 26 letters):', maxlen=26)
        if not name: return
        name = safe_name(name)[:26]
        self.save_map()
        self.v_kit.set(name); self.refresh_project(); self.save_settings()
        self.status.set(f'Kit "{name}" opened.' if self.rows or self.sources else f'New kit "{name}" – add its sounds on step 1.')
        self.nb.select(0)

    @staticmethod
    def folder_mb(p):
        n = 0
        if os.path.isfile(p):
            return os.path.getsize(p) / 2 ** 20
        for root, _d, files in os.walk(p):
            for f in files:
                try:
                    n += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        return n / 2 ** 20

    def cleanup_project(self):
        """Free disk space after the kit is built and tested: recordings, test hits, or the whole project."""
        if self.busy:
            messagebox.showinfo('SmartKit', 'Still busy – wait or press Stop.'); return
        self.kit_renamed()
        p, kit = self.proj_dir, self.v_kit.get()
        if not os.path.isdir(p):
            messagebox.showinfo('SmartKit', f'"{kit}" has no project files.'); return
        out = os.path.join(p, 'output')
        rec = [os.path.join(p, 'renders')]
        tst = [os.path.join(p, x) for x in ('probe', '_preview.wav')]
        mb = lambda paths: sum(self.folder_mb(x) for x in paths if os.path.exists(x))
        all_mb, rec_mb, tst_mb, out_mb = self.folder_mb(p), mb(rec), mb(tst), mb([out])
        def inside(child, parent):
            try:
                c, q = os.path.normcase(os.path.abspath(child)), os.path.normcase(os.path.abspath(parent))
                return os.path.commonpath([c, q]) == q
            except ValueError:                                # different drives
                return False
        if not inside(p, PROJECTS) or os.path.normcase(os.path.abspath(p)) == os.path.normcase(os.path.abspath(PROJECTS)):
            messagebox.showerror('SmartKit', f'Not cleaning {p}: it is not a kit folder inside Projects.'); return
        out_used = inside(self.v_out.get().strip() or out, p)

        d = T.Dialog(self, 'Clean up project files')
        ttk.Label(d.body, text=f'Project files of "{kit}"  –  {all_mb:,.0f} MB', style='Title.TLabel').pack(anchor='w')
        T.WrapLabel(d.body, style='Help.TLabel', wraplength=470, text=(
            'Test the kit on the module first. These files are only needed to change the kit and build it again. '
            'The SD card, your sample folders and the plugin are not touched. Files go to the Recycle Bin.')
                    ).pack(fill='x', anchor='w', pady=(4, 12))
        opts = []

        def opt(text, sub, paths, size, on):
            v = tk.BooleanVar(value=on and size > 0)
            f = ttk.Frame(d.body); f.pack(fill='x', anchor='w', pady=3)
            c = ttk.Checkbutton(f, text=f'{text}  –  {size:,.0f} MB', variable=v); c.pack(anchor='w')
            if size <= 0 and paths: c.state(['disabled'])
            ttk.Label(f, text=sub, style='Small.TLabel').pack(anchor='w', padx=(26, 0))
            opts.append((v, paths)); return v
        v_rec = opt('Plugin recordings', 'Rebuilding with other settings would need the sounds recorded again.',
                    rec, rec_mb, True)
        v_tst = opt('Test hits from Find sounds', 'Made again by pressing Find sounds.', tst, tst_mb, True)
        v_out = None
        if out_mb > 0:
            v_out = opt('Kit built into the project folder (output)',
                        'Only if you copied it to the SD card already.', [out], out_mb, False)
        v_all = opt('The whole project', 'Sound list, pad choices, saved plugin kit and log – the kit leaves the '
                    'kit list. Presets and settings files stay.', [p], all_mb, False)

        def sync(*_):                                    # 'whole project' includes the others
            for v, _p in opts[:-1]:
                if v_all.get(): v.set(True)
        v_all.trace_add('write', sync)
        d.button('Move to Recycle Bin', lambda: d.ok(True), accent=True)
        d.button('Cancel', d.cancel)
        if not d.show():
            return
        paths = [p] if v_all.get() else [x for v, ps in opts[:-1] if v.get() for x in ps]
        if not paths:
            return
        if v_all.get() and out_used and out_mb > 0 and not messagebox.askyesno(
                'SmartKit', 'The built kit is inside this project folder and goes too. Continue?'):
            return
        freed = mb(paths)
        try:
            T.to_recycle_bin(paths)
        except OSError as e:
            messagebox.showerror('SmartKit', str(e)); return
        if v_all.get():
            self.rows, self.layout, self.sources = {}, [], []
            self.proj_dir = None
        self.refresh_project()
        self.status.set(f'Moved {freed:,.0f} MB of project files of "{kit}" to the Recycle Bin.')

    def kit_renamed(self):
        """The kit name is also the project folder. A new name renames the project (sounds, sources and
        recordings stay); a name that already has a project asks whether to open that one instead."""
        new, old = self.project_dir(), getattr(self, 'proj_dir', None)
        if old is None or os.path.normcase(new) == os.path.normcase(old):
            return
        self.save_map()                                  # unsaved changes go to the kit that was open
        has = lambda d: any(os.path.exists(os.path.join(d, f)) for f in ('sounds.json', 'plugin_state.bin'))
        if not (self.rows or self.sources) or not has(old):
            self.refresh_project(); return               # nothing to carry over
        if has(new):
            a = messagebox.askyesnocancel('SmartKit', f'There is already a project called "{os.path.basename(new)}".\n\n'
                                          'Yes = open that project (its own sounds)\n'
                                          f'No = keep the sounds you have now and use them for "{os.path.basename(new)}" '
                                          '(its saved sound list is replaced)\nCancel = keep the old name')
            if a is None:
                self.v_kit.set(os.path.basename(old)); return
            if a:
                self.refresh_project(); return
            self.proj_dir = new; self.save_map()
            self.status.set(f'Sounds kept for "{os.path.basename(new)}".'); return
        try:
            if os.path.isdir(new):                       # e.g. only a log file there: move the project in
                import shutil
                for f in os.listdir(old):
                    if not os.path.exists(os.path.join(new, f)):
                        shutil.move(os.path.join(old, f), os.path.join(new, f))
            else:
                os.rename(old, new)                      # move everything: sounds, sources, recordings, log
            self.proj_dir = new
            self.status.set(f'Kit renamed – sounds and recordings kept ("{os.path.basename(new)}").')
        except OSError:
            self.proj_dir = new; self.save_map()        # folder in use: copy the sound list at least
            self.status.set(f'Kit renamed – sounds kept ("{os.path.basename(new)}").')

    def refresh_project(self):
        p = self.project_dir()
        self.proj_dir = p
        self.btn_restore.state(['!disabled'] if os.path.exists(os.path.join(p, 'plugin_state.bin')) else ['disabled'])
        self.rows, self.layout, self.sources = {}, [], []
        mp = os.path.join(p, 'sounds.json')
        if os.path.exists(mp):
            try:
                d = json.load(open(mp))
                self.rows = d.get('rows', {}) if isinstance(d, dict) and 'rows' in d else {}
                self.layout = d.get('layout', []) if isinstance(d, dict) else []
                self.sources = d.get('sources', []) if isinstance(d, dict) else []
            except Exception:
                pass
        sp = os.path.join(p, 'plugin_state.bin')
        if os.path.exists(sp):
            try:
                lay = sd3state.parse(open(sp, 'rb').read())
                if lay:
                    self.layout = lay
                    self.rename_auto()
                    self.tidy_rows()
            except Exception:
                pass
        if hasattr(self, 'tree'):
            self.fill_tree()
        self.fill_sources()

    # ---------- sample sources
    SRC_KIND = {'folder': 'folder', 'sfz': 'SFZ', 'dspreset': 'Decent Sampler', 'hydrogen': 'Hydrogen kit',
                'sin': 'Strike instruments', 'cut': 'recording to cut'}

    def fill_sources(self):
        if not hasattr(self, 'src_list'): return
        self.src_list.delete(0, 'end')
        for s in self.sources:
            n = sum(1 for r in self.rows.values() if r.get('srcid') == s['id'])
            self.src_list.insert('end', f"{s['id']:2d}  {self.SRC_KIND.get(s['kind'], s['kind']):18s}  {s['path']}   ({n} sounds)")

    def add_folder(self):
        p = filedialog.askdirectory(title='Sample folder (all WAV files in it and its sub-folders)')
        if p: self.add_source([p], 'folder')

    def add_sampler(self):
        p = filedialog.askopenfilenames(title='Sampler instrument', filetypes=[
            ('SFZ / Decent Sampler / Hydrogen', '*.sfz *.dspreset *.xml'), ('All files', '*.*')])
        if p: self.add_source(list(p), 'sampler')

    def add_sin(self):
        p = filedialog.askopenfilenames(title='Strike instruments (on the SD card or a copy of it)',
                                        filetypes=[('Strike instrument', '*.sin')])
        if p: self.add_source(list(p), 'sin')

    def add_long(self):
        p = filedialog.askopenfilenames(title='Recordings: one drum per file, played soft to loud',
                                        filetypes=[('WAV', '*.wav')])
        if p: self.add_source(list(p), 'cut')

    def add_source(self, paths, how):
        if self.busy:
            messagebox.showinfo('SmartKit', 'Still busy – wait or press Stop.'); return

        def job():
            found = []
            for i, p in enumerate(paths if how != 'sin' else [None]):
                if self.cancel_flag: raise H.Cancelled()
                if how == 'sin':
                    found.append(('sin', ' + '.join(os.path.basename(x) for x in paths[:3]) + (' …' if len(paths) > 3 else ''),
                                  SRC.number_drums(SRC.scan_sin(paths, self.log))))
                elif how == 'cut':
                    found.append(('cut', p, SRC.scan_long([p], self.log)))
                else:
                    self.progress(i, len(paths), f'Reading {p} …')
                    snds = SRC.scan_any(p, self.log)
                    found.append((snds[0]['src']['kind'] if snds else 'folder', p, snds))
            # level, length and a file to play for every sound (from its loudest sample)
            tot = sum(len(x[2]) for x in found); k = 0
            for _, _, snds in found:
                for s in snds:
                    k += 1
                    if k % 10 == 0: self.progress(k, tot, f'Measuring {k} of {tot} sounds …')
                    if self.cancel_flag: raise H.Cancelled()
                    f = SRC.preview_file(s['src'])
                    try:
                        aud, sr = read_wav(f)
                        env = np.abs(aud).max(1)
                        pk = float(env.max()) + 1e-12
                        s['ring'] = round(float(np.where(env > pk * 1e-3)[0][-1]) / sr, 2)
                        s['peak'] = pk
                    except Exception as e:
                        s['ring'], s['peak'] = 0.0, 1e-9
                        self.log(f'  cannot read {f}: {e}')
                    s['file'] = f
            self.progress(tot, tot, f'{tot} sounds')
            return found

        def done(found):
            if not found: return
            for kind, path, snds in found:
                if not snds:
                    self.log(f'{path}: no sounds found'); continue
                sid = max([s['id'] for s in self.sources] + [0]) + 1
                self.sources.append({'id': sid, 'kind': kind, 'path': path})
                many = len(snds) > 60                          # a whole library: tick the ones you want
                drums = {}
                for j, s in enumerate(snds):
                    gi = drums.setdefault(s['group'], len(drums))
                    key = f'S{sid:02d}{gi:03d}_{j:03d}'
                    lbl = os.path.basename(path.rstrip('/\\')) if kind not in ('sin',) else 'Strike'
                    self.rows[key] = dict(
                        key=key, note=s['note'], notes=[s['note']], group=f"{lbl} / {s['group']}", code=s['code'],
                        base=s['base'], sfx=s['sfx'], name=sd3names.fit(s['base'], s['sfx']),
                        full=f"{s['long']}  ·  {s['base']}  ({s['label'] or self.SRC_KIND.get(kind, kind)})",
                        role=s['role'], pads=[], use=not many, ring=s['ring'], peak=s['peak'], file=s['file'],
                        auto=['name', 'role', 'pads'], dup=None, src=s['src'], srcid=sid)
                self.log(f'Added {len(snds)} sounds from {path}' + (' – switched off: tick the ones you want on tab 2'
                                                                       if many else ''))
            if not any(r['pads'] for r in self.rows.values()):
                self.auto_pads(quiet=True)
            self.fill_tree(); self.fill_sources(); self.save_map()
            self.status.set('Sample sounds added – see tab 2.')
        self.run_bg(job, done, 'Reading the samples …')

    def remove_source(self):
        sel = self.src_list.curselection()
        if not sel: return
        s = self.sources[sel[0]]
        if not messagebox.askyesno('SmartKit', f"Remove {s['path']} and its sounds from this kit?\n(The files are not touched.)"):
            return
        self.sources.remove(s)
        for k in [k for k, r in self.rows.items() if r.get('srcid') == s['id']]:
            del self.rows[k]
        self.fill_tree(); self.fill_sources(); self.save_map()

    def set_code(self, key, code):
        """Change a sample sound's 5-letter code: type, name and pad suggestions follow."""
        r = self.rows[key]
        role, long, note, sd3 = SRC.describe(code, 1)
        r['sfx'], r['code'] = code, sd3 or r.get('code', '')
        r['role'] = role; r['auto'] = [x for x in r.get('auto', []) if x != 'role']
        r['note'] = note if not code.startswith(('TOM', 'CRS')) else r['note']
        r['notes'] = [r['note']]
        if 'name' in r.get('auto', []):
            r['name'] = sd3names.fit(r['base'], code)
        r['full'] = f"{long}  ·  " + r['full'].split('  ·  ', 1)[-1]
        self.refresh_row(key); self.save_map()

    def tidy_rows(self):
        """Projects from older versions: drop sounds that are switched off in the plugin and 'same as' links
        between different drums (those made a tom use a crash recording)."""
        keys = {f"{a['box']:02d}_{a['code']}" for a in self.layout}
        for k in [k for k in self.rows if re.match(r'\d\d_', k) and k not in keys]:
            del self.rows[k]
        for k, r in self.rows.items():           # the note that really plays it (E-drum map)
            a = self.art_of(k)
            if a and a.get('play') is not None:
                r['note'] = a['play']
        for k, r in self.rows.items():
            d = r.get('dup')
            if d and d.split('_')[0] != k.split('_')[0]:
                r['dup'] = None
                a = self.art_of(k)
                if a and 'name' in r.get('auto', []):
                    r['name'] = self.auto_name(a)[0]

    def art_of(self, key):
        for a in self.layout:
            if f"{a['box']:02d}_{a['code']}" == key:
                return a

    def auto_name(self, a):
        """'6.5x14 TamaBellBr80s_RIMON': drum name from the sound library + 5-letter articulation code."""
        base = a.get('drum_name') or a['inst']
        return sd3names.fit(base, sd3names.art_suffix(a['code'], a['role'], a['pos'])), base

    def full_name(self, a):
        """'Snare – 6.5x14" Tama Bell Brass 1980s – Rim only (snareRO)': for choosing pads."""
        d = a.get('drum_name') or a['inst']
        return f"{sd3names.art_long(a['code'], a['role'], a['pos'])}  ·  {d}  ({a['code']})"

    def rename_auto(self):
        for key, r in self.rows.items():
            a = self.art_of(key)
            if not a: continue
            name, base = self.auto_name(a)
            r['base'], r['sfx'] = base, sd3names.art_suffix(a['code'], a['role'], a['pos'])
            r['full'] = self.full_name(a)
            if 'name' in r.get('auto', []) and not r.get('dup'):
                r['name'] = name

    def reset_names(self):
        if not self.layout and not any(r.get('src') for r in self.rows.values()):
            messagebox.showinfo('SmartKit', 'No kit layout read from the plugin (only Superior Drummer / EZdrummer).'); return
        if not messagebox.askyesno('SmartKit', 'Name every sound after its drum in the plugin library + articulation '
                                               "code (e.g. SNRRO_6.5x14 TamaBellBr80s)?\nNames you typed are replaced."):
            return
        for r in self.rows.values():
            if 'name' not in r.setdefault('auto', []): r['auto'].append('name')
            r['dup'] = None if not r.get('dup') else r['dup']
        self.rename_auto()
        for r in self.rows.values():
            if r.get('dup'):
                a = self.art_of(r['key'])
                if a: r['name'] = self.auto_name(a)[0]
            if r.get('src'):
                r['name'] = sd3names.fit(r['base'], r['sfx'])
        self.fill_tree(); self.save_map()

    def plugin_path(self):
        for p in self.plugins:
            if os.path.basename(p) == self.v_plugin.get():
                return p

    def do_load(self):
        """Plugins must be created on the main thread (their window can only open from that thread),
        so the main window is busy meanwhile; a small separate window shows the progress."""
        path = self.plugin_path()
        if not path or self.busy:
            return
        import subprocess
        expect = float(self.st.get('load_seconds', 70))
        self.plugin_info.set(f'Loading {self.v_plugin.get()} …'); self.update()
        splash = None
        try:
            splash = subprocess.Popen([sys.executable, os.path.join(HERE, 'loading_splash.py'),
                                       f'Loading {self.v_plugin.get()} …', str(expect)])
        except Exception:
            pass
        t0 = time.time()
        try:
            try:
                wait = float(self.v_loadwait.get() or 15)
            except Exception:
                wait = 15
            name = self.host.load(path, wait=wait)
        except Exception as e:
            self.plugin_info.set(f'Could not load the plugin: {e}'); name = None
            self.log('Could not load the plugin:\n' + traceback.format_exc())
            messagebox.showerror('SmartKit', f'Could not load {self.v_plugin.get()}:\n\n{e}\n\n'
                                 'Close Superior Drummer if it is open on its own (or in another program) and try again.')
        finally:
            if splash:
                splash.terminate()
        if name:
            secs = time.time() - t0
            self.log(f'{name} loaded in {secs:.0f} s')
            self.st['load_seconds'] = secs
            self.loadbar['value'] = 100
            self.plugin_info.set(f'{name} loaded in {secs:.0f} s. Now open the plugin window or use the saved kit.')
            self.save_settings()

    def need_plugin(self):
        if not self.host.plugin:
            messagebox.showinfo('SmartKit', 'Load the plugin first (tab 1).'); return False
        if self.busy:
            messagebox.showinfo('SmartKit', 'Still busy – wait or press Stop.'); return False
        return True

    def do_editor(self):
        if not self.need_plugin(): return
        import subprocess
        self.status.set('Plugin window open – press "Kit loaded – continue" when your kit has loaded.')
        ev = threading.Event()
        helper = None
        try:
            helper = subprocess.Popen([sys.executable, os.path.join(HERE, 'editor_done.py')])
            threading.Thread(target=lambda: (helper.wait(), ev.set()), daemon=True).start()
        except Exception:
            pass
        try:
            self.host.show_editor(close_event=ev)
        except Exception as e:
            messagebox.showerror('SmartKit', f'Could not open the plugin window: {e}'); return
        finally:
            if helper and helper.poll() is None:
                helper.terminate()
        os.makedirs(self.project_dir(), exist_ok=True)
        try:
            self.host.save_state(os.path.join(self.project_dir(), 'plugin_state.bin'))
        except Exception as e:
            self.log(f'Could not save the kit settings: {e}')
        self.read_layout()
        self.refresh_project_buttons()
        self.wait_ready()

    def refresh_project_buttons(self):
        p = self.project_dir()
        self.btn_restore.state(['!disabled'] if os.path.exists(os.path.join(p, 'plugin_state.bin')) else ['disabled'])

    def read_layout(self):
        try:
            self.layout = sd3state.parse(self.host.plugin.raw_state)
        except Exception as e:
            self.layout = []
            self.log(f'Could not read the kit layout from the plugin: {e}')
        if self.layout:
            groups = sorted({a['group'] for a in self.layout})
            self.log(f'Read {len(self.layout)} articulations in {len(groups)} instruments from the plugin.')
            if sd3state.SKIPPED:
                self.log(f'{len(sd3state.SKIPPED)} articulations are switched off in the plugin (not loaded) and are '
                         'left out: ' + ', '.join(a['code'] for a in sd3state.SKIPPED))
            self.report_edrum()

    def report_edrum(self):
        ed = sd3state.EDRUM
        if ed.get('name'):
            moved = [f"{a['code']} {a['notes'][0]}→{a['play']}" for a in self.layout if a['play'] != a['notes'][0]
                     and a['notes'][0] in ed['remap']]
            self.log(f"The plugin's MIDI In / E-drum map \"{ed['name']}\" redirects {len(ed['remap'])} notes. SmartKit "
                     'plays each sound with a note that reaches it' + (': ' + ', '.join(moved) if moved else '.'))
        if sd3state.UNREACHABLE:
            names = ', '.join(a['code'] for a in sd3state.UNREACHABLE)
            self.log(f'Cannot be played while that E-drum map is on (all their notes are redirected): {names}')
            self.after(200, lambda: messagebox.showwarning('SmartKit', (
                f"These sounds can't be recorded while Superior Drummer's MIDI In / E-drum map "
                f"\"{ed.get('name')}\" is on, because it sends their notes to other sounds:\n\n{names}\n\n"
                "To get them: open the plugin window, set Settings → MIDI In/E-Drums to the default (no "
                "e-drum preset), press 'Kit loaded – continue', then Find sounds again.")))

    def do_restore(self):
        if not self.need_plugin(): return
        try:
            self.host.restore_state(os.path.join(self.project_dir(), 'plugin_state.bin'))
        except Exception as e:
            self.log('Could not restore the kit:\n' + traceback.format_exc())
            messagebox.showerror('SmartKit', f'Could not restore the kit: {e}'); return
        self.read_layout()
        self.wait_ready()

    def wait_ready(self):
        self.plugin_info.set('Waiting for the kit samples to finish loading …')
        self.loadbar.configure(mode='indeterminate'); self.loadbar.start(12)
        probe_note = 38
        if self.layout:
            probe_note = sd3state.primary_note(self.layout[0])

        def job():
            return self.host.wait_until_ready(note=probe_note, cancel=lambda: self.cancel_flag)

        def done(t):
            self.loadbar.stop(); self.loadbar.configure(mode='determinate'); self.loadbar['value'] = 100
            kit = f' {len(self.layout)} sounds found in the kit layout.' if self.layout else ''
            self.plugin_info.set(('Kit ready.' if t is not None else
                                  'No sound yet – the kit may still be loading. You can carry on.') + kit)
            self.nb.select(1)                          # on to step 2
            if not self.rows:
                self.after(300, self.do_probe)
        self.run_bg(job, done, 'Waiting for the kit samples …')

    # ============================================================ tab 2: sounds
    def tab_sounds(self, nb):
        t = ttk.Frame(nb); nb.add(t, text='2 · Find sounds')
        self.instructions(t, 'sounds')
        b = ttk.Frame(t); b.pack(fill='x', padx=12)
        ttk.Button(b, text='Find sounds', style='Accent.TButton', command=self.do_probe).pack(side='left', padx=3)
        ttk.Label(b, text='notes (other plugins)').pack(side='left', padx=(8, 2))
        self.v_notes = self.var('notes', '0-127')
        ttk.Entry(b, textvariable=self.v_notes, width=9).pack(side='left')
        ttk.Button(b, text='▶ Play', command=self.play_sel).pack(side='left', padx=(12, 3))
        ttk.Button(b, text='Stop', command=self.stop).pack(side='right', padx=3)
        b = ttk.Frame(t); b.pack(fill='x', padx=12, pady=(6, 0))
        ttk.Button(b, text='Suggest pads', command=self.auto_pads).pack(side='left', padx=3)
        ttk.Button(b, text='Save preset…', command=self.save_preset).pack(side='left', padx=3)
        ttk.Button(b, text='Load preset…', command=self.load_preset).pack(side='left', padx=3)
        ttk.Button(b, text='All off', command=lambda: self.set_all_use(False)).pack(side='left', padx=3)
        ttk.Button(b, text='Library names', command=self.reset_names).pack(side='left', padx=3)
        self.v_inst_only = tk.StringVar(value=self.st.get('inst_only', '0'))
        ttk.Checkbutton(b, text='Instruments only (no pads – assign them on the module)', variable=self.v_inst_only,
                        onvalue='1', offvalue='0', command=self.save_settings).pack(side='left', padx=12)
        self.pbar = ttk.Progressbar(t); self.pbar.pack(fill='x', padx=12, pady=(8, 4))
        cols = ('use', 'full', 'name', 'type', 'pads', 'ring', 'level', 'notes')
        tr = ttk.Treeview(t, columns=cols, show='tree headings', height=18)
        tr.column('#0', width=170, stretch=False); tr.heading('#0', text='instrument')
        for c, w, txt in [('use', 40, 'use'), ('full', 330, 'sound (plugin or samples) – double-click to play'), ('name', 200, 'Strike instrument name'),
                          ('type', 70, 'type'), ('pads', 150, 'Strike pad(s)'), ('ring', 55, 'rings s'),
                          ('level', 60, 'level dB'), ('notes', 80, 'MIDI notes')]:
            tr.heading(c, text=txt); tr.column(c, width=w, anchor='w', stretch=(c in ('full', 'name', 'pads')))
        ysb = ttk.Scrollbar(t, orient='vertical', command=tr.yview); tr.configure(yscrollcommand=ysb.set)
        ysb.pack(side='right', fill='y', padx=(0, 12), pady=(4, 12)); tr.pack(fill='both', expand=True, padx=(12, 0), pady=(4, 12))
        tr.bind('<Button-1>', self.on_click)
        tr.bind('<Double-1>', self.on_double)
        tr.bind('<Button-3>', self.on_right)
        tr.bind('<space>', lambda e: self.play_sel())
        self.tree = tr

    # ---------- rows
    def parse_notes(self):
        out = []
        for part in self.v_notes.get().replace(',', ' ').split():
            m = re.match(r'(\d+)-(\d+)$', part)
            if m:
                out += list(range(int(m.group(1)), int(m.group(2)) + 1))
            elif part.isdigit():
                out.append(int(part))
        return [n for n in out if 0 <= n <= 127]

    def do_probe(self):
        if not self.need_plugin(): return
        folder = os.path.join(self.project_dir(), 'probe')
        if not self.layout:
            self.read_layout()
        if self.layout:
            items = [(f"{a['box']:02d}_{a['code']}", sd3state.primary_note(a), a) for a in self.layout]
        else:
            items = [(f'N{n:03d}', n, None) for n in self.parse_notes()]

        def job():
            found = {}
            for i, (key, note, a) in enumerate(items):
                if self.cancel_flag: raise H.Cancelled()
                self.progress(i, len(items), f'Listening to {a["group"] + " " + a["label"] if a else "note " + str(note)} …')
                audio, ring = self.host.ring_hit(note)
                if audio is None:
                    continue
                f = os.path.join(folder, f'{key}.wav')
                H.write_wav_float(f, audio)
                found[key] = dict(note=note, ring=round(float(ring), 2), peak=float(np.abs(audio).max()), file=f, art=a)
            self.progress(len(items), len(items), f'{len(found)} sounds found')
            return found

        def done(found):
            if found is None: return
            old = self.rows
            self.rows = {k: r for k, r in old.items() if r.get('src')}     # sample sounds stay
            fps = {}
            for key, f in found.items():
                a = f['art']
                aud, _ = read_wav(f['file'])
                k = aud.mean(1)[:4096]; k = k / (np.linalg.norm(k) + 1e-12)
                # same sound as another articulation of the SAME drum (SD3 reuses samples, e.g. bow shank = crash)
                dup = next((m for m, kk in fps.items() if len(kk) == len(k) and float(np.dot(kk, k)) > 0.98
                            and m.split('_')[0] == key.split('_')[0]
                            and abs(20 * np.log10(found[m]['peak'] / max(f['peak'], 1e-9))) < 1.0), None)
                fps[key] = k
                if a:
                    name, base = self.auto_name(a)
                    group, role, notes, sfx = a['group'], a['role'], a['notes'], sd3names.art_suffix(a['code'], a['role'], a['pos'])
                else:
                    group, notes = 'MIDI notes', [f['note']]
                    name = base = H.GM_NAMES.get(f['note'], f"Note {f['note']}")
                    role, sfx = guess_role([measure(aud, H.SR)])[0], ''
                row = dict(key=key, note=f['note'], notes=notes, group=group, code=a['code'] if a else '', base=base, sfx=sfx,
                           full=self.full_name(a) if a else name,
                           name=name, role=role, pads=[], use=dup is None, ring=f['ring'], peak=f['peak'],
                           file=f['file'], auto=['name', 'role'], dup=dup)
                if dup is not None:
                    row['name'] = f"{name} (same as {self.rows[dup]['name'] if dup in self.rows else dup})"
                prev = old.get(key)
                if prev:                                  # keep what the user changed before
                    for fld in ('name', 'role', 'pads', 'use'):
                        if fld not in prev.get('auto', []) or fld == 'use':
                            row[fld] = prev[fld]
                    row['auto'] = [x for x in prev.get('auto', []) if x in row['auto'] or x == 'pads']
                self.rows[key] = row
            if not any(r['pads'] for r in self.rows.values()):
                self.auto_pads(quiet=True)
            self.fill_tree(); self.save_map()
            self.status.set(f'{len(found)} sounds found. Check the names, types and pads (* = chosen automatically).')
        self.run_bg(job, done, 'Listening to every sound …')

    def fill_tree(self):
        tr = self.tree
        open_groups = {i for i in tr.get_children() if tr.item(i, 'open')}
        tr.delete(*tr.get_children())
        groups = {}
        for key, r in sorted(self.rows.items(), key=lambda kv: (kv[1]['group'], kv[1]['note'])):
            g = r['group']
            if g not in groups:
                gid = 'g|' + g
                groups[g] = gid
                tr.insert('', 'end', iid=gid, text=g, open=(gid in open_groups or not open_groups), tags=('group',))
            tr.insert(groups[g], 'end', iid=key, text='', values=self.row_values(r), tags=() if r['use'] else ('off',))
        for g, gid in groups.items():
            self.update_group(gid)
        self.kit_summary()

    def row_values(self, r):
        star = lambda f: '*' if f in r.get('auto', []) else ''
        pads = ' '.join('instrument only' if p == INST_ONLY else p for p in r['pads'])
        return ('☑' if r['use'] else '☐', r.get('full') or r['name'], r['name'] + star('name'),
                r['role'] + star('role'), (pads + star('pads')) if pads else '',
                r['ring'], f"{20 * np.log10(max(r['peak'], 1e-9)):.1f}", ' '.join(map(str, r['notes'][:4])))

    def update_group(self, gid):
        kids = self.tree.get_children(gid)
        on = sum(self.rows[k]['use'] for k in kids)
        mark = '☑' if on == len(kids) else ('☐' if on == 0 else '◪')
        self.tree.item(gid, values=(mark, '', f'{on} of {len(kids)} used', '', '', '', ''))
        self.kit_summary()

    def kit_summary(self):
        if not hasattr(self, 'kit_tip'): return
        n = len(self.used_rows())
        self.kit_tip.configure(text=f'{n} sound{"s" * (n != 1)} in the kit' if self.rows else 'no sounds yet')

    def refresh_row(self, key):
        r = self.rows[key]
        self.tree.item(key, values=self.row_values(r), tags=() if r['use'] else ('off',))
        self.update_group(self.tree.parent(key))

    def save_map(self):
        if not self.rows and not self.sources: return
        d = getattr(self, 'proj_dir', None) or self.project_dir()     # the open project (also while renaming)
        os.makedirs(d, exist_ok=True)
        json.dump({'rows': self.rows, 'layout': self.layout, 'sources': self.sources},
                  open(os.path.join(d, 'sounds.json'), 'w'), indent=1)

    def set_all_use(self, on):
        for k in self.rows: self.rows[k]['use'] = on
        self.fill_tree(); self.save_map()

    # ---------- mouse
    def cell(self, event):
        return self.tree.identify_row(event.y), self.tree.identify_column(event.x)

    def colname(self, col):
        if col == '#0': return 'tree'
        return self.tree['columns'][int(col[1:]) - 1]

    def on_click(self, e):
        iid, col = self.cell(e)
        if not iid or self.colname(col) != 'use':
            return
        if iid.startswith('g|'):
            kids = self.tree.get_children(iid)
            on = not all(self.rows[k]['use'] for k in kids)
            for k in kids:
                self.rows[k]['use'] = on; self.refresh_row(k)
        else:
            self.rows[iid]['use'] = not self.rows[iid]['use']; self.refresh_row(iid)
        self.save_map()
        return 'break'

    def on_double(self, e):
        iid, col = self.cell(e)
        if not iid or iid.startswith('g|'):
            return
        if self.colname(col) == 'name':
            self.edit_name(iid, col)
        elif self.colname(col) in ('type',):
            self.edit_type(iid, col)
        elif self.colname(col) == 'pads':
            self.pad_menu(iid, e)
        else:
            self.play_key(iid)
        return 'break'

    def on_right(self, e):
        iid, col = self.cell(e)
        if not iid or iid.startswith('g|'):
            return
        self.tree.selection_set(iid)
        c = self.colname(col)
        if c == 'type':
            self.edit_type(iid, col)
        elif c == 'pads':
            self.pad_menu(iid, e)
        elif c == 'name':
            self.edit_name(iid, col)
        else:
            m = T.Menu(self)
            m.add_command(label='▶ Play', command=lambda: self.play_key(iid))
            m.add_command(label='Rename…', command=lambda: self.edit_name(iid, '#3'))
            tm = T.Menu(m)
            for r in ROLES:
                tm.add_command(label=r, command=lambda r=r: self.set_field(iid, 'role', r))
            m.add_cascade(label='Type', menu=tm)
            if self.rows[iid].get('src'):
                cm = T.Menu(m)
                for grp, codes in (('Kick / snare / tom', ['KCKHD', 'SNRHD', 'SNRRI', 'SNRRO', 'SNRXS', 'SNRFL', 'SNROF', 'TOMHD', 'TOMRI']),
                                   ('Hi-hat', ['HHBCL', 'HHBTT', 'HHBO1', 'HHBO2', 'HHBO3', 'HHBO4', 'HHBO5', 'HHECL', 'HHETT',
                                               'HHEO1', 'HHEO2', 'HHEO3', 'HHEO4', 'HHEO5', 'HHPCL', 'HHPSP']),
                                   ('Cymbals', ['CRSED', 'CRSBW', 'CRSBL', 'CRSCH', 'RIDBW', 'RIDBL', 'RIDED', 'SPLED', 'SPLCH',
                                                'CHNED', 'STKED', 'PRCHT', 'PRCCB'])):
                    sm = T.Menu(cm)
                    for c in codes:
                        sm.add_command(label=f'{c}  {SRC.describe(c)[1]}', command=lambda c=c: self.set_code(iid, c))
                    cm.add_cascade(label=grp, menu=sm)
                m.add_cascade(label='Code (5 letters)', menu=cm)
            m.add_command(label='Strike pads…', command=lambda: self.pad_menu(iid, e))
            m.tk_popup(e.x_root, e.y_root)

    def set_field(self, key, field, value):
        r = self.rows[key]
        r[field] = value
        if field in r.get('auto', []):
            r['auto'] = [x for x in r['auto'] if x != field]
        self.refresh_row(key); self.save_map()

    def place_editor(self, key, col, widget):
        x, y, w, h = self.tree.bbox(key, col)
        widget.place(in_=self.tree, x=x, y=y, width=max(w, 120), height=h)
        widget.focus_set()
        self.editor = widget

    def close_editor(self):
        if self.editor is not None:
            self.editor.destroy(); self.editor = None

    def edit_name(self, key, col):
        self.close_editor()
        v = tk.StringVar(value=self.rows[key]['name'])
        e = ttk.Entry(self.tree, textvariable=v)
        def ok(_=None):
            nm = re.sub(r'\s+', ' ', re.sub(sd3names.PLAIN, ' ', v.get())).strip()[:26]
            if nm: self.set_field(key, 'name', nm)
            self.close_editor()
        e.bind('<Return>', ok); e.bind('<FocusOut>', ok); e.bind('<Escape>', lambda _: self.close_editor())
        self.place_editor(key, col, e); e.select_range(0, 'end')

    def edit_type(self, key, col):
        self.close_editor()
        v = tk.StringVar(value=self.rows[key]['role'])
        cb = ttk.Combobox(self.tree, textvariable=v, values=ROLES, state='readonly')
        def ok(_=None):
            self.set_field(key, 'role', v.get()); self.close_editor()
        cb.bind('<<ComboboxSelected>>', ok); cb.bind('<Escape>', lambda _: self.close_editor())
        cb.bind('<FocusOut>', lambda _: self.after(200, self.close_editor))
        self.place_editor(key, col, cb)
        self.after(50, lambda: cb.event_generate('<Button-1>'))

    def pad_menu(self, key, e):
        r = self.rows[key]
        m = T.Menu(self)
        vs = {}

        def toggle(p, combine=False):
            pads = list(r['pads'])
            pads = [x for x in pads if x != INST_ONLY]
            if p in pads:
                pads.remove(p)
            else:
                if p.startswith('H1'):                    # one hi-hat slot per sound row
                    pads = [x for x in pads if not x.startswith(p[:3])]
                pads.append(p)
                if not combine:                           # a pad (or hi-hat slot) plays one sound: take it away from others
                    for k, o in self.rows.items():
                        if k != key and p in o['pads']:
                            o['pads'] = [x for x in o['pads'] if x != p]
                            if 'pads' in o.get('auto', []): o['auto'].remove('pads')
                            self.refresh_row(k)
            self.set_field(key, 'pads', pads)
        cm = T.Menu(m)
        for p in PADS:
            vs[p] = tk.BooleanVar(value=p in r['pads'])
            others = [o['name'] for k, o in self.rows.items() if k != key and p in o['pads']]
            lab = f'{p}  {PAD_NAMES[p]}' + (f'   (now: {", ".join(others)[:40]})' if others else '')
            m.add_checkbutton(label=lab, variable=vs[p], command=lambda p=p: toggle(p))
            if others and p not in r['pads']:
                cm.add_command(label=f'{p}  {PAD_NAMES[p]}  together with {", ".join(others)[:40]}',
                               command=lambda p=p: toggle(p, combine=True))
        hm = T.Menu(m)
        for p in HAT_SLOTS:
            vs[p] = tk.BooleanVar(value=p in r['pads'])
            hm.add_checkbutton(label=f'{HAT_SLOT_NAMES[p[:3]]} – {p[4:]}', variable=vs[p], command=lambda p=p: toggle(p))
        m.add_separator()
        m.add_cascade(label='Hi-hat', menu=hm)
        if cm.index('end') is not None:
            m.add_cascade(label='Share a pad with another sound (combine)', menu=cm)
        m.add_separator()
        vs[INST_ONLY] = tk.BooleanVar(value=INST_ONLY in r['pads'])
        m.add_checkbutton(label='Instrument only (saved to Instruments, not in the kit)', variable=vs[INST_ONLY],
                          command=lambda: self.set_field(key, 'pads', [] if INST_ONLY in r['pads'] else [INST_ONLY]))
        m.add_command(label='No pad', command=lambda: self.set_field(key, 'pads', []))
        m.tk_popup(e.x_root, e.y_root)

    def sel(self):
        s = [i for i in self.tree.selection() if not i.startswith('g|')]
        return s[0] if s else None

    def play_sel(self):
        k = self.sel()
        if k: self.play_key(k)

    def play_key(self, key):
        try:
            import winsound
            a, sr = read_wav(self.rows[key]['file'])
            a = a / max(np.abs(a).max(), 1e-9) * 0.7
            tmp = os.path.join(self.project_dir(), '_preview.wav')
            H.write_wav16(tmp, a[:sr * 6], sr)
            winsound.PlaySound(tmp, winsound.SND_FILENAME | winsound.SND_ASYNC)
            self.status.set(f"Playing {self.rows[key]['name']}")
        except Exception as e:
            self.status.set(f'Cannot play: {e}')

    # ---------- pad suggestions & presets
    def auto_pads(self, quiet=False):
        """Suggest pads from the kit layout / names (your layout: splash on the Tom 1 rim, china as crash 3)."""
        if not quiet and not messagebox.askyesno('SmartKit', 'Replace pad choices marked * with suggestions?\n'
                                                              '(pads you chose yourself are kept)'):
            return
        mine = {p for r in self.rows.values() if 'pads' not in r.get('auto', ['pads']) for p in r['pads']}
        for r in self.rows.values():
            if 'pads' in r.get('auto', ['pads']) or not r['pads']:
                r['pads'] = []
                if 'pads' not in r.setdefault('auto', []): r['auto'].append('pads')
        taken = set(mine)
        rows = [r for _, r in sorted(self.rows.items(), key=lambda kv: (kv[1]['group'], kv[1]['note'])) if r['use']]
        has = lambda r, *ns: any(n in r['notes'] for n in ns)
        code = lambda r: r.get('code', '')

        def put(r, *pads):
            free = [p for p in pads if p not in taken]
            if free and 'pads' in r.get('auto', []):
                r['pads'] = r['pads'] + free; taken.update(p if not p.startswith('H1') else p for p in free)
                return True
        first = lambda cond: next((r for r in rows if cond(r)), None)
        r = first(lambda r: r['role'] == 'kick' and has(r, 36)) or first(lambda r: r['role'] == 'kick')
        if r: put(r, 'K1H')
        r = first(lambda r: r['role'] == 'snare' and has(r, 38)) or first(lambda r: r['role'] == 'snare')
        if r: put(r, 'S1H')
        r = first(lambda r: has(r, 40)) or first(lambda r: r['role'] == 'rim' and has(r, 37)) or first(lambda r: r['role'] == 'rim')
        if r: put(r, 'S1R')
        toms, seen = [], set()
        for r in rows:
            if r['role'] == 'tom' and r['group'] not in seen and (re.search(r'R$', code(r)) or not code(r)):
                toms.append(r); seen.add(r['group'])
        toms.sort(key=lambda r: -max(r['notes']))           # high toms first (GM: 50/48 high … 41 floor)
        for i, r in enumerate(toms[:4]): put(r, f'T{i + 1}H')
        r = first(lambda r: r['role'] in ('crash', 'other') and ('splash' in r['name'].lower() or has(r, 55)))
        if r: put(r, 'T1R')
        c1 = first(lambda r: r['role'] == 'crash' and has(r, 49))
        c2 = first(lambda r: r['role'] == 'crash' and has(r, 57))
        c3 = first(lambda r: r['role'] == 'crash' and has(r, 52))
        for r, n in ((c1, 1), (c2, 2), (c3, 3)):
            if r: put(r, f'C{n}B', f'C{n}E')
        r = first(lambda r: r['role'] == 'ride' and has(r, 51))
        if r: put(r, 'R1B')
        r = first(lambda r: r['role'] == 'ride' and has(r, 53))
        if r: put(r, 'R1D')
        r = first(lambda r: r['role'] == 'ride' and has(r, 59))
        if r: put(r, 'R1E')
        elif first(lambda r: 'R1B' in r['pads']): put(first(lambda r: 'R1B' in r['pads']), 'R1E')
        # hi-hats (Toontrack codes: TP tip closed, T1..T5 tip opening, CL edge closed, O1..O5 edge opening,
        # PL pedal, PLO pedal splash) – best guesses, listen to check
        for r in rows:
            c = code(r)
            if r['role'] not in ('hihat', 'pedal'):
                continue
            m = re.match(r'hats(TP|T(\d)|CL|O(\d)|PL|PLO)$', c)
            if m:
                g = m.group(1)
                slot = ('H1B closed' if g == 'TP' else f'H1B open {int(m.group(2))}' if m.group(2) and 1 <= int(m.group(2)) <= 5
                        else 'H1E closed' if g == 'CL' else f'H1E open {int(m.group(3))}' if m.group(3) and 1 <= int(m.group(3)) <= 5
                        else 'H1F chick' if g == 'PL' else 'H1F splash' if g == 'PLO' else None)
            elif not c:
                slot = ('H1B closed' if has(r, 42) else 'H1B open 3' if has(r, 46) else 'H1F chick' if has(r, 44) else None)
            else:
                slot = None
            if slot: put(r, slot)
        if hasattr(self, 'tree'):
            self.fill_tree()
        self.save_map()

    def preset_key(self, r):
        return f"{r['group'].split(' (slot')[0]}|{r['code']}" if r.get('code') else f"note|{r['note']}"

    def save_preset(self):
        os.makedirs(PRESETS, exist_ok=True)
        p = filedialog.asksaveasfilename(initialdir=PRESETS, defaultextension='.json',
                                         filetypes=[('SmartKit pad preset', '*.json')], title='Save pad preset')
        if not p: return
        d = {}
        for r in self.rows.values():
            d.setdefault(self.preset_key(r), {'pads': r['pads'], 'use': r['use'], 'note': r['note'],
                                              'name': None if 'name' in r.get('auto', []) else r['name'],
                                              'role': None if 'role' in r.get('auto', []) else r['role']})
        json.dump({'smartkit_preset': 1, 'rows': d}, open(p, 'w'), indent=1)
        self.status.set(f'Preset saved: {os.path.basename(p)}')

    def load_preset(self):
        p = filedialog.askopenfilename(initialdir=PRESETS, filetypes=[('SmartKit pad preset', '*.json')])
        if not p: return
        d = json.load(open(p)).get('rows', {})
        by_note = {v['note']: v for v in d.values()}
        n = 0
        for r in self.rows.values():
            v = d.get(self.preset_key(r)) or (by_note.get(r['note']) if not r.get('code') else None)
            if not v: continue
            r['pads'], r['use'] = list(v['pads']), v['use']
            r['auto'] = [x for x in r.get('auto', []) if x != 'pads']
            for f in ('name', 'role'):
                if v.get(f):
                    r[f] = v[f]; r['auto'] = [x for x in r['auto'] if x != f]
            n += 1
        self.fill_tree(); self.save_map()
        self.status.set(f'Preset {os.path.basename(p)} applied to {n} sounds.')

    # ============================================================ tab 3: settings
    def tab_settings(self, nb):
        t = self.page(nb, '3 · Settings')
        self.instructions(t, 'settings')
        top = ttk.Frame(t); top.pack(fill='x', padx=12, pady=6)
        f = ttk.Frame(top); f.pack(side='top', anchor='w')
        self.memory_panel(top)
        rows = [
            ('Record every Nth velocity (1 = all 127)', 'vstep', '4', None),
            ('Takes per velocity (round robins)', 'reps', '2', None),
            ('Sample memory to use (MB, max 200)', 'budget', '196', None),
            ('Velocity curve (1 = even steps, >1 = more soft layers)', 'curve', '1.0', None),
            ('Hi-hat closed at pedal value (127 = factory layout)', 'hat', '127', None),
            ('Several sounds on one pad', 'combine', COMBINE_MODES[0], COMBINE_MODES),
            ("'Instrument only' sounds: max MB each (0 = same as the kit's)", 'extra_mb', '0', None),
            ('Levels', 'levels', LEVEL_MODES[0], LEVEL_MODES),
            ('Instrument folders on the card', 'folders', FOLDER_NESTED, FOLDER_MODES),
            ('Compressed sounds (loudness stops rising at hard hits)', 'comp', COMP_MODES[0], COMP_MODES),
            ('  dB of loudness given back to the hard hits', 'comp_db', '8', None),
            ('Empty pad zones (crash bow, ride edge, rims, kick 2 …)', 'fill_empty',
             'play the partner zone', ['play the partner zone', 'stay silent']),
            ('Zone gain', 'gain', 'unity', ['unity', 'normalise']),
            ('Plugin start-up wait (s) – raise if a plugin loads without sound', 'loadwait', '15', None),
            ('Output folder or SD card', 'out', '', 'dir'),
            ('Kit settings copied from (.skt)', 'template', os.path.join(HERE, 'template.skt'), 'file'),
        ]
        for i, (lab, key, dflt, kind) in enumerate(rows):
            ttk.Label(f, text=lab).grid(row=i, column=0, sticky='w', pady=2)
            v = self.var(key, dflt)
            if isinstance(kind, list):
                ttk.Combobox(f, textvariable=v, values=kind, state='readonly', width=40).grid(row=i, column=1, sticky='w')
            else:
                ttk.Entry(f, textvariable=v, width=46 if kind else 10).grid(row=i, column=1, sticky='w')
            if kind in ('dir', 'file'):
                ttk.Button(f, text='…', width=3, command=lambda k=key, kd=kind: self.pick(k, kd)).grid(row=i, column=2)
            if key == 'out':
                ttk.Button(f, text='Find SD card', command=self.find_sd).grid(row=i, column=3, padx=4)
        self.estimate = tk.StringVar(value='')
        n = len(rows)
        ttk.Button(f, text='Estimate recording time', command=self.do_estimate).grid(row=n, column=0, sticky='w', pady=(6, 0))
        ttk.Label(f, textvariable=self.estimate).grid(row=n, column=1, columnspan=3, sticky='w', pady=(6, 0))

    def memory_panel(self, parent):
        mf = ttk.LabelFrame(parent, text='Memory planner – per type of drum')
        mf.pack(side='top', anchor='w', pady=(10, 0), fill='x')
        ttk.Label(mf, text='type', style='Small.TLabel').grid(row=0, column=0, sticky='w', padx=6)
        ttk.Label(mf, text='priority 0–10', style='Small.TLabel').grid(row=0, column=1, sticky='w', padx=6)
        ttk.Label(mf, text='stereo', style='Small.TLabel').grid(row=0, column=2, sticky='w', padx=6)
        prio, ster = self.st.get('priority', {}), self.st.get('stereo_by_type', {})
        self.v_prio, self.v_ster = {}, {}
        for i, r in enumerate(ROLES, 1):
            ttk.Label(mf, text=TYPE_NAMES[r]).grid(row=i, column=0, sticky='w', padx=6)
            self.v_prio[r] = tk.StringVar(value=prio.get(r, f'{WEIGHT.get(r, 0.4) * 10:g}'))
            ttk.Spinbox(mf, from_=0, to=10, increment=0.5, width=6, textvariable=self.v_prio[r]).grid(row=i, column=1, sticky='w', padx=6)
            self.v_ster[r] = tk.StringVar(value=ster.get(r, DEFAULT_STEREO.get(r, 'mono')))
            ttk.Combobox(mf, textvariable=self.v_ster[r], values=STEREO_MODES, state='readonly', width=14
                         ).grid(row=i, column=2, sticky='w', padx=6, pady=1)
        ttk.Button(mf, text='Defaults', command=self.memory_defaults).grid(row=len(ROLES) + 1, column=0, sticky='w', padx=6, pady=4)
        mf.columnconfigure(3, weight=1)
        T.WrapLabel(mf, text=MEMORY_HELP, style='Small.TLabel'
                    ).grid(row=1, column=3, rowspan=len(ROLES) + 1, sticky='new', padx=(16, 6))

    def memory_defaults(self):
        for r in ROLES:
            self.v_prio[r].set(f'{WEIGHT.get(r, 0.4) * 10:g}'); self.v_ster[r].set(DEFAULT_STEREO.get(r, 'mono'))

    def type_weight(self, role):
        try:
            return max(0.0, min(10.0, float(self.v_prio[role].get()))) / 10
        except Exception:
            return WEIGHT.get(role, 0.4)

    def pick(self, key, kind):
        p = filedialog.askdirectory() if kind == 'dir' else filedialog.askopenfilename(filetypes=[('Strike kit', '*.skt')])
        if p: getattr(self, 'v_' + key).set(p)

    def find_sd(self):
        import string
        for d in string.ascii_uppercase[3:]:
            root = f'{d}:\\'
            if all(os.path.isdir(os.path.join(root, x)) for x in ('Kits', 'Instruments', 'Samples')):
                self.v_out.set(root); self.status.set(f'Strike SD card found at {root}'); return
        messagebox.showinfo('SmartKit', 'No Strike SD card found (a drive with Kits, Instruments and Samples folders).')

    def vels(self):
        step = max(1, int(float(self.v_vstep.get() or 4)))
        v = list(range(127, 0, -step))
        if v[-1] != 1: v.append(1)
        return v

    def inst_only(self):
        return hasattr(self, 'v_inst_only') and self.v_inst_only.get() == '1'

    def used_rows(self):
        if self.inst_only():                     # every ticked sound becomes an instrument
            return [r for r in self.rows.values() if r['use']]
        return [r for r in self.rows.values() if r['use'] and r['pads']]

    def do_estimate(self):
        rows = self.used_rows()
        if not rows:
            self.estimate.set('Find the sounds and give them pads first (tab 2).'); return
        sec, audio = H.estimate_seconds(rows, self.vels(), int(self.v_reps.get() or 2), self.host.speed or 10)
        self.estimate.set(f'{len(rows)} sounds × {len(self.vels())} velocities × {self.v_reps.get()} takes = '
                          f'{audio / 60:.0f} min of audio, about {max(1, sec / 60):.0f} min to record.')

    # ============================================================ tab 4: Strike settings
    def tab_strike(self, nb):
        t = self.page(nb, '4 · Strike settings')
        self.instructions(t, 'strike')
        lf = ttk.LabelFrame(t, text='Instrument / pad settings per type of drum')
        lf.pack(fill='x', padx=12, pady=6)
        ttk.Label(lf, text='type', style='Small.TLabel').grid(row=0, column=0, sticky='w', padx=4)
        for j, (k, title, *_r) in enumerate(LAYER_COLS, 1):
            ttk.Label(lf, text=title, style='Small.TLabel').grid(row=0, column=j, padx=2)
        saved = self.st.get('layer', {})
        self.v_layer = {}
        for i, r in enumerate(ROLES, 1):
            ttk.Label(lf, text=TYPE_NAMES[r]).grid(row=i, column=0, sticky='w', padx=4)
            self.v_layer[r] = {}
            for j, (k, title, _kw, lo, hi, dflt) in enumerate(LAYER_COLS, 1):
                v = tk.StringVar(value=saved.get(r, {}).get(k, str(dflt)))
                self.v_layer[r][k] = v
                ttk.Spinbox(lf, from_=lo, to=hi, width=4, textvariable=v).grid(row=i, column=j, padx=1, pady=1)
        bb = ttk.Frame(lf); bb.grid(row=len(ROLES) + 1, column=0, columnspan=len(LAYER_COLS) + 1, sticky='w', pady=4)
        ttk.Button(bb, text='Defaults', command=self.strike_defaults).pack(side='left', padx=4)
        T.WrapLabel(lf, text=STRIKE_HELP, style='Small.TLabel'
                    ).grid(row=len(ROLES) + 2, column=0, columnspan=len(LAYER_COLS) + 1, sticky='ew', padx=4, pady=(0, 4))

        ff = ttk.LabelFrame(t, text='Kit effects')
        ff.pack(fill='x', padx=12, pady=6)
        fx = self.st.get('kitfx', {})
        self.v_fx = {}

        def fv(k, d):
            self.v_fx[k] = tk.StringVar(value=fx.get(k, d)); return self.v_fx[k]
        rows = [('Kit level', [('level', 'spin', 0, 99, '99')]),
                ('Reverb', [('rtype', REVERB_TYPES, 0, 0, 'OFF'), ('rsize', 'spin', 0, 99, '50', 'size'),
                            ('rcolor', 'spin', 0, 99, '50', 'colour'), ('rlevel', 'spin', 0, 99, '50', 'level')]),
                ('Compressor', [('ctype', COMP_TYPES, 0, 0, 'OFF'), ('cthr', 'spin', -90, 0, '0', 'threshold'),
                                ('cout', 'spin', -24, 24, '0', 'output dB')]),
                ('EQ', [('eq', ['OFF', 'ON'], 0, 0, 'OFF'), ('lgain', 'spin', -60, 12, '0', 'low dB'),
                        ('lfreq', EQ_FREQS, 0, 0, '98', 'low Hz'), ('hgain', 'spin', -60, 12, '0', 'high dB'),
                        ('hfreq', EQ_FREQS, 0, 0, '8.1k', 'high Hz')])]
        for i, (lab, items) in enumerate(rows):
            ttk.Label(ff, text=lab).grid(row=i, column=0, sticky='w', padx=4, pady=2)
            c = 1
            for it in items:
                k, kind, lo, hi, d = it[:5]
                if len(it) > 5:
                    ttk.Label(ff, text=it[5]).grid(row=i, column=c, sticky='e', padx=(8, 2)); c += 1
                if kind == 'spin':
                    ttk.Spinbox(ff, from_=lo, to=hi, width=5, textvariable=fv(k, d)).grid(row=i, column=c, sticky='w')
                else:
                    ttk.Combobox(ff, values=kind, textvariable=fv(k, d), state='readonly',
                                 width=10).grid(row=i, column=c, sticky='w')
                c += 1
        ttk.Label(ff, text='FX1 / FX2 (delays, chorus …) are switched off. MIDI notes sent by each pad = the '
                           "plugin's note for the sound on it (hi-hat 8 / 7 / 22 like the factory kits).",
                  style='Small.TLabel').grid(row=len(rows), column=0, columnspan=12, sticky='w', padx=4, pady=4)

    def strike_defaults(self):
        for r in ROLES:
            for k, title, _kw, lo, hi, dflt in LAYER_COLS:
                self.v_layer[r][k].set(str(dflt))

    def strike_options(self):
        """-> layer_by_role, pad_settings, kit header patch for SK.build_kit"""
        def num(v, lo, hi, d):
            try:
                return max(lo, min(hi, int(float(v.get()))))
            except Exception:
                return d
        layer, pads = {}, {}
        for r in ROLES:
            layer[r], pads[r] = {}, {}
            for k, title, kw, lo, hi, dflt in LAYER_COLS:
                val = num(self.v_layer[r][k], lo, hi, dflt)
                if isinstance(kw, int):
                    pads[r][kw] = val
                else:
                    layer[r][kw] = val
        g = lambda k, lo, hi, d: num(self.v_fx[k], lo, hi, d)
        typ = lambda names, k: 255 if self.v_fx[k].get() in ('OFF', '') else max(0, names.index(self.v_fx[k].get()) - 1)
        fq = lambda k: EQ_FREQS.index(self.v_fx[k].get()) if self.v_fx[k].get() in EQ_FREQS else 0
        hdr = {2: g('level', 0, 99, 99),
               8: typ(REVERB_TYPES, 'rtype'), 9: g('rsize', 0, 99, 50), 10: g('rcolor', 0, 99, 50), 11: g('rlevel', 0, 99, 50),
               12: 255, 13: 0, 24: 255, 25: 0,                           # FX1 / FX2 off
               36: typ(COMP_TYPES, 'ctype'), 37: g('cthr', -90, 0, 0), 38: g('cout', -24, 24, 0),
               39: g('lgain', -60, 12, 0), 40: fq('lfreq'), 41: g('hgain', -60, 12, 0), 42: fq('hfreq'),
               43: 0 if self.v_fx['eq'].get() == 'ON' else 255}
        return layer, pads, hdr

    def pad_notes(self, rows):
        notes = dict(HAT_NOTES)
        for r in rows:
            for p in r['pads']:
                if len(p) == 3 and p not in notes and not p.startswith('H1'):
                    notes[p] = int(r['note'])
        return notes

    # ============================================================ tab 5: record & build
    def tab_build(self, nb):
        t = ttk.Frame(nb); nb.add(t, text='5 · Record & build')
        self.instructions(t, 'build')
        b = ttk.Frame(t); b.pack(fill='x', padx=12)
        self.v_redo = tk.IntVar(value=0)
        ttk.Button(b, text='●  Record + build', style='Accent.TButton', command=self.do_record_build).pack(side='left', padx=4)
        ttk.Button(b, text='Record sounds', command=self.do_record).pack(side='left', padx=(12, 4))
        ttk.Button(b, text='Build kit', command=self.do_build).pack(side='left', padx=4)
        ttk.Checkbutton(b, text='re-record sounds already recorded', variable=self.v_redo).pack(side='left', padx=12)
        ttk.Button(b, text='Stop', command=self.stop).pack(side='left', padx=4)
        ttk.Button(b, text='Clean up…', command=self.cleanup_project).pack(side='right', padx=(6, 0))
        ttk.Button(b, text='Open output folder',
                   command=lambda: os.startfile(self.v_out.get() or os.path.join(self.project_dir(), 'output'))).pack(side='right')
        self.pbar2 = ttk.Progressbar(t); self.pbar2.pack(fill='x', padx=12, pady=(8, 4))
        lf = ttk.Frame(t); lf.pack(fill='both', expand=True, padx=12, pady=(4, 12))
        self.logbox = T.register(tk.Text(lf, font=T.F['mono'], height=22, wrap='word'))
        lsb = ttk.Scrollbar(lf, orient='vertical', command=self.logbox.yview); self.logbox.configure(yscrollcommand=lsb.set)
        lsb.pack(side='right', fill='y'); self.logbox.pack(side='left', fill='both', expand=True)

    def render_dir(self, r):
        return os.path.join((getattr(self, 'proj_dir', None) or self.project_dir()), 'renders', r['key'])

    def do_record_build(self):
        """Record the plugin sounds that still need it, then build the kit – all questions are asked first,
        so nothing waits for an OK after the recording."""
        if not self.build_preflight():
            return
        self.do_record(then=lambda: self.do_build(confirmed=True))

    def do_record(self, then=None):
        self.kit_renamed()
        rows = [r for r in self.used_rows() if not r.get('src')]
        if not rows and then:                    # only sample sounds: nothing to record
            then(); return
        if not rows:
            messagebox.showinfo('SmartKit', 'Nothing to record: no plugin sounds with a Strike pad are switched on in '
                                            'tab 2. (Sample sounds need no recording – press Build kit.)'); return
        if not self.need_plugin(): return
        self.save_settings(); self.save_map()
        vels, reps, redo = self.vels(), int(self.v_reps.get() or 2), self.v_redo.get()
        def note_of(r):                          # the MIDI note a recording was made with (older ones: unknown)
            try:
                return int(open(os.path.join(self.render_dir(r), '_note.txt')).read())
            except Exception:
                return None
        todo = [r for r in rows if redo or not os.path.isdir(self.render_dir(r)) or note_of(r) != int(r['note'])]
        if not todo and then:                    # everything recorded already
            self.log('All plugin sounds are recorded already – building.')
            then(); return
        total = max(1, len(todo) * len(vels) * reps)

        def job():
            t0, done, retried = time.time(), 0, 0
            self.log(f'Recording {len(todo)} sounds, {len(vels)} velocities × {reps} takes …')
            for r in todo:
                folder = self.render_dir(r)
                if os.path.isdir(folder):
                    for f in os.listdir(folder):
                        os.remove(os.path.join(folder, f))
                retried += self.host.render_note(r['note'], vels, reps, r['ring'], folder, self.progress,
                                                 lambda: self.cancel_flag, done, total)
                open(os.path.join(folder, '_note.txt'), 'w').write(str(int(r['note'])))
                done += len(vels) * reps
                el = time.time() - t0
                self.log(f"  {r['name']}: done ({el / 60:.1f} min so far, about {el / done * (total - done) / 60:.0f} min left)")
            self.log(f'Recording finished in {(time.time() - t0) / 60:.1f} min ({retried} hits re-recorded '
                     f'because the plugin was still loading them).')
            return True

        def rec_done(ok):
            if ok and then:
                self.status.set('✔ Recording finished – building the kit …')
                self.after(200, then)
            elif ok:
                self.status.set('✔ Recording finished – press Build kit.')
                self.notify('Recording finished', '✔ All sounds are recorded.\n\nNext: press Build kit.')
        self.run_bg(job, rec_done, 'Recording …')

    def check_pads(self, rows):
        """Pads/hi-hat slots that got sounds from different drums (usually a mistake) -> text, or ''."""
        by = {}
        for r in rows:
            for p in r['pads']:
                if p != INST_ONLY:
                    by.setdefault(p, []).append(r)
        bad = [f"{p}: " + ' + '.join(x['name'] for x in rs) for p, rs in sorted(by.items())
               if len({x['key'].split('_')[0] for x in rs}) > 1]
        return '\n'.join(bad)

    def build_preflight(self):
        """The questions before a build (nothing to build, mixed pads, writing to the card). True = go ahead."""
        self.kit_renamed()
        rows = self.used_rows()
        if not rows:
            ticked = sum(1 for r in self.rows.values() if r['use'])
            messagebox.showinfo('SmartKit', 'Nothing to build: ' + (
                'no sounds are listed for this kit. Add a sample folder on tab 1 or press Find sounds on tab 2.'
                if not self.rows else
                'no sounds are switched on on tab 2.' if not ticked else
                f'{ticked} sounds are switched on, but none has a Strike pad. Give them pads on tab 2 '
                '(Suggest pads), or tick "Instruments only".'))
            self.nb.select(1 if self.rows else 0); return False
        out = self.v_out.get().strip() or os.path.join(self.project_dir(), 'output')
        if levelcal.card_root(out) != os.path.normpath(out):     # E:\Kits picked instead of the card itself
            self.v_out.set(levelcal.card_root(out)); out = self.v_out.get()
            self.log(f'Output folder set to {out} (the folder that holds Kits / Instruments / Samples).')
        kit = safe_name(self.v_kit.get())[:26]
        mixed = '' if self.inst_only() else self.check_pads(rows)
        if mixed and not messagebox.askyesno('SmartKit', 'These pads have sounds from different drums on them, which '
                                             'would be mixed into one instrument:\n\n' + mixed +
                                             '\n\nBuild anyway? (No = go back and fix the pads on tab 2)'):
            self.nb.select(1); return False
        if len(out.rstrip('\\/')) <= 2:
            fold = {FOLDER_MODES[0]: f'"{kit} KICKS", "{kit} SNARES" … folders in Instruments',
                    FOLDER_MODES[1]: f'a "{kit}" folder in Instruments',
                    FOLDER_MODES[2]: 'the "all KICKS", "all SNARES" … folders in Instruments (instruments with the '
                                     'same name there are replaced)',
                    FOLDER_NESTED: f'a "{kit}" folder in Instruments with CRASH, SNARE, HIHAT … inside'}.get(self.v_folders.get(), '')
            if not messagebox.askyesno('SmartKit', f'Write the kit straight to {out}?\n\nFiles added: Kits\\{kit}.skt, '
                                                   f'{fold}, and a "{kit}" folder in Samples.'):
                return False
        return True

    def do_build(self, confirmed=False):
        if not confirmed and not self.build_preflight():
            return
        rows = self.used_rows()
        out = self.v_out.get().strip() or os.path.join(self.project_dir(), 'output')
        kit = safe_name(self.v_kit.get())[:26]
        self.save_settings(); self.save_map()
        self.log(f"\n===== Build {time.strftime('%Y-%m-%d %H:%M')} – SmartKit {VERSION} =====")
        layered = self.v_combine.get() == COMBINE_MODES[1]
        opts = types.SimpleNamespace(out=out, kit=kit, budget=float(self.v_budget.get() or 196),
                                     template=self.v_template.get().strip() or None, curve=float(self.v_curve.get() or 1),
                                     vel_level=0, hat_closed_from=int(self.v_hat.get() or 127),
                                     gain=self.v_gain.get(), include_all=False, auto_pads=False, pads_b={},
                                     extras=[], extra_mb=float(self.v_extra_mb.get() or 0),
                                     levels={LEVEL_MODES[1]: 'instrument', LEVEL_MODES[2]: 'mix'}.get(self.v_levels.get(), 'kit'),
                                     fill_empty=self.v_fill_empty.get().startswith('play'),
                                     folders={FOLDER_MODES[0]: 'type', FOLDER_MODES[1]: 'kit',
                                              FOLDER_MODES[2]: 'shared', FOLDER_NESTED: 'nested',
                                              'Shared type folders: all KICKS, all SNARES … (like your SD card)': 'shared'}.get(self.v_folders.get(), 'nested'),
                                     comp_db=0 if self.v_comp.get() == COMP_MODES[2] else float(self.v_comp_db.get() or 0),
                                     comp_restore=self.v_comp.get() == COMP_MODES[0],
                                     pad_notes=self.pad_notes(rows))
        opts.layer_by_role, opts.pad_settings, opts.kit_fx = self.strike_options()
        weights = {r: self.type_weight(r) for r in ROLES}
        stereo = {r: self.v_ster[r].get() for r in ROLES}

        def job():
            self.log('Reading the recordings …')
            hits_of = {}
            for r in rows:
                if r.get('src'):
                    hs = SRC.load_hits(r['src'], self.log)
                    hits_of[r['key']] = (hs, SRC.source_bytes(r['src']))
                    self.log(f"  {r['name']:34s} {len(hs):3d} hits  (samples)")
                    continue
                folder = self.render_dir(r)
                if not os.path.isdir(folder):
                    self.log(f"  {r['name']}: not recorded yet – skipped"); continue
                hs = load_articulation(folder)
                hits_of[r['key']] = (hs, sum(os.path.getsize(os.path.join(folder, f)) for f in os.listdir(folder)))
                self.log(f"  {r['name']:34s} {len(hs):3d} hits")

            def make(name, role, keys):
                hits, src = [], 0
                for k in keys:
                    if k in hits_of:
                        hits += hits_of[k][0]; src += hits_of[k][1]
                n0 = len(hits); hits = dedupe(hits)
                if not hits: return None
                a = Artic(name, '', hits, force_mono=True)
                a.role = role; a.weight = weights.get(role, 0.4)
                wide = np.median([h.side for h in hits]) > 0.15
                mode = stereo.get(role, 'mono')
                a.channels = 2 if (hits[0].a.shape[1] == 2 and (mode == 'stereo' or (mode == 'stereo if wide' and wide))) else 1
                a.n_raw, a.src_bytes = n0, src
                return a

            artics, pads, cache = [], {}, {}
            # hi-hats: one articulation per hat slot
            for r in rows:
                for p in r['pads']:
                    if not p.startswith('H1'): continue
                    surf, what = p[:3], p[4:]
                    if surf == 'H1F':
                        name, role = ('Hats Foot Splash' if what == 'splash' else 'Hats Pedal'), 'pedal'
                    else:
                        name, role = f"Hats {'Bow' if surf == 'H1B' else 'Edge'} {what.title()}", 'hihat'
                    a = make(name, role, [r['key']])
                    if a:
                        a.base = r.get('base') if 'name' in r.get('auto', []) else None
                        a.code = r.get('sfx') if a.base else None      # HHBO1, HHPSP … for the sample file names
                        artics.append(a)
            if self.inst_only():
                # every ticked sound is its own instrument (hi-hat slots still make the bow/edge/pedal hats)
                for r in rows:
                    if any(p.startswith('H1') for p in r['pads']):
                        continue
                    a = make(r['name'], r['role'], [r['key']])
                    if a:
                        a.solo = True; artics.append(a)
                opts.no_pads = True
                return SK.build_kit(artics, {}, opts, log=self.log) if artics else None
            # other pads: sounds sharing a pad are combined (or A + B)
            by_pad = {}
            for r in rows:
                for p in r['pads']:
                    if not p.startswith('H1') and p != INST_ONLY:
                        by_pad.setdefault(p, []).append(r)
            def joined(g):
                if len(g) == 1:
                    return g[0]['name']
                if all('name' in x.get('auto', []) for x in g) and len({x.get('base') for x in g}) == 1 and g[0].get('base'):
                    sf = [x.get('sfx') or 'PRCHT' for x in g]    # SNRHD + SNRMU -> SNRHDMU (type once, then each articulation)
                    t = os.path.commonprefix(sf)[:3]
                    return sd3names.fit(g[0]['base'], (t + ''.join(c[len(t):][:2] for c in sf))[:7])
                return ' - '.join(x['name'] for x in g)
            for p, rs in sorted(by_pad.items()):
                if layered and len(rs) > 1:
                    groups = [[rs[0]], [rs[1]]]
                    if len(rs) > 2: self.log(f'  {p}: only 2 layers possible – using {rs[0]["name"]} + {rs[1]["name"]}')
                else:
                    groups = [rs]
                for li, g in enumerate(groups):
                    keys = tuple(sorted(r['key'] for r in g))
                    if keys not in cache:
                        name = joined(g)
                        cache[keys] = make(name, g[0]['role'], keys)
                        if cache[keys]: artics.append(cache[keys])
                    if cache[keys]:
                        (pads if li == 0 else opts.pads_b)[p] = cache[keys]
            for r in rows:                              # 'instrument only': built, not put in the kit
                if INST_ONLY in r['pads']:
                    a = make(r['name'], r['role'], [r['key']])
                    if a: opts.extras.append(a)
            if not artics and not opts.extras:
                self.log('Nothing to build: the plugin sounds are not recorded yet (press Record sounds) and no '
                         'sample sound could be read.'); return None
            return SK.build_kit(artics, pads, opts, log=self.log)

        def done(summary):
            if summary:
                self.log(f"\nDone: {summary['used_mib']} MB of {summary['budget_mib']} MB. Files are in {out}")
                if summary.get('extras'):
                    self.log(f"Also saved {len(summary['extras'])} instrument(s) that are not in the kit: "
                             + ', '.join(summary['extras']))
                self.status.set(f"✔ Done – kit built ({summary['used_mib']} MB)")
                rec = self.folder_mb(os.path.join(self.proj_dir, 'renders'))
                tip = (f"\n\nAfter testing it on the module you can free {rec:,.0f} MB of recordings: "
                       "File → Clean up this kit's project files." if rec >= 1 else '')
                self.notify('Kit finished', f"✔ The kit is built ({summary['used_mib']} MB of "
                                            f"{summary['budget_mib']} MB).\n\nFiles are in {out}" + tip)
            else:
                self.status.set('Build stopped – see the log.')
        self.run_bg(job, done, 'Building the kit …')


if __name__ == '__main__':
    os.makedirs(PROJECTS, exist_ok=True)
    # pythonw has no console: keep errors and hard crashes (e.g. inside a plugin) in a file
    try:
        import faulthandler
        _crash = open(os.path.join(HERE, 'smartkit_errors.txt'), 'a', buffering=1, encoding='utf-8')
        _crash.write(f"\n===== SmartKit {VERSION} started {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
        sys.stderr = _crash
        if sys.stdout is None: sys.stdout = _crash
        faulthandler.enable(_crash)
    except Exception:
        pass
    App().mainloop()
