"""Load renders, split long renders into hits, measure each hit."""
import os, re, wave, glob
import numpy as np

VEL_RE = re.compile(r'v(\d{1,3})(?:\D*)\.wav$', re.I)


def read_wav(path):
    """Returns float32 array (frames, channels) and sample rate. Supports 16/24/32-bit PCM and 32-bit float."""
    with open(path, 'rb') as f:
        raw = f.read()
    if raw[:4] != b'RIFF' or raw[8:12] != b'WAVE':
        raise ValueError(f'not a WAV file: {path}')
    o, fmt, data = 12, None, None
    while o + 8 <= len(raw):
        cid = raw[o:o + 4]; n = int.from_bytes(raw[o + 4:o + 8], 'little')
        if cid == b'fmt ':
            fmt = raw[o + 8:o + 8 + n]
        elif cid == b'data':
            data = raw[o + 8:o + 8 + n]
        o += 8 + n + (n & 1)
    tag = int.from_bytes(fmt[0:2], 'little'); ch = int.from_bytes(fmt[2:4], 'little')
    sr = int.from_bytes(fmt[4:8], 'little'); bits = int.from_bytes(fmt[14:16], 'little')
    if tag == 0xFFFE:
        tag = int.from_bytes(fmt[24:26], 'little')
    if tag == 3 and bits == 32:
        a = np.frombuffer(data, '<f4').astype(np.float32)
    elif bits == 16:
        a = np.frombuffer(data, '<i2').astype(np.float32) / 32768
    elif bits == 24:
        b = np.frombuffer(data[:len(data) // 3 * 3], np.uint8).reshape(-1, 3)
        v = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16))
        v = np.where(v & 0x800000, v - 0x1000000, v)
        a = v.astype(np.float32) / 8388608
    elif bits == 32:
        a = np.frombuffer(data, '<i4').astype(np.float32) / 2147483648
    else:
        raise ValueError(f'unsupported WAV format ({bits}-bit) in {path}')
    a = a[:len(a) // ch * ch].reshape(-1, ch)
    return a, sr


def write_wav16(path, a, sr):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    x = np.clip(np.round(a * 32767), -32768, 32767).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(a.shape[1]); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(x.tobytes())


def envelope(a, sr, win_ms=5):
    m = a.mean(1) if a.shape[1] > 1 else a[:, 0]
    n = max(1, int(sr * win_ms / 1000))
    c = np.concatenate([[0.0], np.cumsum(m.astype(np.float64) ** 2)])     # moving average in O(N)
    lo = np.clip(np.arange(len(m)) - n // 2, 0, len(m)); hi = np.clip(lo + n, 0, len(m))
    return np.sqrt((c[hi] - c[lo]) / n + 1e-20)


def split_hits(a, sr, gap_s=0.4, thresh_db=-60):
    """Split a long render (one articulation, many hits) at silences."""
    env = envelope(a, sr)
    on = np.where(env > np.max(env) * 10 ** (thresh_db / 20))[0]
    if not len(on):
        return []
    gap = int(gap_s * sr)
    breaks = np.where(np.diff(on) > gap)[0]
    starts = np.r_[on[0], on[breaks + 1]]
    ends = np.r_[on[breaks], on[-1]]
    pre = int(0.002 * sr)
    return [a[max(0, s - pre):e + 1] for s, e in zip(starts, ends)]


class Hit:
    __slots__ = ('src', 'vel', 'a', 'sr', 'peak', 'loud', 'onset', 'side', 'key', 'loud0', 'comp_gain_db')


def measure(a, sr, src='', vel=None):
    h = Hit(); h.src = src; h.vel = vel; h.sr = sr
    env = envelope(a, sr, 2)
    pk_i = int(np.argmax(env))
    h.peak = float(np.abs(a).max()) + 1e-12
    # onset = first point above -40 dB of this hit's own peak envelope, minus 1 ms
    above = np.where(env > env[pk_i] * 0.01)[0]
    h.onset = max(0, int(above[0]) - int(0.001 * sr)) if len(above) else 0
    a = a[h.onset:]
    h.a = a
    m = a.mean(1)
    # perceived hit loudness: RMS of the first 60 ms (attack + body)
    seg = m[:int(0.06 * sr)]
    h.loud = 20 * np.log10(np.sqrt(np.mean(seg * seg)) + 1e-12)
    if a.shape[1] == 2:
        s = a[:, 0] - a[:, 1]; mm = a[:, 0] + a[:, 1]
        h.side = float(np.sqrt(np.mean(s * s)) / (np.sqrt(np.mean(mm * mm)) + 1e-12))
    else:
        h.side = 0.0
    # fingerprint for duplicate detection
    k = m[:2048].astype(np.float64)
    h.key = k / (np.linalg.norm(k) + 1e-12)
    return h


def load_articulation(folder):
    """All hits for one articulation folder."""
    hits = []
    for f in sorted(glob.glob(os.path.join(folder, '*.wav'))):
        a, sr = read_wav(f)
        mv = VEL_RE.search(os.path.basename(f))
        vel = int(mv.group(1)) if mv else None
        if vel is None and len(a) / sr > 8:  # a long multi-hit render (one hit per file has its velocity in the name)
            for seg in split_hits(a, sr):
                hits.append(measure(seg, sr, f, None))
        else:
            hits.append(measure(a, sr, f, vel))
    # drop empty fragments (silence or a few samples): they would break the build
    return [h for h in hits if len(h.a) >= int(0.02 * h.sr) and h.peak > 1e-5]


def dedupe(hits, corr_min=0.9995, db_tol=0.15):
    """Drop renders that are the same underlying sample (SD3 repeats a layer over many velocities)."""
    keep = []
    for h in sorted(hits, key=lambda x: -x.loud):
        dup = False
        for k in keep:
            if abs(k.loud - h.loud) < db_tol and len(k.key) == len(h.key) and float(np.dot(k.key, h.key)) > corr_min:
                dup = True; break
        if not dup:
            keep.append(h)
    return keep


# ---------------------------------------------------------------- SmartKit Render output
def read_schedule(folder):
    """_notes.csv written by 'SmartKit Render.lua': note,file,ring_seconds,velocities,repeats"""
    import csv
    p = os.path.join(folder, '_notes.csv')
    if not os.path.exists(p):
        return None
    rows = []
    with open(p, newline='') as f:
        for r in csv.DictReader(f):
            rows.append({'note': int(r['note']), 'file': r['file'], 'ring': float(r['ring_seconds']),
                         'vels': [int(v) for v in r['velocities'].split()], 'reps': int(r['repeats'])})
    return rows


def load_scheduled(folder, row, silence_db=-75):
    """Cut a rendered velocity ladder into hits at the exact times the script played them."""
    a, sr = read_wav(os.path.join(folder, row['file']))
    hits, t, ring = [], 0.5, row['ring']
    gpk = float(np.abs(a).max()) + 1e-12
    for v in row['vels']:
        for _ in range(row['reps']):
            s = int(round((t - 0.003) * sr)); e = int(round((t + ring - 0.02) * sr))
            seg = a[max(0, s):min(len(a), e)]
            if len(seg) and np.abs(seg).max() > gpk * 10 ** (silence_db / 20):
                hits.append(measure(seg, sr, row['file'], v))
            t += ring
    return hits


def guess_role(hits):
    """Rough role guess from the loudest hit (the user can correct it in kitmap.csv)."""
    h = max(hits, key=lambda x: x.loud)
    m = h.a.mean(1)
    seg = m[:int(0.25 * h.sr)]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
    f = np.fft.rfftfreq(len(seg), 1 / h.sr)
    tot = spec.sum() + 1e-20
    low = spec[f < 150].sum() / tot          # kick body
    mid = spec[f < 600].sum() / tot          # drum shells
    cen = float((spec * f).sum() / tot)
    env = envelope(h.a, h.sr, 10)
    ring = float(np.where(env > env.max() * 1e-3)[0][-1]) / h.sr
    if low > 0.45 and ring < 1.5:
        role = 'kick'
    elif low > 0.12 and ring > 1.0:
        role = 'tom'
    elif cen > 2300:
        role = 'crash' if ring > 2.5 else 'hihat'
    else:
        role = 'snare'
    return role, cen, ring
