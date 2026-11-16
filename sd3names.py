"""Real drum names for Toontrack drum codes, read from the sound databases that Superior Drummer 3 /
EZdrummer install (SQLite files):  C:\\ProgramData\\Toontrack\\<product>\\SoundDatabase\\<library>\\soundDB
e.g. SL-DEATH + SD04_01 -> '6.5x14" Tama Bell Brass 1980s'.  Also builds short Strike instrument names
(max 26 characters, e.g. '6.5x14 Tama BellBrass 80s_RO')."""
import os, re, glob, sqlite3

DB_ROOTS = [r'C:\ProgramData\Toontrack\Superior Drummer 3\SoundDatabase',
            r'C:\ProgramData\Toontrack\EZdrummer 3\SoundDatabase',
            r'C:\ProgramData\Toontrack\EZdrummer 2\SoundDatabase']
_cache = {}

# Toontrack articulation code -> (description, 2-letter articulation). The Strike code is 5 letters:
# instrument type first, then the articulation (the agreed sample code), e.g. SNRHD snare head, SNRXS
# cross-stick, SNRRI rimshot, HHBCL hi-hat bow closed, HHBO1 hi-hat bow open 1, HHECL hi-hat edge closed.
# SD3 does not store articulation names in the kit; the meanings are checked against Superior Drummer 3's
# own key map (SDX-Keys.pdf): snareMC Mid Center, RF Ruffs, hatsCT Tight Edge, TT Tight Tip, TP Closed Tip,
# LO Open Min, cymbal '' Crashed, RT Bow Tip, FR Bow Shank, BL Bell Shank, BT Bell Tip, M Muted,
# ride PU Crashed, ride '' Bow Tip, kickR Open.
TYPE_CODE = {'kick': 'KCK', 'snare': 'SNR', 'rim': 'SNR', 'tom': 'TOM', 'crash': 'CRS', 'ride': 'RID',
             'other': 'PRC', 'splash': 'SPL', 'china': 'CHN', 'stack': 'STK'}
DRUM_ART = {'R': ('Center (head)', 'HD'), 'L': ('Center, left hand', 'LH'), 'FX': ('Rimshot', 'RI'),
            'RO': ('Rim only', 'RO'), 'SL': ('Sidestick (cross-stick)', 'XS'), 'SS': ('Sidestick (cross-stick)', 'XS'),
            'FL': ('Flam', 'FL'), 'RF': ('Ruffs', 'RF'), 'MC': ('Mid center', 'MC'),
            'E': ('Edge', 'ED'), 'TH': ('Thump', 'TH'), 'M': ('Muted', 'MU'), 'MT': ('Muted', 'MU')}
KICK_ART = {'R': ('Kick (open)', 'HD'), 'L': ('Kick, left foot', 'LF'), 'O': ('Kick, open', 'OP'),
            'H': ('Kick (beater stays)', 'HB'), 'M': ('Kick, muted', 'MU')}
# hi-hat: HH + surface (B bow/tip, E edge, L bell, P pedal) + articulation
HAT_ART = {'TP': ('Closed tip', 'HHBCL'), 'TT': ('Tight tip', 'HHBTT'), 'CT': ('Tight edge', 'HHETT'),
           'CL': ('Closed edge', 'HHECL'), 'LO': ('Open min (edge)', 'HHEMN'), 'BL': ('Closed bell', 'HHLCL'),
           'PL': ('Closed pedal (chick)', 'HHPCL'), 'PLO': ('Open pedal (foot splash)', 'HHPSP'),
           'SQ': ('Seq hits', 'HHSEQ')}
for _i in range(7):
    HAT_ART[f'T{_i}'] = (f'Open tip {_i}', f'HHBO{_i}')
    HAT_ART[f'O{_i}'] = (f'Open {_i} (edge)', f'HHEO{_i}')
    HAT_ART[f'B{_i}'] = (f'Open bell {_i}', f'HHLO{_i}')
    HAT_ART[f'M{_i}'] = (f'Muted {_i}', f'HHMU{_i}')
CYM_ART = {'': ('Crashed (edge)', 'ED'), 'RT': ('Bow tip', 'BW'), 'FR': ('Bow shank', 'SH'),
           'RD': ('Bow shank', 'SH'), 'BL': ('Bell shank', 'BL'), 'BT': ('Bell tip', 'BT'),
           'M': ('Muted', 'MU'), 'CS': ('Crashed, choke', 'CH'), 'FX': ('Crashed FX', 'FX'),
           'TL': ('Tail', 'TL'), 'PU': ('Crashed (edge)', 'ED'), 'R2': ('Bow tip 2', 'B2')}
RIDE_ART = dict(CYM_ART, **{'': ('Bow tip', 'BW'), 'PU': ('Crashed (edge)', 'ED')})
# whole hi-hat instruments built from several articulations
HAT_BOW, HAT_EDGE, HAT_PEDAL = 'HHBOW', 'HHEDG', 'HHPED'


