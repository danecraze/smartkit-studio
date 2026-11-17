"""Sample sources other than a drum plugin: sample folders, sampler instruments (SFZ, Decent Sampler,
Hydrogen), Strike instruments (.sin) and long recordings cut into single hits.

Every source is turned into 'sounds' (one articulation of one drum each) that SmartKit shows on tab 2 next to
the plugin's sounds, with the same fields (type, 5-letter code, Strike name, pads).  A sound keeps its files in
row['src'] = {'kind': ..., 'items': [{'f': path or [paths], 'v': velocity or None, 'g': gain dB, 'lr': bool}],
'slice': bool}; load_hits() turns them into measured hits for the memory planner, like plugin recordings."""
import os, re, glob
import xml.etree.ElementTree as ET
import numpy as np
from analyse import read_wav, measure, split_hits
import sd3names

SR = 48000          # the Strike's sample rate (all factory samples are 48 kHz)
AUDIO_EXT = ('.wav', '.wave')

# ------------------------------------------------------------------ codes and GM notes
# 5-letter code -> (role, long name, GM note, SD3-style code so the pad suggestions and hi-hat slots work)
ROLE_OF_PREFIX = {'KCK': 'kick', 'SNR': 'snare', 'TOM': 'tom', 'CRS': 'crash', 'RID': 'ride', 'SPL': 'crash',
                  'CHN': 'crash', 'STK': 'crash', 'PRC': 'other'}
ART_LONG = {'HD': 'Center (head)', 'RI': 'Rimshot', 'RO': 'Rim only', 'XS': 'Cross-stick', 'FL': 'Flam',
            'RF': 'Ruffs', 'MC': 'Mid center', 'ED': 'Edge (crashed)', 'BW': 'Bow', 'BL': 'Bell', 'SH': 'Bow shank',
            'BT': 'Bell tip', 'MU': 'Muted', 'CH': 'Choke', 'HT': 'Hit', 'CB': 'Cowbell', 'OF': 'Off center',
            'LH': 'Left hand', 'OP': 'Open', 'TL': 'Tail', 'FX': 'FX'}
HAT_LONG = {'HHBCL': 'Bow closed', 'HHBTT': 'Bow tight', 'HHECL': 'Edge closed', 'HHETT': 'Edge tight',
            'HHEMN': 'Edge open min', 'HHLCL': 'Bell closed', 'HHPCL': 'Pedal chick', 'HHPSP': 'Pedal splash'}
HAT_SD3 = {'HHBCL': 'hatsTP', 'HHBTT': 'hatsTT', 'HHECL': 'hatsCL', 'HHETT': 'hatsCT', 'HHEMN': 'hatsLO',
           'HHPCL': 'hatsPL', 'HHPSP': 'hatsPLO'}
for _i in range(1, 7):
    HAT_LONG[f'HHBO{_i}'] = f'Bow open {_i}'; HAT_LONG[f'HHEO{_i}'] = f'Edge open {_i}'
    HAT_SD3[f'HHBO{_i}'] = f'hatsT{_i}'; HAT_SD3[f'HHEO{_i}'] = f'hatsO{_i}'
TOM_NOTES = [50, 48, 47, 45, 43, 41]     # GM: high tom … low floor tom


def describe(code, num=1):
    """5-letter code -> (role, long name, GM note, SD3-style code)."""
    if code.startswith('HH'):
        role = 'pedal' if code.startswith('HHP') else 'hihat'
        note = 44 if role == 'pedal' else (42 if code.endswith(('CL', 'TT')) else 46)
        return role, HAT_LONG.get(code, code), note, HAT_SD3.get(code, '')
    t, a = code[:3], code[3:5]
    role = ROLE_OF_PREFIX.get(t, 'other')
    if t == 'SNR':
        if a in ('RI', 'RO', 'XS'):
            role = 'rim'
        note = {'RI': 40, 'RO': 40, 'XS': 37}.get(a, 38)
        sd3 = {'HD': 'snareR', 'RI': 'snareFX', 'RO': 'snareRO', 'XS': 'snareSL'}.get(a, 'snare' + a)
    elif t == 'KCK':
        note, sd3 = 36, 'kickR'
    elif t == 'TOM':
        note = TOM_NOTES[(max(1, num) - 1) % len(TOM_NOTES)]
        sd3 = f'tom{num}' + ('R' if a == 'HD' else 'FX' if a == 'RI' else a)
    elif t == 'RID':
        note = {'BL': 53, 'ED': 59}.get(a, 51)
        sd3 = {'BL': 'ride1BL', 'ED': 'ride1PU'}.get(a, 'ride1')
    elif t == 'SPL':
        note, sd3 = 55, f'splash{num}'
    elif t == 'CHN':
        note, sd3 = 52, f'china{num}'
    elif t in ('CRS', 'STK'):
        note = {1: 49, 2: 57, 3: 52}.get(num, 49)
        sd3 = f'crash{num}' + {'BW': 'RT', 'BL': 'BL', 'SH': 'FR', 'CH': 'CS'}.get(a, '')
    else:
        note, sd3 = 56, ''
    return role, ART_LONG.get(a, a), note, sd3


