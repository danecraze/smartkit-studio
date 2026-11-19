"""Alesis Strike / Strike Pro file formats (.sin instrument, .skt kit).

Byte layouts were worked out independently from factory and user files for compatibility
(see docs/STRIKE_FORMATS.md).

Chunk = 4-char id + u32 LE size + data, data padded to 4 bytes (size excludes padding).
"""
import struct

# ---------------------------------------------------------------- chunks
def read_chunks(b):
    out, o = [], 0
    while o + 8 <= len(b):
        cid = b[o:o + 4].decode('latin1')
        n = struct.unpack('<I', b[o + 4:o + 8])[0]
        out.append((cid, bytes(b[o + 8:o + 8 + n])))
        o += 8 + n + ((4 - n % 4) % 4)
    return out


def write_chunks(chunks):
    b = bytearray()
    for cid, data in chunks:
        b += cid.encode('latin1') + struct.pack('<I', len(data)) + data
        b += b'\0' * ((4 - len(data) % 4) % 4)
    return bytes(b)


def build_strs(strs):
    if not strs:
        return b''
    return b''.join(s.encode('latin1') + b'\0' for s in strs)


def parse_strs(d):
    return [s.decode('latin1') for s in d.split(b'\0') if s]


# ---------------------------------------------------------------- layer (20 bytes)
def layer_bytes(index=0xFFFF, level=99, pan=0, decay=98, attack=0, semitone=0, fine=0,
                cutoff=99, filt=0, vel_decay=0, vel_tune=0, vel_filter=0, vel_level=0,
                vel_lo=0, vel_hi=127, loop=0):
    b = bytearray(20)
    struct.pack_into('<H', b, 0, index)
    b[2] = level; b[3] = pan & 255; b[4] = decay; b[5] = attack
    b[7] = semitone & 255; b[8] = fine & 255; b[9] = cutoff; b[10] = filt
    b[11] = vel_decay & 255; b[12] = vel_tune & 255; b[13] = vel_filter & 255
    b[14] = vel_level; b[15] = vel_lo; b[16] = vel_hi; b[17] = loop
    return bytes(b)


# ---------------------------------------------------------------- instrument (.sin)
CAT_NORMAL, CAT_HIHAT = 0, 3


def make_zone(sample_index, vel_lo, vel_hi, first_of_group=True, gain=64,
              pedal_lo=0, pedal_hi=127, splash=0, level=99):
    """28-byte zone record. Constant bytes copied from SDSE/factory files.
    +0 u16 sample, +2 level, +3/+4 velocity, +5/+6 note range (0..127),
    +7 0xFE, +10/+11 hi-hat pedal range, +17 splash flag, +18 u16 gain (64 = unity),
    +25 3 = first zone of a round-robin group, 1 = following zones."""
    z = bytearray(28)
    struct.pack_into('<H', z, 0, sample_index)
    z[2] = level; z[3] = vel_lo; z[4] = vel_hi
    z[5] = 0; z[6] = 0x7F; z[7] = 0xFE
    z[10] = pedal_lo; z[11] = pedal_hi
    z[17] = splash
    struct.pack_into('<H', z, 18, max(1, min(65535, int(gain))))
    z[25] = 3 if first_of_group else 1
    return bytes(z)


def write_sin(zones, sample_paths, category=CAT_NORMAL, defaults=None, msmp_flags=0):
    """zones: list of 28-byte records; sample_paths: list of ':Lib/x.wav' strings."""
    head = bytearray(24)
    head[1] = category; head[2] = 1
    head[4:24] = defaults or layer_bytes(index=0, level=90, decay=98, vel_level=0)
    if len(zones) > 255:
        raise ValueError('Strike instruments hold at most 255 zones')
    msmp = bytearray(4)
    msmp[2] = len(zones); msmp[3] = msmp_flags
    for z in zones:
        msmp += z
    return write_chunks([('INST', bytes(head)), ('msmp', bytes(msmp)), ('str ', build_strs(sample_paths))])


