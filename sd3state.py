"""Read the kit layout (instruments, articulations, MIDI notes) out of a Toontrack plugin's
saved state (Superior Drummer 3; EZdrummer uses the same engine).

pedalboard's plugin.raw_state is JUCE XML: <VST3PluginState><IComponent>SIZE.JUCEBASE64</IComponent>...
The decoded component state holds Toontrack's text format, e.g.

    instbox 1 {
     xpad 0 SL-FIELDSOFROCKDRY {
      pos "Snare"
      drum "SD34_01"  "-" 0
      ...
      alias snareR 68 38 70        <- articulation 'snareR' is played by notes 68, 38 and 70
      alias snareSL 37 67
     InstrumentType Snare
"""
import re

_CH = '.ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+'
# notes that most drum maps agree on (GM): used to label articulations and suggest pads
GM_LABEL = {35: 'Kick', 36: 'Kick', 37: 'Sidestick', 38: 'Center', 40: 'Rimshot', 42: 'Closed', 44: 'Pedal',
            46: 'Open', 49: 'Crash', 51: 'Bow', 52: 'China', 53: 'Bell', 55: 'Splash', 57: 'Crash', 59: 'Edge'}
SUFFIX_LABEL = {'BL': 'Bell', 'M': 'Mute', 'R': 'Center', 'Trig': 'Trigger', 'Ctrl': 'Controller'}
TYPE_ROLE = {'kick': 'kick', 'snare': 'snare', 'toms': 'tom', 'tom': 'tom', 'hi-hat': 'hihat', 'ride': 'ride',
             'cymbal': 'crash'}


