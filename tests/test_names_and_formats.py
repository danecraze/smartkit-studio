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
