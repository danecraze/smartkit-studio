# Changelog

## 0.12
- Sample sources – no plugin or recording needed: sample folders (converter names and plain pack names,
  left/right pairs, 44.1/96 kHz → 48 kHz), SFZ, Decent Sampler, Hydrogen kits, Strike instruments (`.sin`,
  hi-hats split into pedal positions) and long recordings cut into hits. Mix them with plugin sounds.
- Right-click a sample sound → Code (5 letters).

## 0.11
- Instrument folders `Instruments/<kit>/<TYPE>/…` (KICK, SNARE, TOM, HIHAT, CRASH, RIDE, SPLASH, CHINA, STACK,
  PERC) as default.
- Compressed sounds: detects where loudness stops rising, keeps ~⅓ of the velocity layers for the hard hits,
  maps zones to the source velocities and optionally gives back the loudness steps.

## 0.10
- Type-first 5-letter codes (`SNRHD`, `HHBO1`, `CRSED` …); hi-hat sample files carry their own articulation code.

## 0.9
- Articulation codes checked against Toontrack's key maps; type folders; settings save/load;
  "Instruments only"; sample files named with instrument, pedal position, velocity and take.

## 0.8
- Reads the plugin's e-drum MIDI map and plays each sound with a note that really reaches it.
- Leaves out articulations switched off in the plugin; factory splash byte; per-instrument gain option;
  default amp/pitch/filter/velocity and kit FX; done notification.

## 0.5 – 0.7
- 5-letter codes and real drum names from the Toontrack sound database, File menu, presets, memory
  priorities and mono/stereo per type, faster plugin start, log files.

## 0.1 – 0.4
- First versions: plugin host, recording, memory planner, `.sin` / `.skt` writer, hi-hat building.
