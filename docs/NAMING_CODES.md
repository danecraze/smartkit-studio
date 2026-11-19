# Names and codes

Every Strike instrument SmartKit writes is named `<CODE>_<drum name>` (max 26 plain characters), e.g.
`SNRHD_14 SONOR Designer`. The 5-letter code is **instrument type first, then the articulation**.

## Type (first 3 letters)

Toms and cymbals carry their number, so a kit's toms and crashes sit together, in order, in the module's
instrument list (`TM1HD`, `TM1RI`, `TM2HD` … `CR1ED`, `CR1BW`, `CR2ED` …).

| Code | Type | Code | Type |
|---|---|---|---|
| `KCK` | kick | `CR1`…`CR9` | crash 1 … |
| `SNR` | snare | `RD1`, `RD2` | ride 1, 2 |
| `TM1`…`TM9` | tom 1 … (1 = highest) | `SP1`… | splash |
| `HH` + surface | hi-hat (`HHB` bow, `HHE` edge, `HHL` bell, `HHP` pedal) | `CN1`… | china |
| `PRC` | percussion / other | `ST1`… | stack |

(Before SmartKit 0.16 these were `TOM`, `CRS`, `RID`, `SPL`, `CHN`, `STK` without a number. The tables below
still use those internal codes; the number is added when the instrument is named. Strike instruments with
either kind of name are read back correctly.)

## Articulation (last 2 letters)

| Drums | | Cymbals | |
|---|---|---|---|
| `HD` | head / center | `ED` | crashed (edge) |
| `RI` | rimshot | `BW` | bow tip |
| `RO` | rim only | `SH` | bow shank |
| `XS` | cross-stick / sidestick | `BL` | bell |
| `MC` | mid center | `BT` | bell tip |
| `FL` | flam | `MU` | muted |
| `RF` | ruffs | `CH` | choke |
| `LH` | left hand | `FX` / `TL` | FX / tail |
| `MU` | muted | | |
| `OP`, `HB` | kick open / beater stays | | |

Hi-hat: `HHBCL` bow closed · `HHBTT` bow tight · `HHBO1`…`HHBO6` bow open 1–6 · `HHECL` edge closed ·
`HHETT` edge tight · `HHEMN` edge open min · `HHEO1`…`HHEO6` edge open · `HHLCL` / `HHLO1`… bell ·
`HHPCL` pedal chick · `HHPSP` pedal foot splash.

Whole hi-hat instruments built from several articulations: `HHBOW`, `HHEDG`, `HHPED`; their sample files keep
each articulation's own code (`HHBO1_14 Agop Trad Jazz p067 v100 r1.wav`).

Two sounds combined on one pad: the type once, then both articulations (`SNRHDMU`). The same name twice gets
a number (`TOMHD2_…`).

## Superior Drummer 3 / EZdrummer articulation codes

Read from the plugin's kit state (meanings checked against Toontrack's own key maps):

| Toontrack | Code | Toontrack | Code |
|---|---|---|---|
| snare `R` | `SNRHD` | hats `TP` closed tip | `HHBCL` |
| snare `FX` | `SNRRI` | hats `TT` tight tip | `HHBTT` |
| snare `RO` | `SNRRO` | hats `T1`…`T6` open tip | `HHBO1`… |
| snare `SL` / `SS` | `SNRXS` | hats `CL` closed edge | `HHECL` |
| snare `MC` | `SNRMC` | hats `CT` tight edge | `HHETT` |
| snare `RF` / `FL` | `SNRRF` / `SNRFL` | hats `LO` open min | `HHEMN` |
| tom `R` / `FX` | `TOMHD` / `TOMRI` | hats `O1`…`O6` open edge | `HHEO1`… |
| kick `R` | `KCKHD` | hats `PL` / `PLO` | `HHPCL` / `HHPSP` |
| cymbal (none) crashed | `CRSED` | cymbal `RT` bow tip | `CRSBW` |
| cymbal `FR` bow shank | `CRSSH` | cymbal `BL` bell shank | `CRSBL` |
| ride (none) bow tip | `RIDBW` | ride `PU` crashed | `RIDED` |

## Sample files from converters

Sample folders named the way common drum converters name them are read exactly:
`<drum>_<mic-mix id> <CODE> <number>[v<velocity>].wav`, e.g. `14 SABIAN AAX Studio Hats_Z8 HEO4 28v30.wav`
(number 1 = loudest).

| Converter | Code | Converter | Code |
|---|---|---|---|
| `K` | `KCKHD` | `HBC` / `HBT` / `HBO1-5` | `HHBCL` / `HHBTT` / `HHBO1…` |
| `Sn` | `SNRHD` | `HEC` / `HET` / `HEO1-5` | `HHECL` / `HHETT` / `HHEO1…` |
| `SnR` | `SNRRI` | `HCH` or `HP` | `HHPCL` |
| `SnSS`, `XS` | `SNRXS` | `HSP` or `HF` | `HHPSP` |
| `T1`…`T9` / `T1R` | `TOMHD` / `TOMRI` | `Ri1` / `Ri1B` / `Ri1E` | `RIDBW` / `RIDBL` / `RIDED` |
| `C1E`, `Cr1E` | `CRSED` | `C1`, `Cr1` | `CRSBW` |
| `Ch1E` | `CHNED` | `Sp1E` | `SPLED` |
| `P1` | `PRCHT` | | |

Other sample packs are read by the words in folder and file names (kick, snare, rim, side, tom, hat, closed,
open 2, pedal, foot, crash, ride, bell, china, splash, choke …); `1-2.1` style numbers mean drum-layer.take and
`…01L` / `…01R` pairs become one stereo sample. Wrong guesses can be fixed in the app (right-click a sound →
Code).

## Sample file names written by SmartKit

`<CODE_drum name> [p<pedal start>][s] v<top velocity> r<take>.wav`, e.g.
`SNRHD_14 SONOR Designer v104 r2.wav`, `HHPSP_14 Agop Trad Jazz p007s v127 r1.wav`.
