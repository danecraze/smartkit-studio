"""Strike pad Level (0–99) → dB.

MEASURED is the curve measured on a Strike Pro (firmware 1.5) on 2026-11-17: SmartKit's level test kit (one
tone on 12 pads at Levels 99 … 20, velocity → level off, no effects), module outputs recorded through an
audio interface. Repeats agreed within 0.02 dB. The Level is a firmware table, so it is the same on every
module with this firmware. build_test_kit() and analyse() stay here to measure again if a firmware changes it.
"""
import os
import numpy as np

import strikefmt as SF

KIT = 'SmartKit Level Test'
LEVELS = [99, 95, 90, 85, 80, 75, 70, 60, 50, 40, 30, 20]
PADS = ['K1H', 'S1H', 'S1R', 'T1H', 'T1R', 'T2H', 'T2R', 'T3H', 'T3R', 'T4H', 'T4R', 'C1B']
PAD_NAMES = {'K1H': 'Kick', 'S1H': 'Snare head', 'S1R': 'Snare rim', 'T1H': 'Tom 1 head', 'T1R': 'Tom 1 rim',
             'T2H': 'Tom 2 head', 'T2R': 'Tom 2 rim', 'T3H': 'Tom 3 head', 'T3R': 'Tom 3 rim', 'T4H': 'Tom 4 head',
             'T4R': 'Tom 4 rim', 'C1B': 'Crash 1 bow'}
NOTE0 = 60                       # pad i plays MIDI note 60 + i
SR = 48000
TONE_S, TONE_DB, TONE_HZ = 0.5, -6.0, 997.0
REPEATS = 3

# Provisional curve until a measurement exists: the firmware's voice LevelTbl (app image 0xDDF1C, 202 u16
# entries, 'voices\\vparam.c … numberof(LevelTbl)'), read as index = 2 × Level. Not confirmed on the module.
_FW = [0, 6, 11, 16, 22, 27, 33, 38, 44, 50, 56, 62, 68, 74, 81, 87, 94, 101, 108, 115, 123, 130, 138, 145, 153, 161,
       170, 178, 187, 195, 204, 213, 223, 232, 242, 252, 262, 272, 283, 293, 304, 315, 327, 338, 350, 362, 375, 387,
       400, 413, 427, 440, 454, 468, 483, 498, 513, 528, 544, 560, 576, 593, 610, 628, 645, 663, 682, 701, 720, 740,
       760, 780, 801, 822, 844, 866, 889, 912, 936, 960, 984, 1009, 1035, 1061, 1087, 1115, 1142, 1171, 1199, 1229,
       1259, 1289, 1321, 1353, 1385, 1418, 1452, 1487, 1522, 1558, 1595, 1632, 1671, 1710, 1750, 1790, 1832, 1874,
       1917, 1961, 2006, 2052, 2099, 2147, 2196, 2245, 2296, 2348, 2401, 2455, 2510, 2566, 2623, 2682, 2741, 2802,
       2864, 2928, 2993, 3059, 3126, 3195, 3265, 3336, 3409, 3484, 3560, 3638, 3717, 3798, 3880, 3964, 4050, 4138,
       4227, 4318, 4411, 4506, 4603, 4702, 4803, 4906, 5011, 5118, 5228, 5339, 5453, 5570, 5688, 5809, 5933, 6059,
       6187, 6319, 6452, 6589, 6728, 6871, 7016, 7164, 7315, 7469, 7627, 7787, 7951, 8119, 8289, 8463, 8641, 8822,
       9007, 9196, 9389, 9585, 9786, 9990, 10199, 10412, 10630, 10852, 11078, 11309, 11545, 11785, 12031, 12281,
       12537, 12800, 13312, 14336, 16383]
MEASURED = {99: 0.0, 95: -2.51, 90: -4.33, 85: -5.6, 80: -7.47, 75: -10.3, 70: -12.14, 60: -15.91, 50: -19.87,
            40: -23.83, 30: -28.42, 20: -34.69}
PROVISIONAL = {L: round(20 * np.log10(max(_FW[2 * L], 1) / _FW[198]), 2) for L in range(1, 100)}


# ---------------------------------------------------------------- curve use
def _points(curve):
    pts = sorted((int(k), float(v)) for k, v in (curve or MEASURED).items())
    if not any(L == 99 for L, _ in pts):
        pts.append((99, 0.0))
    return pts


def db_for_level(curve, level):
    """dB relative to Level 99 (interpolated between measured Levels, extrapolated below)."""
    pts = _points(curve)
    if level <= 0:
        return -120.0
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    if level < xs[0]:                                    # below the lowest point: keep its slope
        if len(xs) > 1:
            s = (ys[1] - ys[0]) / (xs[1] - xs[0])
        else:
            s = 0.4
        return ys[0] - s * (xs[0] - level)
    return float(np.interp(level, xs, ys))


def level_for_db(curve, db):
    """The Level (1–99) whose loudness is closest to `db` (≤ 0) relative to Level 99."""
    if db >= 0:
        return 99
    best = min(range(1, 100), key=lambda L: abs(db_for_level(curve, L) - db))
    return best


# ---------------------------------------------------------------- the test kit
def card_root(path):
    """The folder that holds Kits / Instruments / Samples. Picking E:\\Kits (or Instruments / Samples) by mistake
    would otherwise give E:\\Kits\\Kits\\… and kits whose instruments cannot be found."""
    p = os.path.normpath(path)
    if os.path.basename(p).lower() in ('kits', 'instruments', 'samples', 'loops'):
        parent = os.path.dirname(p)
        if any(os.path.isdir(os.path.join(parent, d)) for d in ('Kits', 'Instruments', 'Samples')) or \
                os.path.basename(p).lower() == 'kits':
            return parent
    return p