def read_sin(b):
    ch = dict(read_chunks(b))
    m = ch['msmp']; n = m[2]
    zones = [m[4 + 28 * i:4 + 28 * (i + 1)] for i in range(n)]
    return {'header': ch['INST'], 'zones': zones, 'paths': parse_strs(ch.get('str ', b''))}


# ---------------------------------------------------------------- kit (.skt)
PAD_IDS = ['K1H', 'K2H', 'S1H', 'S1R', 'T1H', 'T1R', 'T2H', 'T2R', 'T3H', 'T3R', 'T4H', 'T4R',
           'H1B', 'H1E', 'H1F', 'C1B', 'C1E', 'C2B', 'C2E', 'C3B', 'C3E', 'R1D', 'R1B', 'R1E']


def write_skt_from_template(template, assign, layer_kw=None, default_layer=None, assign_b=None,
                            header_patch=None, pad_patch=None, layer_kw_b=None):
    """template: bytes of an existing .skt (header, pad order, pad settings are kept).
    assign / assign_b: {pad_id: instrument path ':Lib/name.sin'} for layer A / layer B; other pads emptied.
    layer_kw / layer_kw_b: layer settings per pad (level, decay …); layer B falls back to layer A's."""
    layer_kw = layer_kw or {}
    layer_kw_b = layer_kw_b or {}
    chunks = read_chunks(template)
    strs, out = [], []
    for cid, d in chunks:
        if cid == 'KIT ' and header_patch:
            d = bytearray(d)
            for o, v in header_patch.items():          # kit level / reverb / compressor / EQ (offsets in the 44 bytes)
                if o in (14, 16, 26, 28):               # u16 delay times
                    struct.pack_into('<H', d, o, int(v) & 0xFFFF)
                else:
                    d[o] = int(v) & 255
            out.append((cid, bytes(d)))
            continue
        if cid == 'inst':
            d = bytearray(d)
            pid = d[:3].decode('latin1')
            for o, v in ((pad_patch or {}).get(pid) or {}).items():   # reverb send, MIDI note … (+44..+61)
                d[o] = int(v) & 255
            path = assign.get(pid)
            if path:
                if path not in strs:
                    strs.append(path)
                kw = dict(default_layer or {}); kw.update(layer_kw.get(pid, {}))
                d[4:24] = layer_bytes(index=strs.index(path), **kw)
            else:
                d[4:24] = layer_bytes(index=0xFFFF, level=90)
            pb = (assign_b or {}).get(pid)
            if pb:
                if pb not in strs:
                    strs.append(pb)
                kw = dict(default_layer or {}); kw.update(layer_kw_b.get(pid, layer_kw.get(pid, {})))
                d[24:44] = layer_bytes(index=strs.index(pb), **kw)
            else:
                d[24:44] = layer_bytes(index=0xFFFF, level=90)
            out.append((cid, bytes(d)))
        elif cid == 'str ':
            continue
        else:
            out.append((cid, d))
    out.append(('str ', build_strs(strs)))
    return write_chunks(out)


def read_skt(b):
    pads, strs, head = {}, [], None
    for cid, d in read_chunks(b):
        if cid == 'KIT ':
            head = d
        elif cid == 'inst':
            pads[d[:3].decode('latin1')] = (struct.unpack('<H', d[4:6])[0], struct.unpack('<H', d[24:26])[0], d)
        elif cid == 'str ':
            strs = parse_strs(d)
    return {'header': head, 'pads': pads, 'paths': strs}


# ---------------------------------------------------------------- RAM cost (firmware 0x2179D8)
def sample_ram_bytes(frames, channels, bytes_per_sample=2):
    n = frames * channels * bytes_per_sample + channels * bytes_per_sample * 64
    return (n + 3) & ~3


POOL_BYTES = 209_715_200  # 200 MiB sample pool
