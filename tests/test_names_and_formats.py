import sd3names, sources, strikefmt as SF


def test_type_first_codes():
    assert sd3names.art_info('snareR', 'snare')[1] == 'SNRHD'
    assert sd3names.art_info('snareSL', 'rim')[1] == 'SNRXS'
    assert sd3names.art_info('hatsTP', 'hihat')[1] == 'HHBCL'
    assert sd3names.art_info('hatsT1', 'hihat')[1] == 'HHBO1'
    assert sd3names.art_info('hatsPLO', 'pedal')[1] == 'HHPSP'
    assert sd3names.art_info('ride4PU', 'ride')[1] == 'RIDED'
    assert sd3names.art_info('splash1', 'crash', 'Splash')[1] == 'SPLED'


def test_names_fit_26_plain_characters():
    n = sd3names.fit('18" Istanbul Agop 30th Anniversary', 'CRSED')
    assert n.startswith('CRSED_') and len(n) <= 26
    assert all(c.isalnum() or c in ' ._()-' for c in n)


def test_converter_codes():
    assert sources.conv_code('SnSS')[0] == 'SNRXS'
    assert sources.conv_code('HP')[0] == 'HHPCL'      # pedal chick
    assert sources.conv_code('HF')[0] == 'HHPSP'      # foot splash
    assert sources.conv_code('Ri1B')[0] == 'RIDBL'
    assert sources.conv_code('Cr2E') == ('CRSED', 2)
    assert sources.conv_code('T3R') == ('TOMRI', 3)


def test_plain_pack_words():
    g = lambda s: sources.guess_from_words(sources.WORDS(s))
    assert g('Snare Rimshot 01') == 'SNRRI'
    assert g('HH_Zild14K_open_3') == 'HHBO3'
    assert g('Hi-Hat foot splash') == 'HHPSP'
    assert g('Ride bell') == 'RIDBL'
    assert g('ZildAThin18 choke') == 'CRSCH'


def test_sin_round_trip():
    zones = [SF.make_zone(0, 1, 63), SF.make_zone(1, 64, 127, pedal_lo=7, splash=120)]
    b = SF.write_sin(zones, [':Kit/a v063 r1.wav', ':Kit/a v127 r1.wav'], category=SF.CAT_HIHAT)
    d = SF.read_sin(b)
    assert d['header'][1] == SF.CAT_HIHAT and len(d['zones']) == 2
    assert d['zones'][1][17] == 120 and d['zones'][1][10] == 7
    assert d['paths'][1] == ':Kit/a v127 r1.wav'


def test_safe_names_never_leave_their_folder():
    import smartkit as SK
    for bad in ('..', '.', '  ', '', '../x', '..\\..\\Windows', 'CON', 'nul.txt', 'Kit. ', '...hidden'):
        n = SK.safe(bad, 26, fallback='Kit')
        assert n and n not in ('.', '..') and not n.startswith('.') and not n.endswith(('.', ' '))
        assert '/' not in n and '\\' not in n
        assert n.split('.')[0].upper() not in SK.WIN_RESERVED
    assert SK.safe('SNRHD_14 Maple') == 'SNRHD_14 Maple'


def test_ssd5_layout_from_state():
    """Steven Slate Drums 5: drums, articulations and notes come from the plugin state (no note scan)."""
    import os, sd3state, ssd5state

    def juce_encode(data):                               # inverse of sd3state.juce_b64 (6 bits LSB first)
        bits = ''.join(format(b, '08b')[::-1] for b in data)
        bits += '0' * (-len(bits) % 6)
        return ''.join(sd3state._CH[int(bits[i:i + 6][::-1], 2)] for i in range(0, len(bits), 6))
    attrs = {'SamplerInstrumentInfo_Idx_0m_instrumentName': 'Snare Tma 6 BBR',
             'SamplerInstrumentInfo_Idx_1m_instrumentName': 'Hi-Hat Sbn 14 AAM',
             'SamplerInstrumentInfo_Idx_2m_instrumentName': 'Snare Slate NRG'}
    arts = [(0, 'Snare Center', 38), (0, 'Snare Rimshot', 40), (0, 'Snare Sidestick', 37), (0, 'Snare Rolls', 21),
            (1, 'Hi-Hat Tip 2/5 Open', 68), (1, 'Hi-Hat Shank Closed', 60), (1, 'Hi-Hat Pedal', 72),
            (1, 'Hi-Hat Footsplash', 73), (1, 'Hi-Hat Tip Closed eD', 42), (2, 'Snare Center', 38)]
    cnt = {}
    for i, name, note in arts:
        j = cnt[i] = cnt.get(i, -1) + 1
        attrs[f'SamplerInstrumentInfo_Idx_{i}ArticulationInfo_Idx_{j}m_name'] = name
        attrs[f'SamplerInstrumentInfo_Idx_{i}ArticulationInfo_Idx_{j}m_nRemappedNoteOn'] = str(note)
    xml = '<?xml version="1.0"?> <SSD_SAMPLER_STATE ' + ' '.join(f'{k}="{v}"' for k, v in attrs.items()) + '/>'
    data = b'VC2!' + xml.encode()
    raw = f'<VST3PluginState><IComponent>{len(data)}.{juce_encode(data)}</IComponent></VST3PluginState>'.encode()
    assert sd3state.parse(raw) == []
    lay = ssd5state.parse(raw)
    got = {(a['code'], a['role'], a['notes'][0]) for a in lay}
    assert got == {('snareR', 'snare', 38), ('snareFX', 'snare', 40), ('snareSL', 'rim', 37),
                   ('hatsT2', 'hihat', 68), ('hatsCL', 'hihat', 60), ('hatsPL', 'pedal', 72), ('hatsPLO', 'pedal', 73)}
    assert any('Rolls' in s for s in ssd5state.SKIPPED) and any('eD' in s for s in ssd5state.SKIPPED)
    assert any('plays together' in s for s in ssd5state.SKIPPED)


