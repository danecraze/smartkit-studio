"""Choose velocity layers, round robins and tail lengths for every articulation so the
whole kit fits the Strike's 200 MiB sample pool with the best sound per byte."""
import math, re
import numpy as np
from strikefmt import sample_ram_bytes

# Quality ladder: (velocity layers, round robins, tail cut-off in dB below the articulation's loudest peak)
LADDER = [(3, 1, -48), (4, 1, -54), (6, 1, -54), (6, 2, -60), (8, 2, -60),
          (10, 2, -66), (12, 3, -66), (16, 3, -72), (20, 4, -72), (24, 4, -78)]
SCORE = [0, 3, 5, 7, 8.5, 9.5, 10.3, 11, 11.5, 11.8]

# How much each kind of drum matters when memory is short (higher = gets upgraded first)
WEIGHT = {'snare': 1.0, 'hihat': 1.0, 'kick': 0.9, 'ride': 0.8, 'tom': 0.6, 'crash': 0.55,
          'rim': 0.45, 'pedal': 0.5, 'other': 0.4}

FADE_MAX_S = 0.25
MIN_STEP_DB = 1.5   # smallest loudness step worth a separate velocity layer
TOP_SHARE = 0.35    # compressed sounds: share of the velocity layers kept for the hard hits


def find_compression(hits, flat_db=2.0, min_span=20):
    """Heavily compressed / limited renders: above some velocity the loudness stops rising (the plugin's
    mixer squashes the hard hits) although the sound still changes. Returns the 'knee' velocity from which
    the loudness stays within flat_db of the loudest, or None when the sound still gets louder to the top."""
    by_v = {}
    for h in hits:
        if h.vel is not None:
            by_v.setdefault(h.vel, []).append(getattr(h, 'loud0', h.loud))
    if len(by_v) < 6:
        return None
    vs = sorted(by_v)
    L = [float(np.median(by_v[v])) for v in vs]
    top = max(L)
    # first velocity that is within flat_db of the loudest, and (almost) everything above it stays there
    knee = next(v for v, l in zip(vs, L) if l >= top - flat_db)
    above = [l for v, l in zip(vs, L) if v >= knee]
    if vs[-1] - knee < min_span or len(above) < 3 or sum(l >= top - flat_db - 1.5 for l in above) < 0.9 * len(above):
        return None
    return knee


def expand_compressed(a, extra_db=8.0, restore=True):
    """Give a compressed articulation its dynamics back: the hard hits (from the knee velocity up) get an
    'effective loudness' rising by extra_db, so the memory planner spends more velocity layers there and the
    velocity ranges follow the plugin's own velocities. With restore, everything below the loudest hit is
    turned down so the played loudness rises again towards the hardest hits."""
    for h in a.hits:
        if not hasattr(h, 'loud0'):
            h.loud0 = h.loud
        h.loud, h.comp_gain_db = h.loud0, 0.0
    a.knee = None
    knee = find_compression(a.hits) if extra_db > 0 else None
    if knee is not None:
        vmax = max(h.vel for h in a.hits if h.vel is not None)
        for h in a.hits:
            add = extra_db * (h.vel - knee) / (vmax - knee) if h.vel is not None and h.vel >= knee else 0.0
            h.loud = h.loud0 + add
            h.comp_gain_db = (add - extra_db) if restore else 0.0
        a.knee = knee
    a.hits = sorted(a.hits, key=lambda h: h.loud)
    a._cache.clear(); a._cost.clear()
    return knee


def classify(name):
    """Role from an SDSE-style or plain articulation name."""
    n = name.lower()
    code = name.split()[-1] if name.split() else name
    c = code.lower()
    if re.fullmatch(r'k\d?', c) or 'kick' in n:
        return 'kick'
    if c in ('hch', 'hsp') or any(k in n for k in ('pedal', 'chick', 'foot')):
        return 'pedal'
    if c in ('snss', 'sns', 'snr', 'snrs', 'snro') or 'sidestick' in n or 'rim' in n or 'cross' in n:
        return 'rim'
    if c.startswith('sn') or 'snare' in n:
        return 'snare'
    if re.fullmatch(r't\d+r', c):
        return 'rim'
    if re.fullmatch(r't\d+', c) or 'tom' in n:
        return 'tom'
    if c in ('hch', 'hsp') or 'pedal' in n or 'chick' in n:
        return 'pedal'
    if c.startswith('h') and re.fullmatch(r'h[be][co]\d?|hbo\d|heo\d|hbt|het|hbel\w*', c) or 'hat' in n:
        return 'hihat'
    if c.startswith('ri') or 'ride' in n:
        return 'ride'
    if re.match(r'(cr|ch|sp)\d', c) or any(k in n for k in ('crash', 'china', 'splash')):
        return 'crash'
    return 'other'


