"""Smart Strike Kit builder.

Turns rendered drum hits (one folder per articulation) into a Strike / Strike Pro kit that
fits the module's 200 MiB sample memory, spending the memory where it is heard most.

Usage:
  python smartkit.py <renders folder> <output folder> --kit "My Kit" [--budget 196]
                     [--template some_kit.skt] [--curve 1.0] [--vel-level 0]
"""
import argparse, json, os, sys, re
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import strikefmt as SF
from analyse import load_articulation, dedupe, write_wav16, read_schedule, load_scheduled, guess_role
from plan import Artic, LADDER, WEIGHT, fit_budget, velocity_ranges, expand_compressed

MiB = 1024 * 1024


WIN_RESERVED = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}


def safe(s, n=26, fallback='Untitled'):
    """A file / folder name the module and Windows accept: plain characters only, no leading or trailing
    dots or spaces (so never '.' or '..', which would write outside the kit's folders), not a reserved
    Windows device name, at most n characters."""
    s = re.sub(r'\s+', ' ', re.sub(r'[^A-Za-z0-9 ._()-]', ' ', str(s))).strip(' .')
    s = s[:n].rstrip(' .')
    if not s:
        s = fallback[:n]
    base, dot, rest = s.partition('.')
    if base.strip().upper() in WIN_RESERVED:
        s = (base.strip() + '_' + dot + rest)[:n]
    return s


def find_articulations(root):
    out = []
    for dp, dn, fn in os.walk(root):
        if any(f.lower().endswith('.wav') for f in fn):
            rel = os.path.relpath(dp, root)
            parts = rel.split(os.sep)
            out.append((dp, parts[-1], parts[0] if len(parts) > 1 else ''))
    return sorted(out)


def short_code(name):
    return name.split()[-1] if ' ' in name else name


def default_pad_map(artics, splash_on_tom1_rim=True):
    """Assign articulations to Strike pads. Returns {pad: [artic, ...]}."""
    by = {}
    for a in artics:
        by.setdefault(a.role, []).append(a)
    pads = {}
    code = lambda a: short_code(a.name).lower()
    kicks = by.get('kick', [])
    if kicks: pads['K1H'] = kicks[0]
    sn = [a for a in by.get('snare', [])]
    if sn: pads['S1H'] = sn[0]
    rims = by.get('rim', [])
    snrim = [a for a in rims if code(a).startswith('sn')]
    if snrim: pads['S1R'] = snrim[0]
    toms = sorted(by.get('tom', []), key=lambda a: int(re.sub(r'\D', '', code(a)) or 0))
    for i, t in enumerate(toms[:4]):
        pads[f'T{i + 1}H'] = t
    crashes = by.get('crash', [])
    bows = [a for a in crashes if not code(a).endswith('e')]
    edges = {code(a)[:-1]: a for a in crashes if code(a).endswith('e')}
    splash = [a for a in bows if code(a).startswith('sp')]
    others = [a for a in bows if not code(a).startswith('sp')]
    for i, c in enumerate(others[:3]):
        pads[f'C{i + 1}B'] = c
        pads[f'C{i + 1}E'] = edges.get(code(c), c)
    if splash and splash_on_tom1_rim:
        pads['T1R'] = edges.get(code(splash[0]), splash[0])
    rides = by.get('ride', [])
    for r in rides:
        c = code(r)
        if c.endswith('b'): pads['R1D'] = r       # bell
        elif c.endswith('e'): pads['R1E'] = r     # edge
        else: pads['R1B'] = r                     # bow
    return pads


def read_kitmap(path):
    """kitmap.csv: note,name,role,pad,use,notes  (pad may hold several ids, e.g. 'C1B C1E')"""
    import csv
    if not os.path.exists(path):
        return {}
    out = {}
    with open(path, newline='', encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            try:
                out[int(r['note'])] = {k: (v or '').strip() for k, v in r.items()}
            except (KeyError, ValueError):
                pass
    return out


def write_kitmap(path, rows):
    import csv
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['note', 'name', 'role', 'pad', 'use', 'notes'])
        for r in rows:
            w.writerow(r)


HAT_RE = re.compile(r'^h([be])(c|t|o(\d))$', re.I)


