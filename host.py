"""SmartKit host: loads a drum VST3 (Superior Drummer 3, Steven Slate Drums ...) with
Spotify's pedalboard and records hits from it.

Rules learned from the feasibility test with SD3 (2026-11-13):
  * never reset the plugin (reset=True / plugin.reset() makes SD3 reload all samples);
    let sounds die away by rendering silence instead;
  * SD3 streams samples from disk on first use, so a fast render can miss the first hit of a
    new velocity -> check each hit and re-render it if it came out silent or far too quiet.
"""
import os, sys, glob, time, wave, queue, threading
import numpy as np

SR = 44100
BLOCK = 512
VST3_DIRS = [r'C:\Program Files\Common Files\VST3',
             os.path.expanduser(r'~\AppData\Local\Programs\Common\VST3')]

GM_NAMES = {35: 'Kick 2', 36: 'Kick', 37: 'Snare Sidestick', 38: 'Snare', 39: 'Clap', 40: 'Snare Rimshot',
            41: 'Tom 4 (floor)', 42: 'Hats Closed', 43: 'Tom 3', 44: 'Hats Pedal', 45: 'Tom 2', 46: 'Hats Open',
            47: 'Tom 2b', 48: 'Tom 1', 49: 'Crash 1', 50: 'Tom 1b', 51: 'Ride', 52: 'China', 53: 'Ride Bell',
            55: 'Splash', 57: 'Crash 2', 59: 'Ride 2'}


class Cancelled(Exception):
    pass


class PluginThread:
    """One thread that loads plugins and shows their windows. The plugin framework (JUCE) makes the thread that
    loads the first plugin its 'message thread', and plugin windows can only open there. Doing that here instead
    of on the main thread keeps SmartKit's window working while a plugin window is open."""

    def __init__(self):
        self.q = queue.Queue()
        threading.Thread(target=self._loop, daemon=True, name='plugin').start()

    def _loop(self):
        if sys.platform == 'win32':
            try:
                import ctypes
                ctypes.windll.ole32.CoInitializeEx(None, 2)        # plugin windows want a COM apartment
            except Exception:
                pass
        pump = self._win_pump() if sys.platform == 'win32' else (lambda: None)
        while True:
            pump()                                   # be a real message thread: plugins post work to it
            try:
                fn, box, ev = self.q.get(timeout=0.01)
            except queue.Empty:
                continue
            try:
                box['r'] = fn()
            except BaseException as e:                              # noqa – handed back to the caller
                box['e'] = e
            ev.set()

    @staticmethod
    def _win_pump():
        """Dispatch the Windows messages waiting for this thread (JUCE's message queue lives there: plugins
        use it to finish loading kits, run timers …)."""
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        u.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT,
                                   wintypes.UINT]
        u.TranslateMessage.argtypes = u.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        msg = wintypes.MSG()

        def pump():
            for _ in range(200):
                if not u.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):      # PM_REMOVE
                    break
                u.TranslateMessage(ctypes.byref(msg))
                u.DispatchMessageW(ctypes.byref(msg))
        return pump

    def call(self, fn, wait=True):
        box, ev = {}, threading.Event()
        self.q.put((fn, box, ev))
        if not wait:
            return ev, box
        ev.wait()
        if 'e' in box:
            raise box['e']
        return box.get('r')


def wave_outputs():
    """Names of the Windows audio outputs (e.g. 'Speakers (Focusrite USB Audio)')."""
    if sys.platform != 'win32':
        return []
    import ctypes
    from ctypes import wintypes

    class WAVEOUTCAPSW(ctypes.Structure):
        _fields_ = [('wMid', wintypes.WORD), ('wPid', wintypes.WORD), ('vDriverVersion', wintypes.UINT),
                    ('szPname', wintypes.WCHAR * 32), ('dwFormats', wintypes.DWORD), ('wChannels', wintypes.WORD),
                    ('wReserved1', wintypes.WORD), ('dwSupport', wintypes.DWORD)]
    mm, out = ctypes.windll.winmm, []
    for i in range(mm.waveOutGetNumDevs()):
        c = WAVEOUTCAPSW()
        if mm.waveOutGetDevCapsW(i, ctypes.byref(c), ctypes.sizeof(c)) == 0:
            out.append(c.szPname)
    return out