# ------------------------------------------------------------------ converter file names
# Sample folders made by common drum converters name their files
#   '<drum name>_<mic mix> <CODE> <number>[v<velocity>].wav'   e.g. '14 SABIAN AAX Studio Hats_Z8 HEO4 28v30.wav'
# CODE: K kick · Sn snare · SnR rimshot · SnSS sidestick · T1..T9 toms (T1R rim) · HBC/HBT/HBO1-5 hat bow
# closed/tight/open · HEC/HET/HEO1-5 hat edge · HCH or HP pedal chick · HSP or HF foot splash · Ri1 ride bow ·
# Ri1B bell · Ri1E edge · C1E/Cr1E crash edge · C1/Cr1 crash bow · Ch1E china · Sp1E splash · P1 percussion.
# (Checked against Strike instruments built from them: HP = chick zones, HF = splash zones with the splash flag.)
CONV_RE = re.compile(r'^(?P<base>.*?)[ _]+(?P<code>K\d?|Sn|SnR|SnSS|SnRO|SnXS|XS|T\d{1,2}R?|H(?:BC|BT|EC|ET|CH|SP|P|F|BO\d|EO\d)'
                     r'|Ri\d*[BES]?|Cr?\d+[EB]?|Ch\d+[EB]?|Sp\d+[EB]?|St\d+[EB]?|P\d+)[ _]+(?P<idx>\d+)(?:v(?P<vel>\d{1,3}))?$')


def conv_code(c):
    """Converter code -> (5-letter code, number of the drum/cymbal)."""
    num = int(re.search(r'\d+', c).group()) if re.search(r'\d+', c) else 1
    if re.fullmatch(r'K\d?', c): return 'KCKHD', 1
    if c == 'Sn': return 'SNRHD', 1
    if c == 'SnR': return 'SNRRI', 1
    if c == 'SnRO': return 'SNRRO', 1
    if c in ('SnSS', 'SnXS', 'XS'): return 'SNRXS', 1
    m = re.fullmatch(r'T(\d+)(R?)', c)
    if m: return ('TOMRI' if m.group(2) else 'TOMHD'), int(m.group(1))
    hat = {'HBC': 'HHBCL', 'HBT': 'HHBTT', 'HEC': 'HHECL', 'HET': 'HHETT', 'HCH': 'HHPCL', 'HP': 'HHPCL',
           'HSP': 'HHPSP', 'HF': 'HHPSP'}
    if c in hat: return hat[c], 1
    m = re.fullmatch(r'H([BE])O(\d)', c)
    if m: return f'HH{m.group(1)}O{m.group(2)}', 1
    m = re.fullmatch(r'Ri\d*([BES]?)', c)
    if m: return 'RID' + {'B': 'BL', 'E': 'ED', 'S': 'SH', '': 'BW'}[m.group(1)], num
    m = re.fullmatch(r'(Cr?|Ch|Sp|St)\d+([EB]?)', c)
    if m:
        t = {'C': 'CRS', 'Cr': 'CRS', 'Ch': 'CHN', 'Sp': 'SPL', 'St': 'STK'}[m.group(1)]
        return t + {'E': 'ED', 'B': 'BL', '': 'BW'}[m.group(2)], num
    if re.fullmatch(r'P\d+', c): return 'PRCHT', num
    return None, 1


# ------------------------------------------------------------------ plain names (any sample pack)
WORDS = lambda s: [w for w in re.split(r'[^a-z0-9]+', re.sub(r'([a-z])([A-Z])', r'\1 \2', s).lower()) if w]
ROLE_WORDS = [('hihat', {'hh', 'hihat', 'hihats', 'hat', 'hats', 'hi', 'hhat'}), ('ride', {'ride', 'rd', 'ri'}),
              ('china', {'china', 'ch', 'chn'}), ('splash', {'splash', 'spl', 'sp'}), ('stack', {'stack', 'stk'}),
              ('crash', {'crash', 'cr', 'crsh', 'cym', 'cymbal'}), ('kick', {'kick', 'kik', 'kck', 'bd', 'bassdrum', 'bass'}),
              ('snare', {'snare', 'snr', 'sn', 'sd', 'snarer'}), ('tom', {'tom', 'toms', 'floor', 'ft', 'rack'}),
              ('other', {'cowbell', 'clap', 'tamb', 'tambourine', 'shaker', 'perc', 'conga', 'bongo', 'cajon', 'block',
                         'clave', 'triangle', 'rimclick', 'stick'})]