def hat_openness(a):
    m = HAT_RE.match(short_code(a.name))
    if not m:
        n = a.name.lower()
        surf = 'e' if 'edge' in n else 'b'
        if 'tight' in n:
            return surf, -1
        mo = re.search(r'open\s*(\d+)', n)
        if mo:
            return surf, int(mo.group(1)) + 1
        if 'open' in n:
            return surf, 9
        return surf, 0
    surf = m.group(1).lower()
    if m.group(2).lower() in ('c', 't'):
        return surf, -1 if m.group(2).lower() == 't' else 0
    return surf, int(m.group(3))


TYPE_SUB = {'kick': 'KICK', 'snare': 'SNARE', 'rim': 'SNARE', 'tom': 'TOM', 'hihat': 'HIHAT', 'pedal': 'HIHAT',
            'crash': 'CRASH', 'ride': 'RIDE', 'other': 'PERC'}
TYPE_FOLDER = {'kick': 'KICKS', 'snare': 'SNARES', 'rim': 'SNARES', 'tom': 'TOMS', 'hihat': 'HIHATS',
               'pedal': 'HIHATS', 'crash': 'CRASHES', 'ride': 'RIDES', 'other': 'PERC'}

# pad zones that copy their partner when nothing is assigned to them ('Fill empty pad zones')
FILL_FROM = [('C1B', 'C1E'), ('C1E', 'C1B'), ('C2B', 'C2E'), ('C2E', 'C2B'), ('C3B', 'C3E'), ('C3E', 'C3B'),
             ('R1B', 'R1E'), ('R1E', 'R1B'), ('R1D', 'R1B'), ('H1E', 'H1B'), ('H1B', 'H1E'), ('K2H', 'K1H'),
             ('S1R', 'S1H'), ('T1R', 'T1H'), ('T2R', 'T2H'), ('T3R', 'T3H'), ('T4R', 'T4H')]
PAD_LABEL = {'C1B': 'crash 1 bow', 'C1E': 'crash 1 edge', 'C2B': 'crash 2 bow', 'C2E': 'crash 2 edge',
             'C3B': 'crash 3 bow', 'C3E': 'crash 3 edge', 'R1B': 'ride bow', 'R1E': 'ride edge', 'R1D': 'ride bell',
             'H1E': 'hi-hat edge', 'H1B': 'hi-hat bow', 'K2H': 'kick 2', 'S1R': 'snare rim', 'T1R': 'tom 1 rim',
             'T2R': 'tom 2 rim', 'T3R': 'tom 3 rim', 'T4R': 'tom 4 rim'}


def fit_name(base, suffix):
    try:
        from sd3names import fit
        return fit(base, suffix)
    except Exception:
        return f'{suffix}_{base}'


SPLASH_START = 7          # factory pedal instruments: splash zones from pedal 7, splash byte 127 - 7 = 120


def factory_open_ranges(n):
    """Pedal (CC4) ranges for n open positions, least open first, closed = 127 only, using the boundaries
    almost all factory acoustic hats share (…/67–90/91–126/127)."""
    if n <= 0:
        return []
    if n == 1:
        return [(0, 126)]
    if n == 2:
        return [(91, 126), (0, 90)]
    if n == 3:
        return [(91, 126), (67, 90), (0, 66)]
    if n == 4:
        return [(91, 126), (67, 90), (37, 66), (0, 36)]
    k = n - 2                                   # split 0–66 evenly for the most open ones
    low = []
    for j in range(k):
        lo = round(j * 67 / k); hi = round((j + 1) * 67 / k) - 1
        low.append((lo, hi))
    return [(91, 126), (67, 90)] + low[::-1]