class WaveOut:
    """Plays float stereo blocks on a Windows audio output (plain waveOut, ~90 ms latency).
    write() waits while all buffers are playing, so it paces the caller in real time."""

    def __init__(self, device='', sr=SR, frames=1024, nbuf=4):
        import ctypes
        from ctypes import wintypes

        class WAVEFORMATEX(ctypes.Structure):
            _fields_ = [('wFormatTag', wintypes.WORD), ('nChannels', wintypes.WORD), ('nSamplesPerSec', wintypes.DWORD),
                        ('nAvgBytesPerSec', wintypes.DWORD), ('nBlockAlign', wintypes.WORD),
                        ('wBitsPerSample', wintypes.WORD), ('cbSize', wintypes.WORD)]

        class WAVEHDR(ctypes.Structure):
            _fields_ = [('lpData', ctypes.c_void_p), ('dwBufferLength', wintypes.DWORD),
                        ('dwBytesRecorded', wintypes.DWORD), ('dwUser', ctypes.c_void_p), ('dwFlags', wintypes.DWORD),
                        ('dwLoops', wintypes.DWORD), ('lpNext', ctypes.c_void_p), ('reserved', ctypes.c_void_p)]
        self.ct, mm = ctypes, ctypes.windll.winmm
        PH = ctypes.POINTER(WAVEHDR)
        mm.waveOutOpen.argtypes = [ctypes.POINTER(ctypes.c_void_p), wintypes.UINT, ctypes.POINTER(WAVEFORMATEX),
                                   ctypes.c_size_t, ctypes.c_size_t, wintypes.DWORD]
        for fn in ('waveOutPrepareHeader', 'waveOutWrite', 'waveOutUnprepareHeader'):
            getattr(mm, fn).argtypes = [ctypes.c_void_p, PH, wintypes.UINT]
        for fn in ('waveOutReset', 'waveOutClose'):
            getattr(mm, fn).argtypes = [ctypes.c_void_p]
        names = wave_outputs()
        dev = names.index(device) if device in names else 0xFFFFFFFF          # WAVE_MAPPER = Windows default
        self.mm, self.h = mm, ctypes.c_void_p()
        fmt = WAVEFORMATEX(1, 2, sr, sr * 4, 4, 16, 0)
        r = mm.waveOutOpen(ctypes.byref(self.h), dev, ctypes.byref(fmt), 0, 0, 0)
        if r:
            raise RuntimeError(f'Could not open the audio output (error {r}).')
        self.blen = frames * 4
        self.bufs = [ctypes.create_string_buffer(self.blen) for _ in range(nbuf)]
        self.hdrs = [WAVEHDR(ctypes.addressof(b), self.blen, 0, None, 0, 0, None, None) for b in self.bufs]
        self.sz, self.queued, self.k, self.pending = ctypes.sizeof(WAVEHDR), [False] * nbuf, 0, b''
        for hd in self.hdrs:
            mm.waveOutPrepareHeader(self.h, ctypes.byref(hd), self.sz)

    def write(self, a, stop=None):
        x = np.clip(np.asarray(a, np.float32), -1, 1)
        if x.ndim == 1: x = np.stack([x, x], 1)
        self.pending += (x[:, :2] * 32767).astype('<i2').tobytes()
        while len(self.pending) >= self.blen:
            hd = self.hdrs[self.k]
            while self.queued[self.k] and not (hd.dwFlags & 1):         # WHDR_DONE
                if stop is not None and stop.is_set():
                    return
                time.sleep(0.003)
            self.ct.memmove(self.bufs[self.k], self.pending[:self.blen], self.blen)
            self.pending = self.pending[self.blen:]
            hd.dwFlags &= ~1
            self.mm.waveOutWrite(self.h, self.ct.byref(hd), self.sz)
            self.queued[self.k] = True
            self.k = (self.k + 1) % len(self.hdrs)

    def close(self):
        try:
            self.mm.waveOutReset(self.h)
            for hd in self.hdrs:
                self.mm.waveOutUnprepareHeader(self.h, self.ct.byref(hd), self.sz)
            self.mm.waveOutClose(self.h)
        except Exception:
            pass


def find_plugins():
    found = []
    for d in VST3_DIRS:
        for p in glob.glob(os.path.join(d, '**', '*.vst3'), recursive=True):
            if '.vst3' + os.sep in p:      # file inside a bundle folder
                continue
            found.append(p)
    return sorted(set(found), key=lambda p: os.path.basename(p).lower())


