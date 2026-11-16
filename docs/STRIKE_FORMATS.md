# Alesis Strike / Strike Pro file formats

Worked out independently from factory and user files (firmware 1.5) for compatibility. "?" = not confirmed.
All numbers little-endian.

## Storage

The module has two drives: the internal drive (preset content, read-only for users) and the SD card (user
content). Over USB the computer normally sees only the SD card.

```
Kits/<name>.skt
Instruments/<folder>/<name>.sin
Samples/<any folders>/<file>.wav        48 kHz, 16-bit (factory samples are stereo)
```

Instruments and kits refer to SD-card files with a leading `:` and a path relative to `Samples/` or
`Instruments/` (`:My Kit/SNARE/SNRHD_14 Maple.sin`); internal-drive files have no `:`.
Names: at most 26 characters.

## Chunks

Both file types are a list of chunks: 4-character id, `u32` size, data, padded to a multiple of 4 bytes (the
size excludes the padding). String tables (`str `) are NUL-terminated Latin-1 strings; other chunks refer to
them by index (`0xFFFF` = none).

## Layer (20 bytes)

Used at `+4` (layer A) and `+24` (layer B) of every kit pad, and at `+4` of an instrument's `INST` header
(the instrument's default settings).

| Byte | Meaning |
|---|---|
| 0–1 | instrument / string index (`0xFFFF` = empty) |
| 2 | level 0–99 |
| 3 | pan −50…+50 (signed) |
| 4 | decay 0–99 |
| 5 | attack 0–99 |
| 7 / 8 | semitone −12…+12 / fine −50…+50 (signed) |
| 9 | filter cutoff 0–99 |
| 10 | filter type (0 low-pass, 1 high-pass) |
| 11 / 12 / 13 / 14 | velocity → decay / pitch / filter (signed) / level (0–99) |
| 15 / 16 | velocity low / high |
| 17 | loop (0 off, 1 on) |

## Instrument (`.sin`): `INST` (24) · `msmp` (4 + 28 × zones) · `str ` (sample paths)

`INST`: byte 1 = category (0 normal, 3 hi-hat), bytes 4–23 = default layer.

`msmp` header: byte 0 = cycle mode (0 round robin, 1 random), byte 2 = number of zones (max 255).

Zone (28 bytes):

| Byte | Meaning |
|---|---|
| 0–1 | sample (string index) |
| 2 | level 0–99 |
| 3 / 4 | velocity low / high |
| 5 / 6 | note range (0 / 127) |
| 7 | `0xFE` |
| 10 / 11 | hi-hat pedal range (CC4, 0 open … 127 closed) |
| 17 | splash: 0 = normal; non-zero = foot-splash zone (factory: 127 − splash start, e.g. 120 for zones 7–127) |
| 18–19 | gain (64 = unity; factory zones use 64 × 32767 / sample peak) |
| 25 | round robin: 3 = first zone of a group, 1 = following zones |

Factory hi-hat cymbals: closed = pedal 127 only; opens 91–126 / 67–90 / 37–66 / 0–36 (fewer positions merge
from the open end). Factory hi-hat pedals: chick zones 0–127, splash zones 7–127.

## Kit (`.skt`): `KIT ` (44) · 24 × `inst` (72) · `str ` (instrument paths)

`KIT ` header:

| Byte | Meaning |
|---|---|
| 2 | kit level |
| 5 / 6 / 7 | MIDI program / bank MSB / LSB |
| 8 / 9 / 10 / 11 | reverb type (255 off, else list index − 1) / size / colour / level |
| 12–23 / 24–35 | FX1 / FX2: type, level, delay L u16, delay R u16, feedback L/R, depth, rate, damp |
| 36 / 37 / 38 | compressor type (255 off) / threshold −90…0 / output −24…+24 (signed) |
| 39 / 40 / 41 / 42 | EQ low gain / low freq index / high gain / high freq index |
| 43 | EQ (0 on, 255 off) |

Pad record (`inst`, 72 bytes): `+0` pad id (`K1H K2H S1H S1R T1H…T4R H1B H1E H1F C1B C1E C2B C2E C3B C3E R1D
R1B R1E`), `+4` layer A, `+24` layer B, `+44` reverb send, `+45` FX1 send, `+46` EQ/comp on, `+47` output,
`+48` priority, `+49` mute group, `+50` mono, `+51` MIDI channel, `+52` MIDI note, `+53` gate time,
`+54` note-off mode, `+55` chord mode, `+56…+60` extra notes (255 none), `+61` FX2 send.

Compressor types in order: Master 1, Radio 1, Radio 2, Soft Hyper, Bright, Country, Crunch, Dance, Hip Hop,
Jazz, Lo Boost, Rock 1, Rock 2, Rock 3. Each type only sets an attack and a release time (the ratio is the
same for all).

## Sample memory

The firmware loads every sample of a kit into one 200 MiB pool. Each sample takes its PCM bytes plus 64 frames
of padding, rounded up to 4 bytes. When the pool is full the module shows "Kit is too large" and the samples
loaded last stay silent.