def build_test_kit(out, template, channel=10):  # (developer tool: re-measure the curve)
    """Write Kits/SmartKit Level Test.skt, its instrument and the tone sample under `out` (SD card or folder)."""
    out = card_root(out)
    n = int(SR * TONE_S)
    t = np.arange(n) / SR
    fade = int(0.01 * SR)
    env = np.ones(n)
    env[:fade] = np.sin(np.linspace(0, np.pi / 2, fade)) ** 2
    env[-fade:] = env[:fade][::-1]
    tone = 10 ** (TONE_DB / 20) * np.sin(2 * np.pi * TONE_HZ * t) * env
    pcm = (np.clip(tone, -1, 1) * 32767).astype('<i2')
    stereo = np.repeat(pcm[:, None], 2, axis=1)            # stereo like factory samples
    wav = os.path.join(out, 'Samples', KIT, 'LEVEL TONE.wav')
    os.makedirs(os.path.dirname(wav), exist_ok=True)
    import wave
    with wave.open(wav, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(stereo.tobytes())

    sample = f':{KIT}/LEVEL TONE.wav'
    zone = SF.make_zone(0, 1, 127, first_of_group=True, gain=64)
    defaults = SF.layer_bytes(index=0, level=99, decay=99, vel_level=0)
    sin = SF.write_sin([zone], [sample], category=SF.CAT_NORMAL, defaults=defaults)
    inst = os.path.join(out, 'Instruments', KIT, 'LEVEL TONE.sin')
    os.makedirs(os.path.dirname(inst), exist_ok=True)
    open(inst, 'wb').write(sin)

    path = f':{KIT}/LEVEL TONE.sin'
    assign = {p: path for p in PADS}
    layer_kw = {p: dict(level=L, decay=99, vel_level=0) for p, L in zip(PADS, LEVELS)}
    pad_patch = {p: {44: 0, 45: 0, 46: 0, 61: 0, 49: 0, 51: (channel - 1) & 15, 52: NOTE0 + i}
                 for i, p in enumerate(PADS)}
    header = {2: 99, 8: 255, 11: 0, 12: 255, 24: 255, 36: 255, 43: 255}     # kit level 99, all effects off
    skt = SF.write_skt_from_template(open(template, 'rb').read(), assign, layer_kw=layer_kw,
                                     default_layer={'vel_level': 0}, pad_patch=pad_patch, header_patch=header)
    kitf = os.path.join(out, 'Kits', KIT + '.skt')
    os.makedirs(os.path.dirname(kitf), exist_ok=True)
    open(kitf, 'wb').write(skt)
    return kitf


def pad_order_text():
    return '\n'.join(f'{i + 1:2d}. {PAD_NAMES[p]:<12} Level {L}' for i, (p, L) in enumerate(zip(PADS, LEVELS)))


# ---------------------------------------------------------------- analysis
def _read(path):
    from analyse import read_wav
    x, sr = read_wav(path)
    x = x.astype(np.float64)
    return (x.mean(axis=1) if x.ndim == 2 else x), sr


def find_bursts(x, sr):
    """Tone bursts: (start, end, level dB) – level = RMS of the middle of each burst."""
    hop = int(0.005 * sr)
    n = len(x) // hop
    e = np.sqrt(np.mean(x[:n * hop].reshape(n, hop) ** 2, axis=1) + 1e-20)
    edb = 20 * np.log10(e)
    floor = np.percentile(edb, 20)
    thr = floor + 10
    on = edb > thr
    out, i = [], 0
    while i < n:
        if on[i]:
            j = i
            while j < n and (on[j] or (j + 4 < n and on[j:j + 5].any())):   # bridge tiny dips
                j += 1
            dur = (j - i) * hop / sr
            if dur >= 0.25:
                a, b = i * hop, j * hop
                m = int((b - a) * 0.2)
                seg = x[a + m:b - m]
                out.append((a / sr, b / sr, 20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-20)))
            i = j
        else:
            i += 1
    return out, floor


def analyse(path, levels=LEVELS):
    """Return (curve {level: dB rel. to Level 99}, report text). Raises ValueError when the recording does
    not match the test (wrong number of steps, not getting quieter …)."""
    x, sr = _read(path)
    bursts, floor = find_bursts(x, sr)
    if not bursts:
        raise ValueError('No tone found in the recording. Was the module\'s output recorded, and loud enough?')
    groups = []                                           # repeats of one pad sit within 1 dB of each other
    for b in bursts:
        if groups and abs(b[2] - np.median([g[2] for g in groups[-1]])) < 1.0:
            groups[-1].append(b)
        else:
            groups.append([b])
    vals = [float(np.median([g[2] for g in grp])) for grp in groups]
    if len(vals) != len(levels):
        raise ValueError(f'Found {len(vals)} level steps ({len(bursts)} tones), expected {len(levels)}. '
                         'Record the whole test, one pad after the other in the listed order.\n'
                         'Steps found (dB): ' + ', '.join(f'{v:.1f}' for v in vals))
    if any(b > a + 0.3 for a, b in zip(vals, vals[1:])):
        raise ValueError('The steps do not get quieter one after the other – were the pads played in order?\n'
                         + ', '.join(f'{v:.1f}' for v in vals))
    top = vals[0]
    curve = {int(L): round(v - top, 2) for L, v in zip(levels, vals)}
    if vals[-1] - floor < 15:
        report_floor = f' (the quietest step is only {vals[-1] - floor:.0f} dB above the noise – record louder)'
    else:
        report_floor = ''
    rep = 'Level → dB below Level 99:\n' + '\n'.join(
        f'  {L:3d}  {curve[L]:+6.2f} dB   (built in {MEASURED.get(L, 0):+6.2f})' for L in levels) + report_floor
    return curve, rep