def guess_from_words(words):
    """Words of a path -> 5-letter code (or None)."""
    ws = set(words)
    if any(w.startswith('hihat') or w.startswith('hihats') for w in ws):
        ws.add('hihat')
    role = next((r for r, keys in ROLE_WORDS if ws & keys), None)
    if role is None and any(w.startswith(('zild', 'sabian', 'sbn', 'paiste', 'pst', 'meinl', 'istanbul', 'agop', 'ufip', 'bosph'))
                            for w in ws):
        role = 'crash'                       # a cymbal maker but no type: most likely a crash
    if role is None:
        return None
    if role == 'hihat':
        num = next((int(w[-1]) for w in words if re.fullmatch(r'(open|op|o)[1-6]', w)), None)
        if ws & {'pedal', 'foot', 'ped', 'chick', 'fc', 'stomp'}:
            return 'HHPSP' if ws & {'splash', 'spl', 'open', 'sp'} else 'HHPCL'
        surf = 'E' if ws & {'edge', 'e', 'shank'} else 'B'
        if ws & {'tight', 'tt'}: return f'HH{surf}TT'
        if ws & {'closed', 'clsd', 'cl', 'close', 'shut', 'c'}: return f'HH{surf}CL'
        if ws & {'half', 'semi', 'loose', 'lse'}: return f'HH{surf}O2'
        if num or ws & {'open', 'op', 'opn', 'o'}:
            return f'HH{surf}O{num or 3}'
        return f'HH{surf}CL'
    if role == 'snare':
        if ws & {'side', 'sidestick', 'xs', 'xstick', 'cross', 'crossstick', 'cs', 'ss', 'stick'}: return 'SNRXS'
        if ws & {'rimonly', 'ro'} or ('rim' in ws and 'only' in ws): return 'SNRRO'
        if ws & {'rim', 'rimshot', 'rs', 'r'}: return 'SNRRI'
        if ws & {'flam'}: return 'SNRFL'
        if ws & {'roll', 'ruff', 'ruffs'}: return 'SNRRF'
        if ws & {'off', 'offcenter', 'edge'}: return 'SNROF'
        return 'SNRHD'
    if role == 'tom':
        return 'TOMRI' if ws & {'rim', 'rimshot', 'rs'} else 'TOMHD'
    if role == 'kick':
        return 'KCKHD'
    if role in ('crash', 'china', 'splash', 'stack'):
        t = {'crash': 'CRS', 'china': 'CHN', 'splash': 'SPL', 'stack': 'STK'}[role]
        if ws & {'choke', 'chk', 'grab'}: return t + 'CH'
        if ws & {'bell', 'cup'}: return t + 'BL'
        if ws & {'bow', 'tip', 'ride'}: return t + 'BW'
        return t + 'ED'
    if role == 'ride':
        if ws & {'bell', 'cup', 'b', 'bl'}: return 'RIDBL'
        if ws & {'edge', 'crash', 'e', 'shank'}: return 'RIDED'
        return 'RIDBW'
    return 'PRCCB' if 'cowbell' in ws else 'PRCHT'


GM_CODE = {35: 'KCKHD', 36: 'KCKHD', 37: 'SNRXS', 38: 'SNRHD', 40: 'SNRRI', 39: 'PRCHT', 41: 'TOMHD', 43: 'TOMHD',
           45: 'TOMHD', 47: 'TOMHD', 48: 'TOMHD', 50: 'TOMHD', 42: 'HHBCL', 44: 'HHPCL', 46: 'HHBO3', 49: 'CRSED',
           57: 'CRSED', 52: 'CHNED', 55: 'SPLED', 51: 'RIDBW', 59: 'RIDBW', 53: 'RIDBL', 56: 'PRCCB'}
GM_NUM = {41: 4, 43: 3, 45: 2, 47: 2, 48: 1, 50: 1, 49: 1, 57: 2, 52: 1, 55: 1, 51: 1, 59: 2, 53: 1}


# ------------------------------------------------------------------ sounds
def make_sound(group, base, code, num, items, kind, label='', slice_=False, origin=''):
    role, long, note, sd3 = describe(code, num)
    return {'group': group, 'base': sd3names.clean(base) or 'Sound', 'sfx': code, 'role': role, 'num': num,
            'long': long + (f' {num}' if code.startswith(('TOM', 'CRS')) and num > 1 else ''),
            'note': note, 'code': sd3, 'label': label,
            'src': {'kind': kind, 'items': items, 'slice': slice_, 'origin': origin}}


