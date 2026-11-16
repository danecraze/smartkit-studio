"""End-to-end: sample library -> sounds -> memory plan -> Strike files."""
import glob, os, types
import numpy as np
import pytest
import sources, smartkit as SK, strikefmt as SF
from plan import Artic, find_compression, expand_compressed


def opts(out, **kw):
    o = types.SimpleNamespace(out=out, kit='Test Kit', budget=20.0, template=None, curve=1.0, vel_level=0,
                              hat_closed_from=127, gain='unity', include_all=False, auto_pads=False, pads_b={},
                              extras=[], extra_mb=0, levels='instrument', fill_empty=True, folders='nested',
                              comp_db=8, comp_restore=True, pad_notes={})
    o.__dict__.update(kw)
    return o


def test_scan_converter_library(converter_library):
    snds = sources.scan_any(converter_library, log=lambda *a: None)
    codes = sorted(s['sfx'] for s in snds)
    assert codes == sorted(['KCKHD', 'SNRHD', 'SNRRI', 'TOMHD', 'TOMHD', 'TOMHD', 'HHBCL', 'HHECL', 'HHEO1',
                            'HHEO2', 'HHPCL', 'HHPSP', 'CRSED', 'RIDBW', 'RIDBL'])
    toms = sorted((s['note'], s['base']) for s in snds if s['sfx'] == 'TOMHD')
    assert [b for _, b in toms] == ['16 Maple Tom', '12 Maple Tom', '10 Maple Tom']   # smallest = highest note
    hits = sources.load_hits(next(s for s in snds if s['sfx'] == 'SNRHD')['src'])
    assert len(hits) == 5 and all(h.sr == 48000 for h in hits)          # 44.1 kHz converted to 48 kHz
    assert sorted(h.vel for h in hits) == [15, 40, 70, 100, 127]


def test_build_kit_from_samples(converter_library, tmp_path):
    snds = sources.scan_any(converter_library, log=lambda *a: None)
    pick = {'KCKHD': 'K1H', 'SNRHD': 'S1H', 'SNRRI': 'S1R', 'CRSED': 'C1E', 'RIDBW': 'R1B', 'RIDBL': 'R1D'}
    artics, pads = [], {}
    for s in snds:
        if s['sfx'] in pick or s['sfx'] == 'TOMHD':
            hits = sources.load_hits(s['src'])
            a = Artic(sources.sd3names.fit(s['base'], s['sfx']), '', hits)
            a.role, a.n_raw, a.src_bytes = s['role'], len(hits), sources.source_bytes(s['src'])
            artics.append(a)
            pads[pick.get(s['sfx']) or {50: 'T1H', 48: 'T2H', 47: 'T3H'}[s['note']]] = a
    out = str(tmp_path / 'card')
    summary = SK.build_kit(artics, pads, opts(out), log=lambda *a: None)
    assert summary and summary['used_mib'] <= 20.0
    kits = glob.glob(os.path.join(out, 'Kits', '*.skt'))
    assert len(kits) == 1
    kit = SF.read_skt(open(kits[0], 'rb').read())
    assert len(kit['pads']) == 24
    for path in kit['paths']:                                       # every instrument the kit uses exists …
        assert path.startswith(':')
        sin = os.path.join(out, 'Instruments', *path[1:].split('/'))
        assert os.path.exists(sin), path
        inst = SF.read_sin(open(sin, 'rb').read())
        assert 0 < len(inst['zones']) <= 255
        for sp in inst['paths']:                                    # … and every sample it plays
            assert os.path.exists(os.path.join(out, 'Samples', *sp[1:].split('/'))), sp
        assert len(os.path.basename(sin)[:-4]) <= 26
    assert any('/SNARE/SNRHD_' in p for p in kit['paths'])          # Instruments/<kit>/<TYPE>/<CODE_name>


def test_compressed_sound_gets_hard_layers():
    """Loudness flat above velocity 51 (like a squashed plugin snare): ~1/3 of the layers go to the hard hits."""
    from analyse import measure
    hits = []
    for v in range(1, 128, 4):
        level = min(v, 51) / 51
        t = np.arange(4800) / 48000
        a = (level * np.exp(-t * 20) * np.sin(2 * np.pi * (200 + v) * t))[:, None].astype(np.float32)
        hits.append(measure(a, 48000, f'v{v}', v))
    a = Artic('SNRHD_test', '', hits, force_mono=True)
    knee = find_compression(a.hits)
    assert 37 <= knee <= 53
    assert expand_compressed(a, 8.0) == knee
    layers = a.select(12, 1)
    hard = [g for g in layers if g[0].vel >= knee]
    assert len(hard) >= 3
    assert [g[0].vel for g in layers] == sorted(g[0].vel for g in layers)


@pytest.mark.parametrize('kind', ['sfz', 'hydrogen'])
def test_sampler_files(tmp_path, kind):
    from conftest import write_wav
    for v in (40, 127):
        write_wav(str(tmp_path / 's' / f'snare_v{v}.wav'), amp=v / 127)
        write_wav(str(tmp_path / 's' / f'snare_oh_v{v}.wav'), amp=v / 254, ch=2)
    if kind == 'sfz':
        (tmp_path / 'kit.sfz').write_text(
            '<control> default_path=s/\n<group> key=38\n<region> sample=snare_v40.wav hivel=40\n'
            '<region> sample=snare_v127.wav lovel=41\n<group> key=38\n<region> sample=snare_oh_v40.wav hivel=40\n'
            '<region> sample=snare_oh_v127.wav lovel=41\n')
        snds = sources.scan_any(str(tmp_path / 'kit.sfz'), log=lambda *a: None)
    else:
        (tmp_path / 'drumkit.xml').write_text(
            '<drumkit_info><name>T</name><instrumentList><instrument><name>Snare</name>'
            '<layer><filename>s/snare_v40.wav</filename><min>0</min><max>0.3</max></layer>'
            '<layer><filename>s/snare_v127.wav</filename><min>0.3</min><max>1</max></layer>'
            '</instrument></instrumentList></drumkit_info>')
        snds = sources.scan_any(str(tmp_path), log=lambda *a: None)
    assert len(snds) == 1 and snds[0]['sfx'] == 'SNRHD'
    hits = sources.load_hits(snds[0]['src'])
    assert len(hits) == 2
    if kind == 'sfz':
        assert all(h.a.shape[1] == 2 for h in hits)                 # close mic + stereo overhead mixed