def type_code(role, pos=''):
    p = (pos or '').lower()
    if role in ('crash', 'ride', 'other'):
        for k in ('splash', 'china', 'stack'):
            if k in p:
                return TYPE_CODE[k]
    return TYPE_CODE.get(role, 'PRC')


def art_info(code, role, pos=''):
    """('snareRO', 'snare') -> ('Rim only', 'SNRRO'): instrument type first, then the articulation."""
    s = re.sub(r'^[a-z]+\d*', '', code or '')
    p = (pos or code or '').lower()
    if role in ('hihat', 'pedal'):
        if s in HAT_ART:
            return HAT_ART[s]
        return s or 'Hit', ('HHP' if role == 'pedal' else 'HH') + (s.upper() or 'HT')[:5 - (3 if role == 'pedal' else 2)]
    t = type_code(role, pos or code)
    table = {'kick': KICK_ART, 'ride': RIDE_ART, 'crash': CYM_ART}.get(role, DRUM_ART)
    if s in table:
        long, a = table[s]
        if t in ('SPL', 'CHN', 'STK') and not s:
            long = {'SPL': 'Splash', 'CHN': 'China', 'STK': 'Stack'}[t]
        return long, t + a
    if not s:
        if 'cowbell' in p:
            return 'Cowbell', t + 'CB'
        return 'Hit', t + 'HT'
    return s, t + s.upper()[:2]


def art_suffix(code, role, pos=''):
    return art_info(code, role, pos)[1]


def art_long(code, role, pos=''):
    return art_info(code, role, pos)[0]


# shortenings tried in order until a name fits
ABBREV = [(r'\b19(\d0)s\b', r'\1s'), (r'Istanbul Agop', 'Agop'), (r'Traditional', 'Trad'), (r'Anniversary', 'Anniv'),
          (r'Collectors', 'Coll'), (r'Recording Custom', 'RC'), (r'Designer Series', 'Designer'), (r'Square Badge', 'SqBadge'),
          (r'Medium', 'Med'), (r'Supraphonic', 'Supra'), (r'Hollywood', 'Hwood'), (r' B/O [Bb]adge', ''), (r'Custom', 'Cust'),
          (r'Zildjian', 'Zil'), (r'Sabian', 'Sab'), (r'Ludwig', 'Lud'), (r'Gretsch', 'Gret'), (r'Yamaha', 'Yam'),
          (r'Series', ''), (r'Maple', 'Mpl'), (r'Brass', 'Br'), (r' - ', ' '), (r'no front head', 'NoReso'), (r'front head', 'reso'), (r'with ', 'w '), (r'Session', 'Sess'),
          (r'Special', 'Spec'), (r'Constantinople', 'Const')]
BAD = r'[\\/:*?"<>|]'
PLAIN = r'[^A-Za-z0-9 ._()-]'


def _db(lib):
    if lib in _cache:
        return _cache[lib]
    d = {}
    for root in DB_ROOTS:
        p = os.path.join(root, lib, 'soundDB')
        if not os.path.exists(p):
            continue
        try:
            c = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
            for code, name, pos in c.execute(
                    'select d.Name, e.Name, p.Name from SOUNDENTITY e join SDXDRUMS d on d.ID = e.SDXDrumID '
                    'left join SDXPOSITIONS p on p.ID = e.SDXPositionID'):
                if code and name:
                    d.setdefault(code, name.strip())
            c.close()
        except Exception:
            pass
        if d:
            break
    _cache[lib] = d
    return d


def drum_name(lib, code):
    """'SL-DEATH', 'SD04_01' -> '6.5x14" Tama Bell Brass 1980s' (or '' if unknown)."""
    if not lib or not code:
        return ''
    return _db(lib).get(code, '')


def clean(name):
    n = re.sub(r'["″]', ' ', name)                # 18" Zildjian -> 18 Zildjian
    n = re.sub(PLAIN, ' ', n)                       # plain characters only, like the factory instruments
    return re.sub(r'\s+', ' ', n).strip()


def fit(base, suffix='', limit=26):
    """Strike name: '<CODE>_<drum name>' (CRASH_18 Agop 30th Anniv) shortened to the 26 characters the
    module allows. The code comes first so the module's list shows what each instrument is."""
    tail = f'{suffix}_' if suffix else ''
    # shorten every name of one drum the same way (room for a 5-letter code), and further only when
    # a longer suffix needs it
    room = min(limit - 6, limit - len(tail))
    for pat, rep in ABBREV:
        if len(clean(base)) <= room:
            break
        base = re.sub(r'\s+', ' ', re.sub(pat, rep, base)).strip()
    base = clean(base)
    while len(base) > room and base.count(' ') > 1:   # then join words from the right: Bell Br -> BellBr
        i = base.rfind(' ')
        base = base[:i] + base[i + 1:]
    if len(base) > room:
        base = base[:room].rstrip(' -_')
    return tail + base


