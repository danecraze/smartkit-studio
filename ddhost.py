"""Second plugin player for SmartKit: DawDreamer, in its own helper process.

Some plugins (Steven Slate Drums 5) load in pedalboard but never make a sound there, while they play fine in
DawDreamer (tested 2026-11-18). DawDreamer runs in a separate Python process so the two plugin frameworks never
share one process, and a plugin window that blocks (DawDreamer's open_editor waits until it is closed) does not
stop SmartKit.

DDPlugin looks like a pedalboard plugin to host.DrumHost: call it with MIDI messages to render audio, read/write
raw_state, show_editor(close_event).

Differences: every render starts from silence (a ring is not carried into the next render), only MIDI channel 1,
and no live sound while the plugin window is open.
"""
import os, sys, time, struct, tempfile, threading, subprocess
import numpy as np

SKIP_PEDALBOARD = ('ssdsampler',)        # plugins that are silent in pedalboard: use DawDreamer straight away


def wants_dd(path):
    return any(s in os.path.basename(path).lower() for s in SKIP_PEDALBOARD)


def available():
    import importlib.util
    return importlib.util.find_spec('dawdreamer') is not None


def install(log=None):
    """pip install --user dawdreamer (one time)."""
    if log: log('Installing DawDreamer (second plugin player, one time) …')
    flags = 0x08000000 if sys.platform == 'win32' else 0           # CREATE_NO_WINDOW
    py = sys.executable
    if py.lower().endswith('pythonw.exe'):
        py = py[:-len('pythonw.exe')] + 'python.exe'
    subprocess.call([py, '-m', 'pip', 'install', '--user', 'dawdreamer'], creationflags=flags)
    import importlib, site
    importlib.invalidate_caches()
    try:
        importlib.reload(site)
    except Exception:
        pass
    return available()


def notes_from_msgs(msgs, seconds):
    """[(bytes, t)] note on/off → [(note, vel, start, dur)]."""
    out, open_ = [], {}
    for m, t in sorted(msgs, key=lambda x: x[1]):
        if not m or len(m) < 3:
            continue
        st, n, v = m[0] & 0xF0, m[1], m[2]
        if st == 0x90 and v > 0:
            open_[n] = (v, t)
        elif st in (0x80, 0x90) and n in open_:
            v0, t0 = open_.pop(n)
            out.append((n, v0, t0, max(t - t0, 0.005)))
    for n, (v0, t0) in open_.items():
        out.append((n, v0, t0, max(min(0.1, seconds - t0), 0.005)))
    return out


# ================================================================ helper process
def _worker(addr, key):
    from multiprocessing.connection import Client
    conn = Client(addr, authkey=key)
    import dawdreamer as daw
    engine = synth = None
    sr = 44100
    tmp = tempfile.mkdtemp(prefix='smartkit_dd_')
    while True:
        try:
            cmd, *args = conn.recv()
        except EOFError:
            return
        try:
            if cmd == 'quit':
                conn.send(('ok', None)); return
            if cmd == 'load':
                path, sr, block = args
                engine = daw.RenderEngine(sr, block)
                synth = engine.make_plugin_processor('plugin', path)
                engine.load_graph([(synth, [])])
                name = os.path.splitext(os.path.basename(path))[0]
                conn.send(('ok', (name, synth.get_num_output_channels())))
            elif cmd == 'render':
                notes, seconds = args
                synth.clear_midi()
                for n, v, t, d in notes:
                    synth.add_midi_note(int(n), int(v), float(t), float(d))
                engine.render(float(seconds))
                a = np.asarray(engine.get_audio(), np.float32)
                if a.ndim == 1:
                    a = np.stack([a, a])
                main = a[:2] if a.shape[0] >= 2 else np.concatenate([a, a])
                if a.shape[0] > 2 and float(np.abs(main).max()) < 1e-6 and float(np.abs(a).max()) > 1e-6:
                    main = np.stack([a[0::2].sum(0), a[1::2].sum(0)])  # kit routed to other outputs: mix them
                conn.send(('ok', main))
            elif cmd == 'get_state':
                f = os.path.join(tmp, 'state.bin')
                synth.save_state(f)
                conn.send(('ok', open(f, 'rb').read()))
            elif cmd == 'set_state':
                f = os.path.join(tmp, 'state_in.bin')
                open(f, 'wb').write(args[0])
                synth.load_state(f)
                conn.send(('ok', None))
            elif cmd == 'editor':
                synth.open_editor()                           # returns when the window is closed
                conn.send(('ok', None))
            else:
                conn.send(('err', f'unknown command {cmd}'))
        except Exception as e:                                # noqa – handed back to SmartKit
            conn.send(('err', f'{type(e).__name__}: {e}'))