def build_instruments(artics, pads, closed_from=118):
    """One instrument per articulation, except hi-hats: all openness levels of a surface
    go into one hi-hat instrument with CC4 pedal ranges, chick + splash into a pedal instrument."""
    insts, done = [], set()
    hats = [a for a in artics if a.role == 'hihat' and not getattr(a, 'solo', False)]
    by_surface = {}
    for a in hats:
        surf, o = hat_openness(a)
        by_surface.setdefault(surf, []).append((o, a))
    for surf, lst in sorted(by_surface.items()):
        lst.sort(key=lambda t: t[0])                 # tight/closed first, then more and more open
        closed = [a for o, a in lst if o <= 0]
        opens = [a for o, a in lst if o > 0]
        parts = []
        # closed (and tight) share the top of the pedal range
        if closed:
            for a in closed[:1]:
                parts.append((a, closed_from, 127, 0))
        top = closed_from - 1 if closed else 127
        n = len(opens)
        fac = factory_open_ranges(n) if closed and closed_from == 127 else None
        for i, a in enumerate(opens):                # least open sits next to closed
            if fac:
                lo, hi = fac[i]
            else:
                hi = top - round(i * (top + 1) / n)
                lo = 0 if i == n - 1 else top - round((i + 1) * (top + 1) / n) + 1
            parts.append((a, lo, hi, 0))
        n0 = lst[0][1].name
        if HAT_RE.match(short_code(n0)):
            base = n0.rsplit(' ', 1)[0].split('_')[0]
        else:
            base = re.sub(r'\b(bow|edge|closed|tight|open\s*\d*|\d+)\b', '', n0, flags=re.I)
            base = re.sub(r'\s+', ' ', base).strip() or 'Hi-Hat'
        name = f"{base} {'Bow' if surf == 'b' else 'Edge'}"
        lib_base = next((a.base for _, a in lst if getattr(a, 'base', None)), None)
        if lib_base:                                  # drum name from the plugin's library: 14'Agop Trad Jazz_BOW
            name = fit_name(lib_base, 'HHBOW' if surf == 'b' else 'HHEDG')
        insts.append({'name': name, 'category': SF.CAT_HIHAT, 'parts': parts,
                      'pads': ['H1B'] if surf == 'b' else ['H1E']})
        done.update(id(a) for _, a in lst)
    if 'e' not in by_surface and insts:
        insts[0]['pads'].append('H1E')          # only a bow: it plays on the edge zone too
    if 'b' not in by_surface and insts:
        insts[0]['pads'].append('H1B')          # only an edge: it plays on the bow zone too
    pedals = [a for a in artics if a.role == 'pedal' and not getattr(a, 'solo', False)]
    if pedals:
        parts = []
        for a in pedals:
            if short_code(a.name).lower() == 'hsp' or 'splash' in a.name.lower():
                parts.append((a, SPLASH_START, 127, 127 - SPLASH_START))
            else:
                parts.append((a, 0, 127, 0))
        n0 = pedals[0].name
        base = n0.rsplit(' ', 1)[0].split('_')[0] if ' ' in n0 else n0
        base = re.sub(r'\b(pedal|chick|foot|splash|closed)\b', '', base, flags=re.I).strip() or 'Hi-Hat'
        lib_base = next((a.base for a in pedals if getattr(a, 'base', None)), None)
        insts.append({'name': fit_name(lib_base, 'HHPED') if lib_base else f'{base} Pedal', 'category': SF.CAT_HIHAT, 'parts': parts, 'pads': ['H1F']})
        done.update(id(a) for a in pedals)
    for a in artics:
        if id(a) not in done:
            insts.append({'name': a.name, 'category': SF.CAT_NORMAL, 'parts': [(a, 0, 127, 0)]})
    return insts


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('renders'); ap.add_argument('out')
    ap.add_argument('--kit', default='Smart Kit')
    ap.add_argument('--budget', type=float, default=196.0, help='MiB of sample memory to use (pool is 200)')
    ap.add_argument('--template', help='existing .skt to copy kit settings/pad order from')
    ap.add_argument('--curve', type=float, default=1.0, help='velocity curve (1 = even dB steps)')
    ap.add_argument('--vel-level', type=int, default=0, help='instrument VEL>LEVEL (0 = dynamics from samples only)')
    ap.add_argument('--hat-closed-from', type=int, default=118, help='hi-hat pedal value (CC4) from which the hat counts as closed')
    ap.add_argument('--gain', choices=['unity', 'normalise'], default='unity',
                    help="zone gain field: 'unity' keeps the recorded levels, 'normalise' writes what the Strike Editor writes")
    ap.add_argument('--include-all', action='store_true', help='also convert articulations not placed on a pad')
    args = ap.parse_args(argv)

    print(f'Reading renders from {args.renders} ...')
    artics = []
    schedule = read_schedule(args.renders)
    pad_override = {}
    if schedule:
        # ---- output of "SmartKit Render.lua": one WAV per MIDI note + _notes.csv + (optional) kitmap.csv
        kmap = read_kitmap(os.path.join(args.renders, 'kitmap.csv'))
        rows_out = []
        for row in schedule:
            hits = load_scheduled(args.renders, row)
            if not hits:
                continue
            role, cen, ring = guess_role(hits)
            m = kmap.get(row['note'], {})
            if m.get('use', 'y').lower().startswith('n'):
                continue
            name = m.get('name') or f"N{row['note']:03d}"
            n0 = len(hits); hits = dedupe(hits)
            a = Artic(name, '', hits)
            if m.get('role'):
                a.role = m['role'].lower(); a.weight = WEIGHT.get(a.role, 0.4)
            elif a.role == 'other':
                a.role = role; a.weight = WEIGHT.get(role, 0.4)
            a.n_raw = n0; a.src_bytes = os.path.getsize(os.path.join(args.renders, row['file']))
            artics.append(a)
            if m.get('pad'):
                for pid in m['pad'].replace('+', ' ').split():
                    pad_override[pid.upper()] = a
            rows_out.append((row['note'], name, a.role, m.get('pad', ''), 'y', f'{cen:.0f} Hz, rings {ring:.1f} s'))
            print(f'  N{row["note"]:03d} {name:32s} {a.role:6s} {n0:3d} hits -> {len(hits):3d} distinct')
        if not kmap:
            write_kitmap(os.path.join(args.renders, 'kitmap.csv'), rows_out)
            print('\nWrote kitmap.csv next to the renders: name the notes / fix roles / set pads there and run again.')
    else:
        # ---- folders of single-hit WAVs (e.g. SDSE renders)
        for folder, name, piece in find_articulations(args.renders):
            hits = load_articulation(folder)
            n0 = len(hits)
            hits = dedupe(hits)
            if not hits:
                continue
            a = Artic(name, piece, hits)
            a.n_raw = n0
            a.src_bytes = sum(os.path.getsize(os.path.join(folder, f)) for f in os.listdir(folder) if f.lower().endswith('.wav'))
            artics.append(a)
            print(f'  {name:40s} {a.role:6s} {n0:3d} renders -> {len(hits):3d} distinct  ch={a.channels}')

    return build_kit(artics, pad_override, args)


