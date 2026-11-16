"""SmartKit host: loads a drum VST3 (Superior Drummer 3, Steven Slate Drums ...) with
Spotify's pedalboard and records hits from it.

Rules learned from the feasibility test with SD3 (2026-11-13):
  * never reset the plugin (reset=True / plugin.reset() makes SD3 reload all samples);
    let sounds die away by rendering silence instead;
  * SD3 streams samples from disk on first use, so a fast render can miss the first hit of a
    new velocity -> check each hit and re-render it if it came out silent or far too quiet.
"""
import os, glob, time, wave
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

    # ------------------------------------------------------------ plugin
    def load(self, path, wait=120):
        """pedalboard 'warms up' a plugin by playing middle C (note 60) until it hears something, for up to
        `wait` seconds. In Superior Drummer note 60 is often silent, so it always waited the full time.
        SmartKit checks for sound itself afterwards (wait_until_ready), so a short wait is enough."""
        from pedalboard import load_plugin
        self.plugin = load_plugin(path, initialization_timeout=wait)
        self.path = path
        return getattr(self.plugin, 'name', os.path.basename(path))

    def show_editor(self, keep_audio_running=True, close_event=None):
        """Open the plugin window (blocks until it is closed). Meanwhile feed the plugin silent
        audio blocks at real-time pace, like a DAW does, so it doesn't report
        'Audio Engine Inactive' and keeps loading samples."""
        import threading
        stop = threading.Event()

        def feed():
            t0, n = time.time(), 0
            while not stop.is_set():
                try:
                    self._run([], BLOCK / SR)
                except Exception:
                    return
                n += 1
                ahead = n * BLOCK / SR - (time.time() - t0)
                if ahead > 0:
                    time.sleep(ahead)
        th = threading.Thread(target=feed, daemon=True) if keep_audio_running else None
        if th: th.start()
        try:
            self.plugin.show_editor(close_event) if close_event is not None else self.plugin.show_editor()
        finally:
            stop.set()
            if th: th.join(2)

    def save_state(self, path):
        open(path, 'wb').write(self.plugin.raw_state)

    def restore_state(self, path):
        self.plugin.raw_state = open(path, 'rb').read()

    # ------------------------------------------------------------ audio
    def _run(self, msgs, seconds):
        a = self.plugin(msgs, duration=seconds, sample_rate=SR, num_channels=2, buffer_size=BLOCK, reset=False)
        a = np.asarray(a, np.float32)
        return a.T if a.shape[0] == 2 and a.shape[1] != 2 else a

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

    def ring_hit(self, note, vel=127, chunk=2.0, max_s=20.0, floor_db=-60):
        """Play one hit and keep recording until it has died away; returns audio, ring time."""
        out, a0 = [], None
        for attempt in range(6):                    # silent: the plugin is still streaming the sample from disk;
            a0 = self._run([(bytes([0x90, note, vel]), 0.01), (bytes([0x80, note, 0]), 0.11)], chunk)
            if np.abs(a0).max() > 1e-4:             # give it real (wall-clock) time, not just rendered silence
                break
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


def estimate_seconds(notes, vels, reps, speed=1.9):
    audio = sum(min(max(n['ring'] + 0.4, 0.8), 22.0) * len(vels) * reps for n in notes)
    return audio / max(speed, 0.1), audio