def _short_base(base):
    """'14 SABIAN AAX Studio Hats_Z8' -> '14 SABIAN AAX Studio Hats' (the _Z8 is the converter's mic-mix id)."""
    return re.sub(r'_[A-Za-z0-9]{2,3}$', '', base).strip()


TAIL_WORDS = {'choke', 'chk', 'open', 'closed', 'rim', 'rimshot', 'edge', 'bell', 'bow', 'tip', 'xs', 'sidestick',
              'foot', 'pedal', 'splash', 'off', 'ring', 'mute', 'muted', 'flam', 'l', 'r'}


def _strip_numbering(stem):
    """'Sn 1 BB 3.2' -> ('Sn 1 BB', ['3', '2']); 'Toms Custom 1-1.1' -> ('Toms Custom', ['1', '1', '1']);
    'PCS_SnareAO_01L' -> ('PCS_SnareAO', ['01'], 'L'); 'HH_Zild14K_open_3b' -> ('HH_Zild14K_open', ['3'], 'b')."""
    side = ''
    m = re.match(r'^(.*?\d)([LR])$', stem)
    if m:
        stem, side = m.group(1), m.group(2)
    rr = ''
    m = re.match(r'^(.*?\d)([a-d])$', stem)
    if m:
        stem, rr = m.group(1), m.group(2)
    m = re.match(r'^(.*?)[\s_\-]*((?:\d+[.\-_ ])*\d+)[\s_\-]+([A-Za-z]+)$', stem)   # 'ZildAThin18_06_choke'
    if m and m.group(3).lower() in TAIL_WORDS:
        return (m.group(1).strip(' _-') + ' ' + m.group(3)).strip(), re.split(r'[.\-_ ]', m.group(2)), side, rr
    m = re.match(r'^(.*?)[\s_\-]*((?:\d+[.\-_ ])*\d+)$', stem)
    if not m:
        return stem, [], side, rr
    return m.group(1).strip(' _-'), re.split(r'[.\-_ ]', m.group(2)), side, rr


def scan_folder(root, log=print):
    """Every WAV under root -> sounds. Converter names are read exactly; other names by
    their words. Velocity from 'v<number>' at the end of a name, otherwise from loudness at build time."""
    files = []
    for dp, dn, fn in os.walk(root):
        dn.sort()
        for f in sorted(fn):
            if f.lower().endswith(AUDIO_EXT):
                files.append(os.path.join(dp, f))
    sounds, generic = {}, {}
    for p in files:
        rel = os.path.relpath(p, root)
        folder = os.path.dirname(rel)
        stem = os.path.splitext(os.path.basename(p))[0]
        m = CONV_RE.match(stem)
        if m:
            code, num = conv_code(m.group('code'))
            if code:
                base = _short_base(m.group('base'))
                key = (folder, base, code, num)
                s = sounds.get(key)
                if not s:
                    top = folder.split(os.sep)[0] if folder else ''
                    grp = (top + ' / ' if top and not top.startswith(base) else '') + m.group('base')
                    s = sounds[key] = make_sound(grp, base, code, num, [], 'folder', label=m.group('code'), origin=root)
                v = m.group('vel')
                s['src']['items'].append({'f': p, 'v': int(v) if v else None, 'n': int(m.group('idx'))})
                continue
        generic.setdefault(folder, []).append((p, stem))
    # plain names: group by name without its numbering; 3 numbers (1-2.1) = drum, layer, take
    for folder, lst in generic.items():
        parsed = [(p, *_strip_numbering(stem)) for p, stem in lst]
        nums_n = max((len(x[2]) for x in parsed), default=0)
        varying = [i for i in range(nums_n) if len({x[2][i] for x in parsed if len(x[2]) > i}) > 1]
        fwords = WORDS(folder)
        is_toms = 'toms' in fwords or ('tom' in fwords and 'set' in fwords)
        for p, name, nums, side, rr in parsed:
            drum = ''
            if len(varying) >= 3 or (is_toms and varying and (len(varying) >= 2 or len(lst) <= 6)):
                drum = nums[varying[0]] if len(nums) > varying[0] else ''
            code = guess_from_words(WORDS(name) + fwords) or 'PRCHT'
            num = int(drum) if drum.isdigit() else 1
            mm = re.search(r'(?<=[a-z])([A-F])$', name)          # TomA, TomB … = drum 1, 2 …
            if mm and not drum and code.startswith('TOM'):
                num = ord(mm.group(1)) - 64
            base = (name.strip() + (f' {drum}' if drum else '')).strip()
            if code.startswith('TOM') and drum:
                base = re.sub(r'\bToms\b', 'Tom', base)
            key = (folder, base, code, num)
            s = sounds.get(key)
            if not s:
                grp = (folder.replace(os.sep, ' / ') if folder else os.path.basename(root)) + (f' / {base}' if base else '')
                s = sounds[key] = make_sound(grp, base or os.path.basename(folder) or 'Sound', code, num, [], 'folder', origin=root)
                s['label'] = os.path.basename(folder) or name
            it = next((i for i in s['src']['items'] if side and i.get('stem') == (name, tuple(nums), rr)), None)
            if side and it:                         # second half of a left/right pair -> one stereo hit
                it['f'] = [it['f'], p] if side == 'R' else [p, it['f']]
                it['lr'] = True
            else:
                s['src']['items'].append({'f': p, 'v': None, 'stem': (name, tuple(nums), rr) if side else None})
    out = list(sounds.values())
    for s in out:
        for it in s['src']['items']:
            it.pop('stem', None)
    log(f'{root}: {len(files)} files -> {len(out)} sounds')
    return out