def build_kit(artics, pad_override, args, log=print):
    """Choose layers/RR/tails within the memory budget and write Kits/Instruments/Samples.
    args needs: out, kit, budget, template, curve, vel_level, hat_closed_from, gain, include_all."""
    kit = safe(args.kit, 26)
    pads = default_pad_map(artics) if getattr(args, 'auto_pads', True) else {}
    pads.update(pad_override)
    pads_b = getattr(args, 'pads_b', None) or {}
    for a in artics:
        if a.role not in ('hihat', 'pedal') and all(p is not a for p in list(pads.values()) + list(pads_b.values())):
            log(f'  note: "{a.name}" is not on any pad, so it is left out')
    used_artics = list({id(a): a for a in list(pads.values()) + list(pads_b.values())}.values())
    used_artics += [a for a in artics if a.role in ('hihat', 'pedal') and a not in used_artics]
    if args.include_all or getattr(args, 'no_pads', False):
        used_artics = list(artics)

    # group into instruments first: a Strike instrument holds at most 255 zones, so the
    # articulations sharing one (hi-hat openness levels) share that limit
    instruments = build_instruments(used_artics, pads, args.hat_closed_from)
    for inst in instruments:
        for a, *_ in inst['parts']:
            a.max_zones = min(getattr(a, 'max_zones', 255), 255 // len(inst['parts']))

    # compressed sounds (loudness flat at the hard hits): more layers there, loudness steps restored
    comp_db = float(getattr(args, 'comp_db', 0) or 0)
    for a in list(used_artics) + [x for x in (getattr(args, 'extras', None) or []) if x not in used_artics]:
        knee = expand_compressed(a, comp_db, restore=getattr(args, 'comp_restore', True))
        if knee is not None:
            log(f'  {a.name}: compressed - the loudness hardly rises above velocity {knee}; '
                f'more velocity layers there' + (f', hard hits {comp_db:g} dB louder than v{knee}'
                                                   if getattr(args, 'comp_restore', True) else ''))

    budget = int(args.budget * MiB)
    used, ok = fit_budget(used_artics, budget)
    if not ok:
        log(f'WARNING: even the smallest settings need {used / MiB:.1f} MiB (> {args.budget} MiB). Drop some articulations.')

    # 'instrument only' sounds: written as user instruments but not put in the kit. Each one gets about the
    # memory the kit gives the same kind of drum (so it can be swapped in later), or extra_mb if set.
    extras = [a for a in (getattr(args, 'extras', None) or []) if all(a is not b for b in used_artics)]
    for a in extras:
        a.max_zones = 255
        same = [b.cost(b.level) for b in used_artics if b.role == a.role] or [b.cost(b.level) for b in used_artics]
        cap = getattr(args, 'extra_mb', 0) * MiB or (max(same) if same else 8 * MiB)
        _, fits = fit_budget([a], int(cap))
        if not fits:
            a.level = 0
    instruments += [{'name': a.name, 'category': SF.CAT_NORMAL, 'parts': [(a, 0, 127, 0)], 'extra': True} for a in extras]

    # one gain for the whole kit (keeps the balance between drums, avoids clipping)
    peak = max(max(h.peak for h in a.hits) for a in used_artics + extras) if used_artics + extras else 1.0
    target = float(getattr(args, 'kit_peak', 0.891))
    kit_gain = target / peak
    mode = getattr(args, 'levels', 'kit')
    per_inst = mode in ('instrument', 'mix')
    if mode == 'mix':
        log('Levels: every instrument at full level (-1 dBFS); the kit pads are turned down to keep the '
            'plugin\'s mix (loudest instrument at Level 90, Strike Level curve measured on the module)')
    elif per_inst:
        log('Levels: every instrument is raised until its loudest hit is at -1 dBFS (balance the drums with the '
            'pad levels on the module)')
    else:
        log(f'Kit gain {20 * np.log10(kit_gain):+.1f} dB (loudest hit to {20 * np.log10(target):.1f} dBFS)')
    layer_by_role = getattr(args, 'layer_by_role', None) or {}

    def role_of(inst):
        rs = [a.role for a, *_ in inst['parts']]
        return 'hihat' if 'hihat' in rs else (rs[0] if rs else 'other')


    # ---------------------------------------------------------------- write
    lib = kit                                       # Samples/<kit>/<instrument>/…
    folders = getattr(args, 'folders', 'kit')       # Instruments/<folder>/<instrument>.sin

    def folder_of(inst):
        if folders == 'kit':
            return kit
        if folders == 'nested':                          # Instruments/<kit>/CRASH/<instrument>.sin
            m = re.match(r'(SPL|CHN|STK|SP\d|CN\d|ST\d)[A-Z0-9]{2}\d*_', inst['name'])
            t = {'SP': 'SPLASH', 'CH': 'CHINA', 'CN': 'CHINA', 'ST': 'STACK'}[m.group(1)[:2]] if m else \
                TYPE_SUB.get(role_of(inst), 'PERC')
            return f'{kit}/{t}'
        r = role_of(inst)
        t = TYPE_FOLDER.get(r, 'PERC')
        if r == 'crash' and re.match(r'(SPL|CHN|STK|SP\d|CN\d|ST\d)[A-Z0-9]{2}\d*_', inst['name']):
            t = 'SPLASH CHINAS'
        if folders == 'shared':
            return f'all {t}'
        return f'{kit[:26 - len(t) - 1].rstrip()} {t}'
    report = []
    inst_path = {}
    names_used = set()
    for inst in instruments:
        iname = safe(inst['name'], 26)
        k = 2
        while iname.lower() in names_used:                    # never let two instruments share files
            if re.match(r'[A-Z0-9]{2,6}_', inst['name']):     # TOMHD_8x12 Lud Hwood Maple -> TOMHD2_8x12 …
                sfx, base = inst['name'].split('_', 1)
                iname = safe(fit_name(base, f'{sfx[:5]}{k}'), 26)
            else:
                iname = safe(inst['name'], 23) + f' {k}'
            k += 1
        names_used.add(iname.lower())
        zones, paths, parts = [], [], []
        g_inst = target / max(max(h.peak for h in a.hits) for a, *_ in inst['parts']) if per_inst else kit_gain
        inst['gain_db'] = 20 * np.log10(g_inst)
        inst['mix_db'] = 20 * np.log10(kit_gain / g_inst)          # pad gain that brings back the kit balance
        for a, plo, phi, splash in inst['parts']:
            layers = a.render(a.level)
            ranges = velocity_ranges([[h for _, h in g] for g in layers], args.curve,
                                    by_vel=getattr(a, 'knee', None) is not None)
            for (vlo, vhi), grp in zip(ranges, layers):
                for k, (audio, h) in enumerate(grp):
                    # <instrument> [p<pedal start>] v<top velocity> r<round robin>.wav; hi-hat samples carry their
                    # own articulation code: HHBO1_14 Agop Trad Jazz p067 v100 r1.wav
                    pos = f' p{plo:03d}' if inst['category'] == SF.CAT_HIHAT else ''
                    spl = 's' if splash else ''
                    sname = iname
                    code = getattr(a, 'code', None)
                    if code and inst['category'] == SF.CAT_HIHAT and '_' in iname:
                        sname = safe(fit_name(iname.split('_', 1)[1], code), 26)
                    fname = f'{sname}{pos}{spl} v{vhi:03d} r{k + 1}.wav'
                    rel = f'{lib}/{iname}/{fname}'
                    audio = audio * g_inst
                    write_wav16(os.path.join(args.out, 'Samples', lib, iname, fname), audio, h.sr)
                    paths.append(':' + rel)
                    gain = 64 if args.gain == 'unity' else round(64 * 32767 / max(1, np.abs(audio).max() * 32767))
                    zones.append(SF.make_zone(len(paths) - 1, vlo, vhi, first_of_group=(k == 0), gain=gain,
                                              pedal_lo=plo, pedal_hi=phi, splash=splash))
            nl, nr, tdb = LADDER[a.level]
            parts.append({'articulation': a.name, 'role': a.role, 'renders': a.n_raw, 'distinct': len(a.hits),
                          'layers': len(layers), 'rr_max': max(len(g) for g in layers), 'tail_db': tdb,
                          'channels': a.channels, 'pedal': [plo, phi], 'splash': splash,
                          'ram_mib': round(a.cost(a.level) / MiB, 2), 'source_mib': round(a.src_bytes / MiB, 2),
                          'velocity_ranges': ranges})
        lk = dict(level=90, decay=98, vel_level=args.vel_level)
        lk.update(layer_by_role.get(role_of(inst), {}))
        inst['role'] = role_of(inst)
        defaults = SF.layer_bytes(index=0, **lk)
        sin = SF.write_sin(zones, paths, category=inst['category'], defaults=defaults)
        ifold = folder_of(inst)
        p = os.path.join(args.out, 'Instruments', ifold, iname + '.sin')
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, 'wb').write(sin)
        for a, *_ in inst['parts']:
            inst_path.setdefault(id(a), f':{ifold}/{iname}.sin')
        inst['path'] = f':{ifold}/{iname}.sin'
        inst['folder'] = ifold
        report.append({'folder': ifold, 'instrument': iname, 'zones': len(zones), 'parts': parts, 'in_kit': not inst.get('extra'),
                       'gain_db': round(inst['gain_db'], 1)})

    tpl_path = args.template or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'template.skt')
    if os.path.exists(tpl_path):
        tpl = open(tpl_path, 'rb').read()
        assign = {pid: inst_path[id(a)] for pid, a in pads.items() if id(a) in inst_path}
        for inst in instruments:
            for pid in inst.get('pads', []):
                assign[pid] = inst['path']
        assign_b = {pid: inst_path[id(a)] for pid, a in pads_b.items() if id(a) in inst_path}
        role_by_path = {inst['path']: inst.get('role', 'other') for inst in instruments if 'path' in inst}
        if getattr(args, 'no_pads', False):                  # 'instruments only': the kit gets no pads,
            assign, assign_b = {}, {}                        # the instruments are assigned on the module
            log('Instruments only: no pads assigned in the kit – choose the instruments on the module.')
        if getattr(args, 'fill_empty', False):              # a pad zone with nothing on it plays its partner
            for pid, partner in FILL_FROM:
                if pid not in assign and partner in assign:
                    assign[pid] = assign[partner]
                    pn = getattr(args, 'pad_notes', None)
                    if pn is not None and partner in pn and pid not in pn:
                        pn[pid] = pn[partner]                    # and sends the same MIDI note
                    log(f'  {pid} {PAD_LABEL.get(pid, "")} was empty: plays {assign[partner].split("/")[-1][:-4]} '
                        f'(from {partner})')
        layer_kw, pad_patch = {}, {}
        mix_level = {}
        if mode == 'mix':
            import levelcal
            curve = getattr(args, 'level_curve', None)
            loud = max((i['mix_db'] for i in instruments if 'path' in i and not i.get('extra')), default=0.0)
            log('Pad levels (plugin mix):')
            for i in instruments:
                if 'path' not in i or i.get('extra'):
                    continue
                db = i['mix_db'] - loud                      # 0 for the loudest instrument
                top = getattr(args, 'mix_top_level', 90)     # the loudest instrument sits at Level 90
                lv = levelcal.level_for_db(curve, levelcal.db_for_level(curve, top) + db)
                mix_level[i['path']] = lv
                note = '  (lowest useful level – quieter than the plugin)' if db < levelcal.db_for_level(curve, 1) else ''
                log(f"  {i['path'].split('/')[-1][:-4]:<28} {db:+6.1f} dB  → Level {lv}{note}")
        for pid, path in assign.items():
            role = role_by_path.get(path, 'other')
            layer_kw[pid] = dict(layer_by_role.get(role, {}))
            if path in mix_level:
                layer_kw[pid]['level'] = mix_level[path]
            pp = dict((getattr(args, 'pad_settings', None) or {}).get(role, {}))
            note = (getattr(args, 'pad_notes', None) or {}).get(pid)
            if note is not None:
                pp[52] = note
            pad_patch[pid] = pp
        layer_kw_b = {}
        for pid, path in assign_b.items():               # layer B: its own type's settings and mix level
            layer_kw_b[pid] = dict(layer_by_role.get(role_by_path.get(path, 'other'), {}))
            if path in mix_level:
                layer_kw_b[pid]['level'] = mix_level[path]
            if pid not in pad_patch:                     # a pad with only layer B still gets its settings
                pp = dict((getattr(args, 'pad_settings', None) or {}).get(role_by_path.get(path, 'other'), {}))
                note = (getattr(args, 'pad_notes', None) or {}).get(pid)
                if note is not None:
                    pp[52] = note
                pad_patch[pid] = pp
        skt = SF.write_skt_from_template(tpl, assign, default_layer={'vel_level': args.vel_level}, assign_b=assign_b,
                                         layer_kw=layer_kw, layer_kw_b=layer_kw_b, pad_patch=pad_patch,
                                         header_patch=getattr(args, 'kit_fx', None))
        p = os.path.join(args.out, 'Kits', kit + '.skt')
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, 'wb').write(skt)

    summary = {'kit': kit, 'budget_mib': args.budget, 'used_mib': round(used / MiB, 2),
               'pads': {pid: a.name for pid, a in pads.items()},
               'pads_b': {pid: a.name for pid, a in pads_b.items()}, 'instruments': report,
               'extras': [r['instrument'] for r in report if not r['in_kit']]}
    os.makedirs(args.out, exist_ok=True)
    json.dump(summary, open(os.path.join(args.out, 'smartkit_report.json'), 'w'), indent=1)
    log(f'\nKit "{kit}": {used / MiB:.1f} MiB of {args.budget} MiB budget')
    if pads_b and not getattr(args, 'no_pads', False):
        log('Layer B: ' + ', '.join(f'{pid} {a.name}' for pid, a in sorted(pads_b.items())))
    for r in report:
        log(f"  {r['folder']}/{r['instrument']}  ({r['zones']} zones, gain {r['gain_db']:+.1f} dB)"
            + ('' if r['in_kit'] else '   [instrument only – not in the kit]'))
        for q in r['parts']:
            ped = f"  pedal {q['pedal'][0]}-{q['pedal'][1]}" if q['role'] in ('hihat', 'pedal') else ''
            log(f"     {q['articulation']:38s} {q['layers']:2d} layers x up to {q['rr_max']} RR  tail {q['tail_db']} dB  "
                  f"{'stereo' if q['channels'] == 2 else 'mono  '}  {q['ram_mib']:6.2f} MiB  (source {q['source_mib']:.1f} MiB){ped}")
    return summary


if __name__ == '__main__':
    main()