class Artic:
    def __init__(self, name, piece, hits, stereo_ok=True, force_mono=None):
        self.name, self.piece, self.hits = name, piece, sorted(hits, key=lambda h: h.loud)
        self.role = classify(name)
        self.weight = WEIGHT.get(self.role, 0.4)
        self.sr = hits[0].sr
        self.max_peak = max(h.peak for h in hits)
        src_ch = hits[0].a.shape[1]
        wide = np.median([h.side for h in hits]) > 0.15
        if force_mono is not None:
            self.channels = 1 if force_mono else min(2, src_ch)
        else:
            self.channels = 2 if (src_ch == 2 and wide and stereo_ok and self.role in ('crash', 'ride', 'hihat')) else 1
        self.level = 0
        self._cache = {}
        self._env, self._trim, self._cost = {}, {}, {}

    # -------- layer / round-robin selection
    def select(self, n_layers, n_rr):
        key = (n_layers, n_rr)
        if key in self._cache:
            return self._cache[key]
        hs = self.hits                      # sorted soft -> loud
        L = np.array([h.loud for h in hs])
        n_layers = max(1, min(n_layers, len(hs)))
        knee = getattr(self, 'knee', None)
        if knee is not None and n_layers >= 3:
            heads = self._heads_compressed(hs, L, n_layers, knee)
        else:
            heads = self._heads(L, n_layers, range(len(hs)))
        heads.sort()
        # 2) round robins: nearest unused hits within 1 dB of each head (same velocity first)
        used, layers = set(heads), []
        for hd in heads:
            group = [hd]
            near = sorted((hs[i].vel != hs[hd].vel, abs(L[i] - L[hd]), i) for i in range(len(hs))
                          if i not in used and abs(L[i] - L[hd]) <= 1.0)
            for _, d, i in near[:max(0, n_rr - 1)]:
                group.append(i); used.add(i)
            layers.append([hs[i] for i in group])
        if knee is not None and all(h.vel is not None for g in layers for h in g):
            layers.sort(key=lambda g: np.mean([h.vel for h in g]))     # zones follow the plugin's velocities
        else:
            layers.sort(key=lambda g: np.mean([h.loud for h in g]))
        self._cache[key] = layers
        return layers

    def _heads_compressed(self, hs, L, n_layers, knee):
        """Soft part: split by loudness as usual. Hard part (loudness flat): heads spread evenly over the
        plugin's velocities, so the changes in tone between hard hits are kept."""
        hi = [i for i in range(len(hs)) if hs[i].vel is not None and hs[i].vel >= knee]
        lo = [i for i in range(len(hs)) if i not in set(hi)]
        vels = sorted({hs[i].vel for i in hi})
        n_top = min(len(vels), max(1 if n_layers < 5 else 2, round(n_layers * TOP_SHARE)))
        if not lo:
            n_top = min(len(vels), n_layers)
        top = []
        for t in (np.linspace(vels[0], vels[-1], n_top) if n_top > 1 else [vels[-1]]):
            v = min(vels, key=lambda x: abs(x - t))
            cand = [i for i in hi if hs[i].vel == v and i not in top]
            if cand:
                top.append(max(cand, key=lambda i: L[i]))
        bottom = self._heads(L, n_layers - len(top), lo) if lo and n_layers > len(top) else []
        return sorted(set(top + bottom))

    @staticmethod
    def _heads(L, n_layers, idx):
        """Layer heads among the hits idx (sorted soft -> loud): the softest and loudest, then keep splitting
        the biggest loudness gap (steps as even as the source allows, even when the renders have holes)."""
        idx = list(idx)
        if not idx or n_layers <= 0:
            return []
        if n_layers == 1 or len(idx) == 1:
            return [idx[-1]]
        heads = [0, len(idx) - 1]
        while len(heads) < n_layers:
            heads.sort()
            gaps = [(L[idx[b]] - L[idx[a]], a, b) for a, b in zip(heads[:-1], heads[1:]) if b - a > 1]
            if not gaps:
                break
            g, a, b = max(gaps)
            if g < MIN_STEP_DB:          # finer steps than this are not heard: use RR instead
                break
            mid = (L[idx[a]] + L[idx[b]]) / 2
            heads.append(min(range(a + 1, b), key=lambda i: abs(L[idx[i]] - mid)))
        return [idx[i] for i in heads]

    # -------- trimming
    def trim_frames(self, h, tail_db):
        """Frames to keep: until the hit's envelope falls below tail_db relative to the
        articulation's loudest peak (so soft hits get shorter samples), plus fade."""
        from analyse import envelope
        key = (id(h), tail_db)
        if key in self._trim:
            return self._trim[key]
        env = self._env.get(id(h))
        if env is None:
            env = self._env[id(h)] = envelope(h.a, h.sr, 10)
        thr = self.max_peak * 10 ** (tail_db / 20)
        above = np.where(env > thr)[0]
        end = int(above[-1]) + 1 if len(above) else int(0.05 * h.sr)
        r = self._trim[key] = max(int(0.03 * h.sr), min(end, len(h.a)))
        return r

    def cost(self, level):
        if (level, self.channels) in self._cost:
            return self._cost[(level, self.channels)]
        self._cost[(level, self.channels)] = c = self._cost_calc(level)
        return c

    def _cost_calc(self, level):
        n_layers, n_rr, tail_db = LADDER[level]
        total = 0
        for g in self.select(n_layers, n_rr):
            for h in g:
                total += sample_ram_bytes(self.trim_frames(h, tail_db), self.channels)
        return total

    def render(self, level):
        """Final audio for each zone: list of layers -> list of (array, sr)."""
        n_layers, n_rr, tail_db = LADDER[level]
        out = []
        for g in self.select(n_layers, n_rr):
            grp = []
            for h in g:
                n = self.trim_frames(h, tail_db)
                a = h.a[:n].copy()
                g = getattr(h, 'comp_gain_db', 0.0)
                if g:
                    a *= 10 ** (g / 20)          # compressed sound: loudness steps restored
                if self.channels == 1 and a.shape[1] == 2:
                    a = a.mean(1, keepdims=True)
                elif self.channels == 2 and a.shape[1] == 1:
                    a = np.repeat(a, 2, 1)
                f = min(int(FADE_MAX_S * h.sr), len(a) // 3)
                if f > 8:
                    a[-f:] *= (0.5 + 0.5 * np.cos(np.linspace(0, np.pi, f)))[:, None]
                grp.append((a, h))
            out.append(grp)
        return out


def velocity_ranges(layers, curve=1.0, by_vel=False):
    """Map MIDI velocity 1..127 to layers so that the loudness heard rises evenly
    (in dB) with velocity. layers: list of groups sorted soft -> loud."""
    louds = [float(np.mean([h.loud for h in g])) for g in layers]
    if len(louds) == 1:
        return [(1, 127)]
    if by_vel and all(h.vel is not None for g in layers for h in g):
        # follow the plugin's own velocities: switch half-way between the layers' recorded velocities
        vs = [float(np.mean([h.vel for h in g])) for g in layers]
        ranges, start, n = [], 1, len(vs)
        for k in range(n - 1):
            e = int((vs[k] + vs[k + 1]) / 2)
            e = max(start, min(e, 127 - (n - 1 - k)))
            ranges.append((start, e)); start = e + 1
        ranges.append((start, 127))
        return ranges
    lo, hi = louds[0], louds[-1]
    n = len(louds)
    ends = []
    for k, (a, b) in enumerate(zip(louds[:-1], louds[1:])):
        mid = (a + b) / 2  # switch where loudness is half-way between layers
        x = (mid - lo) / (hi - lo) if hi > lo else (k + 1) / n
        ends.append(int(126 * (max(0.0, x) ** (1 / curve))))   # last velocity of layer k
    ranges, start = [], 1
    for k, e in enumerate(ends):
        e = max(start, min(e, 127 - (n - 1 - k)))   # >= 1 velocity each, leave room for the rest
        ranges.append((start, e)); start = e + 1
    ranges.append((start, 127))
    return ranges


def fit_budget(artics, budget_bytes, start_level=0):
    """Greedy: start everything at the lowest rung, then keep buying the upgrade with the
    best (weighted quality gain / extra bytes) until the budget is used."""
    for a in artics:
        a.level = start_level
    used = sum(a.cost(a.level) for a in artics)
    if used > budget_bytes:
        return used, False
    while True:
        best = None
        for a in artics:
            if a.level + 1 >= len(LADDER) or a.weight <= 0:
                continue                                  # top rung reached / priority 0 = keep smallest
            nl, nr, _ = LADDER[a.level + 1]
            if sum(len(g) for g in a.select(nl, nr)) > getattr(a, 'max_zones', 255):
                continue                                  # instrument would exceed 255 zones
            d_cost = a.cost(a.level + 1) - a.cost(a.level)
            d_q = a.weight * (SCORE[a.level + 1] - SCORE[a.level])
            if d_cost <= 0:
                ratio = math.inf
            else:
                ratio = d_q / d_cost
            if used + max(d_cost, 0) <= budget_bytes and (best is None or ratio > best[0]):
                best = (ratio, a, d_cost)
        if best is None:
            break
        _, a, d = best
        a.level += 1; used += d
    return used, True