# ------------------------------------------------------------------ sampler instruments
def _gm_sound(group, base, note, items, kind, origin, words=()):
    code = guess_from_words(list(words)) or GM_CODE.get(note, 'PRCHT')
    return make_sound(group, base, code, GM_NUM.get(note, 1), items, kind, label=f'note {note}', origin=origin)


def _note_num(s):
    """'36' or 'c1' / 'C#2' -> MIDI note (SFZ: c4 = 60)."""
    s = str(s).strip().lower()
    if s.lstrip('-').isdigit():
        return int(s)
    m = re.fullmatch(r'([a-g])(#|b)?(-?\d)', s)
    if not m:
        return None
    n = {'c': 0, 'd': 2, 'e': 4, 'f': 5, 'g': 7, 'a': 9, 'b': 11}[m.group(1)] + {'#': 1, 'b': -1, None: 0}[m.group(2)]
    return n + (int(m.group(3)) + 1) * 12


def scan_sfz(path, log=print):
    """SFZ: one sound per key. Regions with the same key, velocity range and round-robin position but different
    samples (close / overhead / room mics) are mixed into one hit, as the sampler would play them."""
    txt = open(path, encoding='utf-8', errors='replace').read()
    txt = re.sub(r'//[^\n]*', '', txt)
    defines = dict(re.findall(r'#define\s+(\$\w+)\s+(\S+)', txt))
    for k, v in sorted(defines.items(), key=lambda kv: -len(kv[0])):
        txt = txt.replace(k, v)
    base_dir = os.path.dirname(path)
    default_path, levels, regions = '', {'global': {}, 'master': {}, 'group': {}}, []
    for hdr, body in re.findall(r'<(\w+)>([^<]*)', txt):
        ops = dict(re.findall(r'(\w+)=(.+?)(?=\s+\w+=|\s*$)', body.strip(), re.S))
        ops = {k: v.strip() for k, v in ops.items()}
        if hdr == 'control':
            default_path = ops.get('default_path', default_path)
        elif hdr in levels:
            levels[hdr] = ops
            if hdr == 'global': levels['master'] = {}; levels['group'] = {}
            if hdr == 'master': levels['group'] = {}
        elif hdr == 'region':
            r = {}
            for lv in ('global', 'master', 'group'):
                r.update(levels[lv])
            r.update(ops)
            regions.append(r)
    by = {}
    for r in regions:
        smp = r.get('sample')
        if not smp: continue
        f = os.path.normpath(os.path.join(base_dir, default_path.replace('\\', '/'), smp.replace('\\', '/')))
        key = _note_num(r.get('key', r.get('lokey', r.get('pitch_keycenter', '60'))))
        if key is None: continue
        hv = int(r.get('hivel', 127)); lv = int(r.get('lovel', 1))
        seq = r.get('seq_position', '1')
        g = float(r.get('volume', 0)) + (20 * np.log10(max(float(r.get('amplitude', 100)) / 100, 1e-6)))
        by.setdefault(key, {}).setdefault((lv, hv, seq), []).append((f, g))
    name = os.path.splitext(os.path.basename(path))[0]
    out = []
    for key, layers in sorted(by.items()):
        items = []
        for (lv, hv, seq), fs in sorted(layers.items()):
            it = {'f': [f for f, _ in fs], 'v': hv, 'g': [g for _, g in fs], 'mix': len(fs) > 1}
            if len(fs) == 1: it['f'], it['g'] = fs[0][0], fs[0][1]
            items.append(it)
        first = items[0]['f'] if isinstance(items[0]['f'], str) else items[0]['f'][0]
        words = WORDS(os.path.splitext(os.path.basename(first))[0]) + WORDS(os.path.basename(os.path.dirname(first)))
        out.append(_gm_sound(name, f'{name} {key}', key, items, 'sfz', path, words))
    log(f'{path}: {len(regions)} regions -> {len(out)} sounds')
    return out