class DDPlugin:
    """A plugin running in DawDreamer in a helper process, used like a pedalboard plugin."""
    modal_editor = True          # nothing else can be done while its window is open
    one_shot = True              # renders do not continue each other (ring_hit renders the whole ring at once)

    def __init__(self, path, sr=44100, block=512, timeout=180):
        from multiprocessing.connection import Listener
        key = os.urandom(16)
        self._ls = Listener(('127.0.0.1', 0), authkey=key)
        env = dict(os.environ, SMARTKIT_DD_KEY=key.hex())
        flags = 0x08000000 if sys.platform == 'win32' else 0
        here = os.path.dirname(os.path.abspath(__file__))
        self.proc = subprocess.Popen([sys.executable, os.path.join(here, 'ddhost.py'), str(self._ls.address[1])],
                                     env=env, cwd=here, creationflags=flags,
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        box = {}
        th = threading.Thread(target=lambda: box.setdefault('c', self._ls.accept()), daemon=True)
        th.start(); th.join(30)
        if 'c' not in box:
            self.close()
            raise RuntimeError('The DawDreamer helper did not start (is DawDreamer installed?).')
        self._c = box['c']
        self._lock = threading.Lock()
        self.editor_open = False
        self.name, self.outputs = self._call('load', path, sr, block)

    def _call(self, *cmd):
        if self.editor_open and cmd[0] != 'editor':
            raise RuntimeError('Close the plugin window first.')
        with self._lock:
            if self.proc.poll() is not None:
                raise RuntimeError('The plugin helper has stopped (the plugin may have crashed). Load it again.')
            self._c.send(cmd)
            status, r = self._c.recv()
        if status != 'ok':
            raise RuntimeError(r)
        return r

    def __call__(self, msgs, duration, sample_rate=44100, num_channels=2, buffer_size=512, reset=False):
        notes = notes_from_msgs(msgs, duration)
        n = int(round(duration * sample_rate))
        if not notes:                                  # silence: nothing to play (renders start silent anyway)
            return np.zeros((2, n), np.float32)
        a = self._call('render', notes, duration)
        return a[:, :n] if a.shape[1] >= n else np.pad(a, ((0, 0), (0, n - a.shape[1])))

    @property
    def raw_state(self):
        return self._call('get_state')

    @raw_state.setter
    def raw_state(self, data):
        self._call('set_state', bytes(data))

    def show_editor(self, close_event=None):
        """Blocks until the plugin window is closed. Setting close_event closes it."""
        stop = threading.Event()

        def watch():
            while not stop.wait(0.2):
                if close_event is not None and close_event.is_set():
                    _close_windows(self.proc.pid)
                    return
        self.editor_open = True
        threading.Thread(target=watch, daemon=True).start()
        try:
            self._call('editor')
        finally:
            stop.set()
            self.editor_open = False

    def close(self):
        try:
            if getattr(self, '_c', None) is not None:
                self._c.send(('quit',))
        except Exception:
            pass
        try:
            self.proc.wait(5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        try:
            self._ls.close()
        except Exception:
            pass

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def _close_windows(pid):
    """Close the visible top-level windows of a process (the plugin window in the helper)."""
    if sys.platform != 'win32':
        return
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    found = []
    PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(h, _):
        p = wintypes.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and u.IsWindowVisible(h):
            found.append(h)
        return True
    u.EnumWindows(PROC(cb), 0)
    for h in found:
        u.PostMessageW(h, 0x0010, 0, 0)                       # WM_CLOSE


if __name__ == '__main__':
    _worker(('127.0.0.1', int(sys.argv[1])), bytes.fromhex(os.environ['SMARTKIT_DD_KEY']))