def juce_b64(size, s):
    out = bytearray(size); bit = 0
    for ch in s:
        v = _CH.find(ch)
        if v < 0:
            continue
        for k in range(6):
            if v >> k & 1 and bit // 8 < size:
                out[bit // 8] |= 1 << (bit % 8)
            bit += 1
    return bytes(out)


def state_text(raw):
    """raw_state bytes -> Toontrack state text (or '' if this isn't a Toontrack state)."""
    s = raw.decode('latin1', 'replace')
    m = re.search(r'<IComponent>(\d+)\.([^<]*)</IComponent>', s)
    data = juce_b64(int(m.group(1)), m.group(2)) if m else raw
    txt = '\n'.join(x.decode('latin1') for x in re.findall(rb'[ -~\t]{3,}', data))
    return txt if 'instbox' in txt and 'alias' in txt else ''


def pretty_pos(pos):
    p = re.sub(r'(?<=[a-z])(?=[A-Z0-9])', ' ', pos)            # Racktom1 -> Racktom 1
    p = p.replace('Racktom', 'Rack Tom').replace('Floortom', 'Floor Tom')
    return p.strip()


SKIPPED = []      # articulations switched off in the plugin, from the last parse()
UNREACHABLE = []  # articulations no MIDI note can play (the E-drum map sends their notes elsewhere)
EDRUM = {}        # name of the active E-drum (MIDI In) map and how it changes incoming notes


def edrum_map(txt):
    """Superior Drummer's MIDI In / E-drum preset (saved with the kit, e.g. 'STRIKE - SD3') changes incoming
    notes before they reach the kit:  'note 48 transpose 89'  -> note 48 plays whatever note 89 plays;
    'usermap 57 crash1 86 -1' -> note 57 plays articulation crash1 (its note 86).
    Returns (name, {incoming note: note it plays}) – only notes that are changed."""
    m = re.search(r'EdrumPreset (\d+) "([^"]*)" \{', txt)
    if not m:
        return '', {}
    body = txt[m.end():]
    end = re.search(r'\n\s*(Trafo|\}|[A-Z][A-Za-z]+ \{)', body)
    body = body[:end.start()] if end else body[:5000]
    remap = {}
    for x, y in re.findall(r'note (\d+) transpose (\d+)', body):
        remap[int(x)] = int(y)
    for x, code, y in re.findall(r'usermap (\d+) (\S+) (\d+)', body):
        remap[int(x)] = int(y)
    return m.group(2), remap


def parse(raw, include_off=False):
    """Returns a list of articulations:
       {box, inst, pos, drum, type, role, code, suffix, notes, label}  (empty list if not Toontrack).
    Articulations switched off in Superior Drummer ('blocksounds' in their pad block = not loaded,
    the plugin then plays a stand-in sound) are left out unless include_off."""
    txt = state_text(raw)
    if not txt:
        return []
    name, remap = edrum_map(txt)
    EDRUM.clear(); EDRUM.update(name=name, remap=remap)
    arts, box, xpad, pos, drum, itype, lib, pending = [], None, 0, '', '', '', '', []
    blocked, cur = set(), None

    def flush():
        for code, notes in pending:
            arts.append(dict(box=box, pos=pos, drum=drum, lib=lib, type=itype, code=code, notes=notes,
                             off=(box, code) in blocked))
        pending.clear()

    for line in txt.split('\n'):
        l = line.strip()
        m = re.match(r'instbox (\d+) \{', l)
        if m:
            flush(); box, xpad, pos, drum, itype, lib = int(m.group(1)), 0, '', '', '', ''
            continue
        m = re.match(r'xpad (\d+) (\S+)', l)
        if m:
            xpad = int(m.group(1))
            if xpad == 0 and not lib:
                lib = m.group(2).strip('{')
            continue
        if box is None:
            continue
        m = re.match(r'pad (\S+) \{', l)
        if m:
            cur = m.group(1) if xpad == 0 else None; continue
        if l == 'blocksounds' and cur:
            blocked.add((box, cur)); continue
        m = re.match(r'pos "([^"]+)"', l)
        if m and xpad == 0 and not pos:
            pos = m.group(1); continue
        m = re.match(r'drum (\S+)', l)
        if m and xpad == 0 and not drum:
            drum = m.group(1).strip('"'); continue
        m = re.match(r'alias (\S+) (.+)$', l)
        if m and xpad == 0:
            notes = [int(x) for x in m.group(2).split() if x.isdigit() and int(x) < 128]
            if notes:
                pending.append((m.group(1), notes))
            continue
        m = re.match(r'InstrumentType (.+)$', l)
        if m:
            itype = m.group(1).strip()
            flush()
            continue
    flush()
    # tidy up: labels, roles, drop empty slots and switched-off articulations
    out = []
    SKIPPED.clear(); UNREACHABLE.clear()
    for a in arts:
        if a['drum'] in ('-', ''):
            continue
        if a['off'] and not include_off:
            SKIPPED.append(a); continue
        a['play'] = playable_note(a['notes'], remap)
        if a['play'] is None:
            UNREACHABLE.append(a); continue
        code = a['code']
        suffix = re.sub(r'^[a-z]+\d*', '', code)          # snareR -> R, tom1RO -> RO, crash2 -> ''
        if suffix.endswith('Trig') or suffix == 'Ctrl':
            continue                                      # e-drum trigger / controller inputs
        gm = next((GM_LABEL[n] for n in a['notes'] if n in GM_LABEL), None)
        label = gm or SUFFIX_LABEL.get(suffix) or (suffix or 'Hit')
        a.update(inst=pretty_pos(a['pos']), suffix=suffix, label=label,
                 role=TYPE_ROLE.get(a['type'].lower(), 'other'))
        try:                                              # real drum name from the plugin's sound database
            import sd3names
            a['drum_name'] = sd3names.drum_name(a['lib'], a['drum'])
        except Exception:
            a['drum_name'] = ''
        if a['role'] == 'hihat' and (44 in a['notes'] or suffix.startswith('PL')):
            a['role'] = 'pedal'
        if a['role'] == 'snare' and (37 in a['notes'] or 40 in a['notes']):
            a['role'] = 'rim'
        if a['role'] == 'crash' and 'splash' in a['pos'].lower():
            a['label'] = 'Splash' if a['label'] in ('Hit', 'Crash') else a['label']
        out.append(a)
    # several kit pieces can have the same position name (two 'Crash 2'): tell them apart by the drum
    cnt = {}
    for a in out:
        cnt.setdefault(a['inst'], set()).add(a['box'])
    seen = {}
    for a in out:
        if len(cnt[a['inst']]) == 1:
            a['group'] = a['inst']
        else:
            d = a.get('drum_name') or ''
            g = f"{a['inst']} – {d}" if d else a['inst']
            boxes = seen.setdefault(g, [])          # same position AND same drum twice: number them
            if a['box'] not in boxes:
                boxes.append(a['box'])
            n = boxes.index(a['box']) + 1
            a['group'] = g if n == 1 else f'{g} ({n})'
    return out


def playable_note(notes, remap):
    """The MIDI note to send so the plugin really plays an articulation whose own notes are `notes`,
    allowing for the E-drum map (a note that is redirected elsewhere would play a different sound)."""
    eff = lambda x: remap.get(x, x)
    own = [n for n in notes if eff(n) in notes]                      # its own notes that aren't redirected
    if own:
        gm = [n for n in own if n in GM_LABEL]
        return gm[0] if gm else own[0]
    other = [x for x in range(128) if eff(x) in notes]               # another note the map sends here
    return other[0] if other else None


def primary_note(a):
    if a.get('play') is not None:
        return a['play']
    gm = [n for n in a['notes'] if n in GM_LABEL]
    return gm[0] if gm else a['notes'][0]


if __name__ == '__main__':
    import sys
    for a in parse(open(sys.argv[1], 'rb').read()):
        if a['suffix'] in ('Ctrl',):
            continue
        print(f"{a['box']:2d} {a['group']:20s} {a['type']:8s} {a['role']:6s} {a['code']:12s} {a['label']:10s} {a['notes']}")