def scan_dspreset(path, log=print):
    """Decent Sampler (.dspreset): <sample path loVel hiVel rootNote loNote hiNote seqPosition/>."""
    root = ET.parse(path).getroot()
    base_dir = os.path.dirname(path)
    by = {}
    for grp in root.iter('group'):
        gattr = grp.attrib
        for s in grp.iter('sample'):
            a = dict(gattr); a.update(s.attrib)
            f = os.path.normpath(os.path.join(base_dir, a.get('path', '').replace('\\', '/')))
            note = _note_num(a.get('rootNote', a.get('loNote', '60')))
            hv = int(float(a.get('hiVel', 127))); lv = int(float(a.get('loVel', 1)))
            g = float(a.get('volume', '0').replace('dB', '') or 0) if 'dB' in str(a.get('volume', '')) else 0.0
            by.setdefault((note, gattr.get('name', '')), {}).setdefault((lv, hv, a.get('seqPosition', '1')), []).append((f, g))
    name = os.path.splitext(os.path.basename(path))[0]
    out = []
    for (note, gname), layers in sorted(by.items(), key=lambda kv: (kv[0][0] or 0, kv[0][1])):
        items = [({'f': fs[0][0], 'v': hv, 'g': fs[0][1]} if len(fs) == 1 else
                  {'f': [f for f, _ in fs], 'v': hv, 'g': [g for _, g in fs], 'mix': True})
                 for (lv, hv, seq), fs in sorted(layers.items())]
        first = items[0]['f'] if isinstance(items[0]['f'], str) else items[0]['f'][0]
        words = WORDS(gname) + WORDS(os.path.splitext(os.path.basename(first))[0])
        out.append(_gm_sound(name, gname or f'{name} {note}', note or 60, items, 'dspreset', path, words))
    log(f'{path}: {len(out)} sounds')
    return out


def scan_hydrogen(path, log=print):
    """Hydrogen drumkit.xml: <instrument><name/><layer><filename/><min/><max/><gain/></layer>…"""
    root = ET.parse(path).getroot()
    strip = lambda t: t.split('}')[-1]
    base_dir = os.path.dirname(path)
    kit = next((e.text for e in root if strip(e.tag) == 'name'), os.path.basename(base_dir))
    out = []
    for i, inst in enumerate(e for e in root.iter() if strip(e.tag) == 'instrument'):
        nm = next((c.text for c in inst if strip(c.tag) == 'name'), f'Instrument {i + 1}')
        items = []
        for layer in (e for e in inst.iter() if strip(e.tag) == 'layer'):
            d = {strip(c.tag): (c.text or '') for c in layer}
            if not d.get('filename'): continue
            g = float(d.get('gain', 1) or 1)
            items.append({'f': os.path.join(base_dir, d['filename']), 'v': max(1, min(127, int(round(float(d.get('max', 1)) * 127)))),
                          'g': 20 * np.log10(max(g, 1e-6))})
        if not items:
            fn = next((c.text for c in inst if strip(c.tag) == 'filename'), None)
            if fn: items = [{'f': os.path.join(base_dir, fn), 'v': None}]
        if items:
            out.append(_gm_sound(kit, nm, 36 + i, items, 'hydrogen', path, WORDS(nm)))
    log(f'{path}: {len(out)} sounds')
    return out


# ------------------------------------------------------------------ Strike instruments
def _read_sin(path):
    import strikefmt as SF
    d = SF.read_sin(open(path, 'rb').read())
    zones = [{'sample': z[0] | (z[1] << 8), 'vel_lo': z[3], 'vel_hi': z[4], 'hh_lo': z[10], 'hh_hi': z[11],
              'splash': z[17]} for z in d['zones']]
    return {'zones': zones, 'strs': d['paths'], 'category': d['header'][1]}


def card_root(sin_path):
    """<card>/Instruments/<folder>/x.sin -> <card>"""
    p = os.path.abspath(sin_path)
    while True:
        up = os.path.dirname(p)
        if os.path.basename(p).lower() == 'instruments' or up == p:
            return up if os.path.basename(p).lower() == 'instruments' else os.path.dirname(os.path.dirname(sin_path))
        p = up


