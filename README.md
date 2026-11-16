# SmartKit Studio

**Build Alesis Strike / Strike Pro kits from a drum plugin or from samples you already have.**

SmartKit Studio is a free Windows app that turns a drum VST3 kit (e.g. Superior Drummer 3, EZdrummer) or a
folder of drum samples into a ready-to-play kit for the Alesis Strike / Strike Pro drum module: instruments
(`.sin`), samples and a kit (`.skt`) written straight to the module's SD card, planned to fit the module's
200 MB sample memory with the best sound it can get.

> Not affiliated with, endorsed by or supported by Alesis, inMusic or Toontrack.
> See [Disclaimer](#disclaimer).

## Features

- **Drum plugin → Strike kit.** Hosts a VST3 drum plugin, reads the kit layout (Superior Drummer 3 /
  EZdrummer: every drum and articulation, real drum names, articulations that are switched off, the plugin's
  e-drum MIDI map), plays every articulation at every velocity and records it.
- **Your own samples → Strike kit** (no plugin, no recording):
  - sample folders (common converter naming like `14 SONOR Designer Sn 1v127.wav`, or plain pack names),
  - sampler instruments: **SFZ**, **Decent Sampler** (`.dspreset`), **Hydrogen** kits (`drumkit.xml`),
  - existing **Strike instruments** (`.sin`) – rebuilt with new names and a new memory plan,
  - long recordings (one drum played soft to loud) cut into single hits.
  Mix plugin sounds and sample sounds in one kit.
- **Memory planner.** Every sound starts small; upgrades (more velocity layers, more round robins, longer
  tails) go to whichever sound gains the most per MB, weighted by a priority per drum type, until the kit fills
  the memory you set (default 196 of 200 MB). Mono/stereo per type.
- **Compressed sounds.** Finds sounds whose loudness stops rising at hard hits (plugin compressors / limiters),
  keeps more velocity layers for the hard hits, maps zones to the source velocities and can give back the
  loudness steps.
- **Hi-hats built like factory ones.** Bow, edge and pedal instruments with the factory pedal ranges
  (closed = 127; opens 91–126 / 67–90 / 37–66 / 0–36), chick + foot splash (splash zones 7–127).
- **Clear names.** Every instrument gets a 5-letter type-first code + drum name, e.g. `SNRHD_14 SONOR Designer`,
  `HHBO1_14 Agop Trad Jazz`, `CRSED_18 Agop 30th Anniv` (see [docs/NAMING_CODES.md](docs/NAMING_CODES.md)).
  Sample files carry instrument, pedal position, velocity and take.
- **Strike settings.** Defaults per drum type for level, pan, decay, pitch, filter, velocity → level / decay /
  filter / pitch and velocity range; kit reverb, compressor and EQ; pad MIDI notes; folders per kit and type.
- **Pad assignment** suggested automatically, editable per sound (incl. "instrument only" – saved to the card
  but not placed in the kit).
- Presets, saved settings, a log per kit and a crash log.

## Requirements

- Windows 10/11 (the app is Python + Tk; the plugin host part needs Windows VST3 plugins)
- [Python 3.10+](https://www.python.org/downloads/) – tick **"Add python.exe to PATH"** when installing
- Python packages: `numpy`, and `pedalboard` for plugin hosting (installed automatically on first start)
- An Alesis Strike or Strike Pro module and its SD card (firmware 1.5 was used for testing)

## Install and start

1. Download this repository (green **Code** button → **Download ZIP**) and unzip it, e.g. to
   `Documents\SmartKit Studio`.
2. Double-click **`SmartKit Studio.bat`**. The first start installs the Python add-ons (needs internet).
3. Follow the tabs from left to right:
   1. **Sources** – load a drum plugin and pick its kit, and/or add sample folders, SFZ / Decent Sampler /
      Hydrogen files, Strike instruments or recordings.
   2. **Find sounds** – read the plugin's sounds; check type, name and Strike pad for every sound.
   3. **Settings** – velocities, takes, memory, priorities, folders, compressed sounds.
   4. **Strike settings** – amp / pitch / filter / velocity defaults per drum type, kit effects.
   5. **Record & build** – record the plugin sounds, then build the kit to a folder or straight to the SD card.

The full guide is in [USER_GUIDE.txt](USER_GUIDE.txt) (also under **Help → Read me** in the app).

Manual install (instead of the .bat):

```
python -m pip install -r requirements.txt
python smartkit_app.py
```

## What it writes

```
<SD card>/Kits/<kit>.skt
<SD card>/Instruments/<kit>/<TYPE>/<CODE_drum name>.sin      (or another folder layout, see Settings)
<SD card>/Samples/<kit>/<instrument>/<instrument> [p<pedal>] v<velocity> r<take>.wav   (48 kHz, 16-bit)
```

SmartKit asks before it writes to a drive root and only writes user content; it never touches the module's
internal (preset) drive.

## How it works (short)

| Step | File |
|---|---|
| Host the plugin, play notes, record | `host.py` |
| Read the Toontrack kit layout, names and MIDI map | `sd3state.py`, `sd3names.py` |
| Read sample folders / SFZ / Decent Sampler / Hydrogen / `.sin` | `sources.py` |
| Measure hits, split long files, read/write WAV | `analyse.py` |
| Velocity layers, round robins, tails, memory plan, compressed sounds | `plan.py` |
| Build instruments and kit | `smartkit.py` |
| Strike `.sin` / `.skt` file formats | `strikefmt.py` – see [docs/STRIKE_FORMATS.md](docs/STRIKE_FORMATS.md) |
| The app (Tk) | `smartkit_app.py` |

`smartkit.py` also works on the command line for a folder of renders (`python smartkit.py <renders> <out>`),
e.g. renders made in REAPER with [extras/reaper/SmartKit Render.lua](extras/reaper/) (untested).

## Status and known limits

- Tested on one Strike Pro (firmware 1.5) with Superior Drummer 3 and converted sample libraries.
- Kit-memory limit: the module loads every sample of a kit into a 200 MiB pool; SmartKit plans for that.
- Up to 255 zones per instrument, 26 characters per name, plain characters only (`A–Z a–z 0–9 space . _ ( ) -`).
- Two folder levels under `Instruments` (kit / type) build and load; whether the module's instrument
  browser shows the second level has not been fully confirmed – the other folder layouts are one level.
- Kontakt (`.nki`) instruments are encrypted and can't be read – use the plugin route or export samples.
- Preset (internal-drive) samples are not copied when rebuilding Strike instruments.

## Tests

```
python -m pip install numpy pytest
python -m pytest tests
```

The tests build complete kits from generated samples (no plugin, no module needed).

## Contributing

Issues and pull requests are welcome – especially reports from other Strike / Strike Pro / Strike Pro SE
firmware versions, other drum plugins and other sample-library naming schemes. Please never attach samples
you don't have the rights to share.

## Disclaimer

SmartKit Studio is an independent project. Alesis and Strike are trademarks of inMusic Brands; Superior
Drummer and EZdrummer are trademarks of Toontrack Music AB; all other names belong to their owners. The Strike
file formats were worked out independently for compatibility. No samples, firmware or factory content are
included.

Only convert sounds you are licensed to use, and check your sample library's licence: many libraries allow
use in your own music but not redistribution of the sounds. Keep the converted kits for your own use.

Use at your own risk; keep a backup of your SD card.

## Licence

[MIT](LICENSE)