def test_host_channel_and_sound_check():
    """sound_check finds a plugin that only answers on MIDI channel 10; notes are then sent there."""
    import numpy as np, host as H
    h = H.DrumHost()
    sent = []

    class Plug:
        def __call__(self, msgs, duration, **kw):
            sent.extend(m for m, t in msgs)
            n = int(duration * H.SR)
            loud = any(m[0] == 0x99 for m, t in msgs)
            return np.full((2, n), 0.5 if loud else 0.0, np.float32)
    h.plugin = Plug()
    import time as _t
    orig = _t.sleep; _t.sleep = lambda s: None
    try:
        assert h.sound_check(36) is True
    finally:
        _t.sleep = orig
    assert h.channel == 9 and h.realtime is False
    sent.clear(); h._run([(bytes([0x90, 38, 100]), 0.0), (bytes([0x80, 38, 0]), 0.1)], 0.2)
    assert [m[0] for m in sent] == [0x99, 0x89]


def test_plugin_window_runs_on_plugin_thread(monkeypatch):
    """The plugin is loaded and its window shown on the plugin thread; open_editor returns at once,
    renders keep working meanwhile, and on_closed runs when the window closes."""
    import sys, types, threading, time, numpy as np, host as H
    calls = {}

    class Plug:
        def __call__(self, msgs, duration, **kw):
            return np.zeros((2, int(duration * H.SR)), np.float32)

        def show_editor(self, ev):
            calls['editor_thread'] = threading.current_thread().name
            ev.wait(5)
    fake = types.SimpleNamespace(load_plugin=lambda path, initialization_timeout=0:
                                 (calls.__setitem__('load_thread', threading.current_thread().name), Plug())[1])
    monkeypatch.setitem(sys.modules, 'pedalboard', fake)
    h = H.DrumHost(); h.audio_out = 'off'
    h.load('x.vst3', wait=1)
    assert calls['load_thread'] == 'plugin'
    ev, closed = threading.Event(), threading.Event()
    t = time.time()
    h.open_editor(ev, on_closed=lambda err: closed.set())
    assert time.time() - t < 1                                  # returned straight away
    for _ in range(50):
        if h.editor_open: break
        time.sleep(0.02)
    assert h.editor_open and calls['editor_thread'] == 'plugin'
    h.hold = True
    assert h._run([], 0.1).shape == (int(0.1 * H.SR), 2)        # a job can render while the window is open
    h.hold = False
    ev.set()
    assert closed.wait(3) and not h.editor_open


def test_dawdreamer_player_helper(tmp_path, monkeypatch):
    """The DawDreamer helper process: render, state, window blocking, kit on other outputs mixed to stereo."""
    import os, shutil, threading, time
    import ddhost, host
    shutil.copy(os.path.join(os.path.dirname(__file__), 'fake_dawdreamer.py'), tmp_path / 'dawdreamer.py')
    monkeypatch.setenv('PYTHONPATH', str(tmp_path))
    assert ddhost.wants_dd(r'C:\VST3\SSDSampler5.vst3') and not ddhost.wants_dd('Superior Drummer 3.vst3')
    p = ddhost.DDPlugin('/x/SSDSampler5.vst3')
    try:
        a = p([(bytes([0x90, 38, 127]), 0.01), (bytes([0x80, 38, 0]), 0.11)], 1.0)
        assert a.shape == (2, 44100) and a.max() > 0.5
        p.raw_state = b'KIT'
        assert p.raw_state == b'KIT'
        t = threading.Thread(target=p.show_editor); t.start(); time.sleep(0.2)
        try:
            p.raw_state
            assert False, 'state read while the window is open'
        except RuntimeError:
            pass
        t.join()
        h = host.DrumHost(); h.plugin = p; h.player = 'dawdreamer'
        assert h.sound_check(38)
        a, ring = h.ring_hit(38)
        assert a is not None and a.shape[1] == 2
    finally:
        p.close()