def scan_sin(paths, log=print):
    """Strike instruments: each .sin (each hi-hat pedal position / chick / splash on its own) becomes a sound,
    re-planned into the new kit's memory with the new codes. Samples on the SD card (':' paths) are read from
    the card's Samples folder; preset (internal) samples are skipped."""
    out = []
    for path in paths:
        try:
            inst = _read_sin(path)
        except Exception as e:
            log(f'  {os.path.basename(path)}: not readable ({e})'); continue
        root = card_root(path)
        name = os.path.splitext(os.path.basename(path))[0]
        groups, missing = {}, 0
        for z in inst['zones']:
            ref = inst['strs'][z['sample']] if z['sample'] < len(inst['strs']) else ''
            if not ref.startswith(':'):
                missing += 1; continue
            f = os.path.join(root, 'Samples', *ref[1:].split('/'))
            if not os.path.exists(f):
                missing += 1; continue
            k = (z['hh_lo'], z['hh_hi'], bool(z['splash']))
            groups.setdefault(k, []).append({'f': f, 'v': z['vel_hi']})
        if not groups:
            log(f'  {name}: no samples found on the card' + (' (preset samples are not copied)' if missing else '')); continue
        hat_like = len(groups) > 1 or any(k[2] for k in groups) or any(k[:2] != (0, 127) for k in groups)
        first = next(iter(groups.values()))[0]['f']
        m = CONV_RE.match(os.path.splitext(os.path.basename(first))[0])
        code0, num = conv_code(m.group('code')) if m else (None, 1)
        code0 = code0 or guess_from_words(WORDS(name) + WORDS(os.path.basename(os.path.dirname(path)))) or 'PRCHT'
        if not hat_like:
            out.append(make_sound(os.path.basename(os.path.dirname(path)), name, code0, num, groups[(0, 127, False)],
                                  'sin', label=os.path.basename(path), origin=path))
            continue
        pedal = any(k[2] for k in groups) or code0.startswith('HHP') or re.search(r'ped|foot|chick', name, re.I)
        surf = ('E' if re.search(r'edge', name, re.I) else 'B' if re.search(r'bow', name, re.I)
                else 'E' if code0.startswith('HHE') else 'B')         # the instrument's own name first
        rng = sorted(k for k in groups if not k[2])
        for k in rng + [k for k in groups if k[2]]:
            if k[2]:
                code = 'HHPSP'
            elif pedal:
                code = 'HHPCL'
            elif k[1] == 127 and k[0] >= 90:
                code = f'HH{surf}CL'
            else:
                opens = [r for r in rng if not (r[1] == 127 and r[0] >= 90)]
                code = f'HH{surf}O{min(5, len(opens) - opens.index(k))}'      # nearest closed = open 1
            out.append(make_sound(os.path.basename(os.path.dirname(path)), name, code, 1, groups[k], 'sin',
                                  label=f'{os.path.basename(path)} pedal {k[0]}-{k[1]}', origin=path))
        if missing:
            log(f'  {name}: {missing} zones use preset samples – left out')
    log(f'{len(paths)} Strike instrument(s) -> {len(out)} sounds')
    return out


# ------------------------------------------------------------------ long recordings
def scan_long(paths, log=print):
    """One WAV per drum (e.g. a snare played soft to loud): cut into single hits at build time."""
    out = []
    for p in paths:
        stem = os.path.splitext(os.path.basename(p))[0]
        code = guess_from_words(WORDS(stem) + WORDS(os.path.basename(os.path.dirname(p)))) or 'PRCHT'
        out.append(make_sound('Recordings', stem, code, 1, [{'f': p, 'v': None}], 'cut', label='cut into hits',
                              slice_=True, origin=p))
    log(f'{len(paths)} recording(s)')
    return out


def number_drums(sounds):
    """Toms and crashes of one set (top folder) get their order (tom 1 = smallest, crash 1, 2, 3), so the pad
    suggestions put them on T1H…T4H and C1…C3 like a plugin kit."""
    size = lambda s: float(re.match(r'\s*(\d+(?:\.\d+)?)', s['base']).group(1)) if re.match(r'\s*\d', s['base']) else 99
    for prefix, notes in (('TOM', TOM_NOTES), ('CRS', [49, 57, 52, 49, 57]), ('STK', [52])):
        sets = {}
        for s in sounds:
            if s['sfx'].startswith(prefix):
                top = s['group'].split(' / ')[0] if ' / ' in s['group'] else ''
                sets.setdefault(top, {}).setdefault(s['group'], []).append(s)
        for drums in sets.values():
            order = sorted(drums, key=lambda g: (drums[g][0].get('num', 1), size(drums[g][0]), g))
            for i, g in enumerate(order):
                for s in drums[g]:
                    s['note'] = notes[min(i, len(notes) - 1)]
                    a = s['sfx'][3:]
                    s['code'] = (f'tom{i + 1}' + ('R' if a == 'HD' else 'FX' if a == 'RI' else a) if prefix == 'TOM'
                                 else f'crash{i + 1}' + {'BW': 'RT', 'BL': 'BL', 'SH': 'FR', 'CH': 'CS'}.get(a, ''))
    return sounds