def write_wav_float(path, a, sr=SR):
    """32-bit float WAV (keeps hits that peak over 0 dBFS)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    a = np.asarray(a, np.float32)
    data = a.astype('<f4').tobytes()
    ch = a.shape[1]
    hdr = b'RIFF' + (4 + 26 + 8 + len(data)).to_bytes(4, 'little') + b'WAVE'
    fmt = (3).to_bytes(2, 'little') + ch.to_bytes(2, 'little') + sr.to_bytes(4, 'little') + \
          (sr * ch * 4).to_bytes(4, 'little') + (ch * 4).to_bytes(2, 'little') + (32).to_bytes(2, 'little') + b'\0\0'
    with open(path, 'wb') as f:
        f.write(hdr + b'fmt ' + len(fmt).to_bytes(4, 'little') + fmt + b'data' + len(data).to_bytes(4, 'little') + data)


def write_wav16(path, a, sr=SR):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    x = np.clip(np.round(np.asarray(a) * 32767), -32768, 32767).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(x.shape[1]); w.setsampwidth(2); w.setframerate(sr); w.writeframes(x.tobytes())


class DrumHost:
    def __init__(self):
        self.plugin = None
        self.path = None
        self.speed = None          # measured render speed (x real time)
        self.channel = 0           # MIDI channel the plugin listens on (0 = channel 1; found by sound_check)
        self.realtime = False      # render at real-time pace (for samplers that only stream while audio flows)
        self.audio_out = ''        # Windows output for the live sound of the plugin window ('' = default, 'off')
        self.hold = False          # a job (Find sounds, Record …) owns the plugin: live sound pauses
        self.editor_open = False
        self._lock = threading.RLock()
        self._pt = None
        self.player = 'pedalboard'

    # ------------------------------------------------------------ plugin
    def load(self, path, wait=120, player='auto', log=None):
        """pedalboard 'warms up' a plugin by playing middle C (note 60) until it hears something, for up to
        `wait` seconds. In Superior Drummer note 60 is often silent, so it always waited the full time.
        SmartKit checks for sound itself afterwards (wait_until_ready), so a short wait is enough.
        player: 'pedalboard', 'dawdreamer' or 'auto' (DawDreamer for plugins known to be silent in pedalboard)."""
        import ddhost
        if self.editor_open:
            raise RuntimeError('Close the plugin window first.')
        self.unload()
        self.channel, self.realtime = 0, False
        if player == 'dawdreamer' or (player == 'auto' and ddhost.wants_dd(path)):
            if not ddhost.available() and not ddhost.install(log):
                raise RuntimeError('DawDreamer (needed for this plugin) could not be installed. '
                                   'Check the internet connection and try again.')
            self.plugin = ddhost.DDPlugin(path, sr=SR, block=BLOCK)
            self.player = 'dawdreamer'
        else:
            from pedalboard import load_plugin
            if self._pt is None:
                self._pt = PluginThread()
            self.plugin = self._pt.call(lambda: load_plugin(path, initialization_timeout=wait))
            self.player = 'pedalboard'
        self.path = path
        return getattr(self.plugin, 'name', os.path.basename(path))

    def unload(self):
        p, self.plugin = self.plugin, None
        if p is not None and hasattr(p, 'close'):
            try:
                p.close()
            except Exception:
                pass

    def switch_player(self, log=None):
        """The plugin is silent in pedalboard: load it in DawDreamer instead, with the same kit.
        Returns True when switched."""
        import ddhost
        if self.player != 'pedalboard' or not self.path:
            return False
        try:
            state = self.get_state()
        except Exception:
            state = None
        self.load(self.path, player='dawdreamer', log=log)
        if state:
            self.plugin.raw_state = state
        return True

    def open_editor(self, close_event, on_closed=None):
        """Open the plugin window on the plugin thread and return at once (SmartKit stays usable).
        While it is open the plugin runs like in a DAW: its sound goes to the chosen audio output, so drums
        clicked in the plugin window can be heard. on_closed(error) runs (on the plugin thread) when it closes."""
        stop = threading.Event()

        def live():
            if getattr(self.plugin, 'modal_editor', False):
                return                                 # DawDreamer: no live sound while its window is open
            out = None
            if self.audio_out != 'off' and sys.platform == 'win32':
                try:
                    out = WaveOut(self.audio_out)
                except Exception:
                    out = None
            t0, n = time.time(), 0
            try:
                while not stop.is_set():
                    if self.hold:                      # Find sounds / Record is using the plugin
                        time.sleep(0.02); t0, n = time.time(), 0; continue
                    try:
                        with self._lock:
                            a = self.plugin([], duration=BLOCK * 2 / SR, sample_rate=SR, num_channels=2,
                                            buffer_size=BLOCK, reset=False)
                    except Exception:
                        return
                    if out is not None:
                        a = np.asarray(a, np.float32)
                        out.write(a.T if a.shape[0] == 2 and a.shape[1] != 2 else a, stop)
                    else:
                        n += 1
                        ahead = n * BLOCK * 2 / SR - (time.time() - t0)
                        if ahead > 0:
                            time.sleep(ahead)
            finally:
                if out is not None:
                    out.close()

        def run():
            self.editor_open = True
            th = threading.Thread(target=live, daemon=True); th.start()
            err = None
            try:
                self.plugin.show_editor(close_event)
            except Exception as e:
                err = e
            finally:
                stop.set(); th.join(2)
                self.editor_open = False
            if on_closed:
                on_closed(err)
        if self._pt is None:
            self._pt = PluginThread()
        self._pt.call(run, wait=False)

    def get_state(self):
        with self._lock:
            return self.plugin.raw_state

    def save_state(self, path):
        open(path, 'wb').write(self.get_state())

    def restore_state(self, path):
        self.set_state(open(path, 'rb').read())

    def set_state(self, data):
        def put():
            with self._lock:
                self.plugin.raw_state = data
        if self._pt is not None and not self.editor_open:
            self._pt.call(put)
        else:
            put()

    # ------------------------------------------------------------ audio
    def _msgs(self, msgs):
        """Note on/off messages on the plugin's channel."""
        if not self.channel:
            return msgs
        return [(bytes([m[0] & 0xF0 | self.channel]) + bytes(m[1:]) if m and 0x80 <= m[0] < 0xF0 else m, t)
                for m, t in msgs]

    def _run(self, msgs, seconds):
        msgs = self._msgs(msgs)
        if self.realtime and seconds > BLOCK / SR:
            return self._run_realtime(msgs, seconds)
        with self._lock:
            a = self.plugin(msgs, duration=seconds, sample_rate=SR, num_channels=2, buffer_size=BLOCK, reset=False)
        a = np.asarray(a, np.float32)
        return a.T if a.shape[0] == 2 and a.shape[1] != 2 else a

    def _run_realtime(self, msgs, seconds, step=0.1):
        """Render in short pieces, no faster than real time (like a DAW playing)."""
        out, t0, done = [], time.time(), 0.0
        while done < seconds - 1e-9:
            d = min(step, seconds - done)
            part = [(m, t - done) for m, t in msgs if done <= t < done + d]
            with self._lock:
                a = self.plugin(part, duration=d, sample_rate=SR, num_channels=2, buffer_size=BLOCK, reset=False)
            a = np.asarray(a, np.float32)
            out.append(a.T if a.shape[0] == 2 and a.shape[1] != 2 else a)
            done += d
            ahead = done - (time.time() - t0)
            if ahead > 0:
                time.sleep(ahead)
        return np.concatenate(out)

    def sound_check(self, note, log=None, cancel=None):
        """Find how this plugin makes sound: MIDI channel 1 or 10, rendered fast or at real-time pace.
        Sets self.channel / self.realtime. Returns True when a hit was heard."""
        tries = [(0, False), (9, False), (0, True), (9, True)]
        one_shot = getattr(self.plugin, 'one_shot', False)
        if one_shot:                                 # DawDreamer: channel 1, rendered; give it time to load samples
            tries = [(0, False)]
        for rnd in range(8 if one_shot else 4):
            for ch, rt in tries:
                if cancel and cancel(): raise Cancelled()
                self.channel, self.realtime = ch, rt
                a = self._run([(bytes([0x90, note, 127]), 0.02), (bytes([0x80, note, 0]), 0.12)], 1.5)
                pk = float(np.abs(a).max())
                if log: log(f'  sound check: note {note}, MIDI channel {ch + 1}, '
                            f'{"real time" if rt else "fast"} → peak {20 * np.log10(max(pk, 1e-9)):.0f} dB')
                if pk > 1e-4:
                    self.silence(2.0)
                    return True
                self.silence(0.5)
            if one_shot:
                time.sleep(2.0); continue
            self.channel, self.realtime = 0, True    # play silence in real time for a while, like a DAW does,
            self.silence(3.0)                        # so a plugin that loads its kit only while audio runs can finish
        self.channel, self.realtime = 0, False
        return False

    def silence(self, seconds=1.0):
        self._run([], seconds)

    def wait_until_ready(self, note=38, timeout=180, cancel=None):
        """After loading a kit SD3 keeps loading samples in the background: wait for sound."""
        t = time.time()
        while time.time() - t < timeout:
            if cancel and cancel(): raise Cancelled()
            a = self._run([(bytes([0x90, note, 127]), 0.02), (bytes([0x80, note, 0]), 0.1)], 1.0)
            if np.abs(a).max() > 1e-4:
                self.silence(2.0)
                return time.time() - t
            time.sleep(1.5)
        return None

    def hit(self, note, vel, seconds, retries=3, expect_peak=None):
        """One hit; re-rendered if it comes out silent / far too quiet (sample not streamed in yet)."""
        for attempt in range(retries + 1):
            t = time.time()
            a = self._run([(bytes([0x90, note, vel]), 0.01), (bytes([0x80, note, 0]), 0.11)], seconds)
            took = time.time() - t
            self.speed = seconds / max(took, 1e-3) if self.speed is None else 0.8 * self.speed + 0.2 * seconds / max(took, 1e-3)
            pk = float(np.abs(a).max())
            bad = pk < 1e-4 or (expect_peak is not None and vel >= 10 and pk < expect_peak * 1e-3)
            if not bad:
                return a, attempt
            time.sleep(0.3 * (attempt + 1))
            self.silence(1.0)
        return a, retries + 1

    def ring_hit(self, note, vel=127, chunk=2.0, max_s=20.0, floor_db=-60, tries=6):
        """Play one hit and keep recording until it has died away; returns audio, ring time.
        tries: how often a silent note is played again (the plugin may still be loading its samples)."""
        out, a0 = [], None
        if getattr(self.plugin, 'one_shot', False):    # renders don't continue each other: render the whole ring
            chunk = max_s
        for attempt in range(tries):                    # silent: the plugin is still streaming the sample from disk;
            a0 = self._run([(bytes([0x90, note, vel]), 0.01), (bytes([0x80, note, 0]), 0.11)], chunk)
            if np.abs(a0).max() > 1e-4:             # give it real (wall-clock) time, not just rendered silence
                break
            if attempt + 1 < tries:
                time.sleep(0.3 * (attempt + 1))
                self.silence(1.0)
        out.append(a0)
        pk = float(np.abs(a0).max())
        if pk < 1e-4:
            return None, 0.0
        thr = pk * 10 ** (floor_db / 20)
        total = chunk
        while total < max_s and np.abs(out[-1][-int(0.2 * SR):]).max() > thr:
            out.append(self._run([], chunk)); total += chunk
        a = np.concatenate(out)
        m = np.abs(a).max(1)
        idx = np.where(m > thr)[0]
        ring = (idx[-1] / SR) if len(idx) else chunk
        self.silence(0.5)
        return a[:idx[-1] + 1 if len(idx) else len(a)], ring

    # ------------------------------------------------------------ jobs
    def probe(self, notes, folder, progress=None, cancel=None):
        """Play every note once at 127. Returns [{note, ring, peak, file}] for notes that make a sound."""
        found = []
        for i, n in enumerate(notes):
            if cancel and cancel(): raise Cancelled()
            if progress: progress(i, len(notes), f'Listening to note {n} ...')
            a, ring = self.ring_hit(n)
            if a is None:
                continue
            f = os.path.join(folder, f'N{n:03d}.wav')
            write_wav_float(f, a)
            found.append({'note': n, 'ring': round(float(ring), 2), 'peak': float(np.abs(a).max()), 'file': f})
        if progress: progress(len(notes), len(notes), f'{len(found)} notes make a sound')
        return found

    def render_note(self, note, vels, reps, ring, folder, progress=None, cancel=None, done0=0, total=1):
        """Velocity ladder (loud -> soft) x repeats; one WAV per hit: '<folder>/r1 v127.wav'."""
        seconds = min(max(ring + 0.4, 0.8), 22.0)
        max_pk, retried = None, 0
        k = 0
        for v in vels:
            for r in range(1, reps + 1):
                if cancel and cancel(): raise Cancelled()
                a, att = self.hit(note, v, seconds, expect_peak=max_pk)
                retried += att
                pk = float(np.abs(a).max())
                if pk > 1e-5:
                    write_wav_float(os.path.join(folder, f'r{r} v{v}.wav'), a)
                    max_pk = pk if max_pk is None else max(max_pk, pk)
                k += 1
                if progress: progress(done0 + k, total, f'Note {note}: velocity {v}, take {r}')
        return retried


TYPICAL_RING = {'kick': 1.5, 'snare': 2.0, 'rim': 1.0, 'tom': 3.0, 'hihat': 2.5, 'pedal': 1.0, 'crash': 8.0,
                'ride': 10.0, 'other': 2.0}


def estimate_seconds(notes, vels, reps, speed=1.9):
    ring = lambda n: n.get('ring') or TYPICAL_RING.get(n.get('role'), 3.0)     # not measured yet: typical
    audio = sum(min(max(ring(n) + 0.4, 0.8), 22.0) * len(vels) * reps for n in notes)
    return audio / max(speed, 0.1), audio
