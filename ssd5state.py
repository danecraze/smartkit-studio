"""Kit layout of Steven Slate Drums 5 (SSDSampler5) from the plugin's saved state.

The VST3 state is JUCE's IComponent blob (same encoding as Superior Drummer's) holding one XML element
<SSD_SAMPLER_STATE …> with flat attributes, e.g.

    SamplerInstrumentInfo_Idx_1m_instrumentName="Snare Tma 6 BBR"
    SamplerInstrumentInfo_Idx_1ArticulationInfo_Idx_1m_name="Snare Rimshot"
    SamplerInstrumentInfo_Idx_1ArticulationInfo_Idx_1m_nRemappedNoteOn="40"

parse() returns the same list of articulation dicts as sd3state.parse(), with SD3-style codes so the rest of
SmartKit (names, types, hi-hat building, pad suggestions) works unchanged. Instruments layered on the same
notes (SSD5 plays both) are recorded once, as the plugin plays them.
"""
import re

SKIPPED = []          # articulations left out (and why)

# SSD5 articulation name (lower case, without the instrument word) -> SD3-style suffix
HAT = {'tip closed': 'TP', 'tip open': 'T5', 'shank closed': 'CL', 'shank open': 'O5',
       'pedal': 'PL', 'footsplash': 'PLO', 'foot splash': 'PLO'}
for _i in range(1, 5):
    HAT[f'tip {_i}/5 open'] = f'T{_i}'
    HAT[f'shank {_i}/5 open'] = f'O{_i}'
DRUM = {'': 'R', 'center': 'R', 'rimshot': 'FX', 'rimshot edge': 'RE', 'side': 'SD', 'sidestick': 'SL',
        'rimclick': 'RO', 'rim click': 'RO', 'rim': 'RO', 'flam': 'FL', 'ruff': 'RF', 'ruffs': 'RF'}
CYM = {'edge': '', 'crash': '', 'bow': 'RT', 'bow tip': 'RT', 'bow shank': 'FR', 'bell': 'BL', 'choke': 'CS'}
RIDE = {'bow tip': '', 'bow': '', 'bow shank': 'FR', 'bell': 'BL', 'edge': 'PU', 'crash': 'PU', 'choke': 'CS'}
SKIP = ('double', 'rolls', 'roll', ' ed')            # double-pedal copies, rolls, e-drum duplicates ("… eD")


def _attrs(raw):
    i = raw.find(b'<IComponent>')
    j = raw.find(b'</IComponent>')
    if i < 0 or j < 0:
        return None
    import sd3state
    size, _, b64 = raw[i + 12:j].decode('latin-1').partition('.')
    try:
        data = sd3state.juce_b64(int(size), b64)
    except ValueError:
        return None
    k = data.find(b'<SSD_SAMPLER_STATE')
    if k < 0:
        return None
    text = data[k:].decode('latin-1', 'replace')
    return dict(re.findall(r'(\w+)="([^"]*)"', text))


def _role(name):
    n = name.lower()
    for word, role in (('kick', 'kick'), ('snare', 'snare'), ('tom', 'tom'), ('hi-hat', 'hihat'), ('hihat', 'hihat'),
                       ('ride', 'ride'), ('crash', 'crash'), ('splash', 'crash'), ('china', 'crash'),
                       ('stack', 'crash')):
        if n.startswith(word) or f' {word}' in n:
            return role
    return 'other'


def parse(raw):
    """[] when the state is not SSD5's."""
    A = _attrs(raw) if raw else None
    SKIPPED.clear()
    if not A:
        return []
    inst, arts = {}, {}
    for k, v in A.items():
        m = re.match(r'SamplerInstrumentInfo_Idx_(\d+)m_(instrumentName|isLoaded|libraryName)$', k)
        if m:
            inst.setdefault(int(m[1]), {})[m[2]] = v
            continue
        m = re.match(r'SamplerInstrumentInfo_Idx_(\d+)ArticulationInfo_Idx_(\d+)m_(name|nRemappedNoteOn|nNativeNoteOn)$', k)
        if m:
            arts.setdefault((int(m[1]), int(m[2])), {})[m[3]] = v
    out, taken, toms, cyms = [], {}, [], []
    for i in sorted(inst):                                     # number toms / cymbals in kit order
        r = _role(inst[i].get('instrumentName', ''))
        if r == 'tom': toms.append(i)
        if r == 'crash': cyms.append(i)
    for (i, j) in sorted(arts):
        info, a = inst.get(i, {}), arts[(i, j)]
        iname = re.sub(r'\s+', ' ', info.get('instrumentName', '')).strip()
        if not iname or info.get('isLoaded', '1') == '0':
            continue
        try:
            note = int(a.get('nRemappedNoteOn') or a.get('nNativeNoteOn'))
        except (TypeError, ValueError):
            continue
        aname = a.get('name', '').strip()
        role = _role(iname)
        first = iname.split(' ')[0]                            # 'Snare', 'Tom', 'Hi-Hat', 'Crash' …
        art = aname[len(first):].strip() if aname.lower().startswith(first.lower()) else aname
        low = ' ' + art.lower()
        if any(low.endswith(s) or f'{s} ' in low for s in SKIP) or not 0 <= note < 128:
            SKIPPED.append(f'{iname}: {aname}'); continue
        if note in taken:                                      # layered with an instrument already listed
            SKIPPED.append(f'{iname}: {aname} (plays together with {taken[note]})'); continue
        taken[note] = iname
        a_l = art.lower()
        if role == 'hihat':
            sfx = HAT.get(a_l, a_l.upper().replace(' ', '')[:3])
            prefix = 'hats'
            if sfx in ('PL', 'PLO'):
                role = 'pedal'
        elif role == 'ride':
            sfx, prefix = RIDE.get(a_l, a_l.upper()[:2]), 'ride'
        elif role == 'crash':
            sfx, prefix = CYM.get(a_l, a_l.upper()[:2]), f'crash{cyms.index(i) + 1}'
        elif role == 'kick':
            sfx, prefix = 'R', 'kick'
        elif role in ('snare', 'tom'):
            sfx = DRUM.get(a_l, a_l.upper()[:2])
            prefix = 'snare' if role == 'snare' else f'tom{toms.index(i) + 1}'
            if role == 'snare' and sfx in ('SL', 'RO'):
                role = 'rim'
        else:
            sfx, prefix = a_l.replace(' ', '').upper()[:2], re.sub(r'[^a-z]', '', first.lower()) or 'perc'
        # display: 'Tom 2', 'Crash L', 'Hi-Hat' + the drum ('Lwg VCL 12')
        words = iname.split(' ')
        pos = first if role not in ('tom',) else f'Tom {toms.index(i) + 1}'
        if role == 'crash' and len(words) > 1 and words[1] in ('L', 'R', 'M', '1', '2', '3'):
            pos = f'{first} {words[1]}'
        drum = ' '.join(w for w in words[1:] if w not in ('L', 'R', 'M')) or iname
        out.append(dict(box=i, pos=pos, drum=drum, lib=info.get('libraryName', 'SSD'), type=role,
                        code=prefix + sfx, notes=[note], play=note, suffix=sfx,
                        label=art or aname or 'Hit', role=role, inst=pos, group=f'{pos} – {drum}',
                        drum_name=drum if role != 'other' else iname, art_name=aname))
    return out