def scan_any(path, log=print):
    """A folder, an .sfz / .dspreset / drumkit.xml / .sin file, or a WAV recording."""
    return number_drums(_scan_any(path, log))


def _scan_any(path, log=print):
    pl = path.lower()
    if os.path.isdir(path):
        if os.path.exists(os.path.join(path, 'drumkit.xml')):
            return scan_hydrogen(os.path.join(path, 'drumkit.xml'), log)
        sins = sorted(glob.glob(os.path.join(path, '**', '*.sin'), recursive=True))
        if sins and not glob.glob(os.path.join(path, '**', '*.wav'), recursive=True):
            return scan_sin(sins, log)
        return scan_folder(path, log)
    if pl.endswith('.sfz'): return scan_sfz(path, log)
    if pl.endswith('.dspreset'): return scan_dspreset(path, log)
    if pl.endswith('.xml'): return scan_hydrogen(path, log)
    if pl.endswith('.sin'): return scan_sin([path], log)
    if pl.endswith(AUDIO_EXT): return scan_long([path], log)
    raise ValueError(f'unknown source: {path}')


# ------------------------------------------------------------------ audio
def resample(a, sr, to=SR):
    """FFT resampling (no extra packages): 44.1 / 96 kHz samples -> 48 kHz like the factory samples."""
    if sr == to:
        return a
    n = len(a); m = int(round(n * to / sr))
    pad = 1 << int(np.ceil(np.log2(max(n, 2))))          # power of two: fast, and less edge ringing
    X = np.fft.rfft(np.pad(a, ((0, pad - n), (0, 0))), axis=0)
    mpad = int(round(pad * to / sr))
    Y = np.zeros((mpad // 2 + 1, a.shape[1]), complex)
    k = min(len(X), len(Y)); Y[:k] = X[:k]
    y = np.fft.irfft(Y, mpad, axis=0) * (mpad / pad)
    return y[:m].astype(np.float32)


def _load_item(it):
    fs = it['f'] if isinstance(it['f'], list) else [it['f']]
    gs = it.get('g', 0.0); gs = gs if isinstance(gs, list) else [gs] * len(fs)
    parts = []
    for f, g in zip(fs, gs):
        a, sr = read_wav(f)
        a = resample(a, sr)
        parts.append(a * (10 ** ((g or 0) / 20)))
    if it.get('lr') and len(parts) == 2:                   # separate left / right files -> one stereo hit
        n = max(len(p) for p in parts)
        return np.stack([np.pad(p.mean(1), (0, n - len(p))) for p in parts], 1)
    if len(parts) == 1:
        return parts[0]
    ch = max(p.shape[1] for p in parts); n = max(len(p) for p in parts)        # several mics -> mixed
    out = np.zeros((n, ch), np.float32)
    for p in parts:
        p = np.repeat(p, ch, 1) if p.shape[1] < ch else p
        out[:len(p)] += p
    return out


def load_hits(src, log=print):
    """Measured hits of one sound (all at 48 kHz, all mono or all stereo)."""
    hits = []
    for it in src['items']:
        try:
            a = _load_item(it)
        except Exception as e:
            log(f"    skipped {it['f']}: {e}"); continue
        f = it['f'] if isinstance(it['f'], str) else it['f'][0]
        if src.get('slice') or (it.get('v') is None and len(a) / SR > 8):
            for seg in split_hits(a, SR):
                hits.append(measure(seg, SR, f, None))
        else:
            hits.append(measure(a, SR, f, it.get('v')))
    hits = [h for h in hits if len(h.a) >= int(0.02 * SR) and h.peak > 1e-5]
    if hits and any(h.a.shape[1] == 2 for h in hits):
        for h in hits:
            if h.a.shape[1] == 1:
                h.a = np.repeat(h.a, 2, 1)
    return hits


def preview_file(src):
    """The file that best shows the sound (loudest velocity / first number), for ▶ Play and the level column."""
    its = src['items']
    best = max(its, key=lambda i: (i.get('v') or 0, -(i.get('n') or 0)))
    return best['f'] if isinstance(best['f'], str) else best['f'][0]


def source_bytes(src):
    tot = 0
    for it in src['items']:
        for f in (it['f'] if isinstance(it['f'], list) else [it['f']]):
            try:
                tot += os.path.getsize(f)
            except OSError:
                pass
    return tot
