# Changelog

## 0.14
- Steven Slate Drums 5 now makes sound: it is silent in SmartKit's usual plugin player (pedalboard), so SmartKit
  runs it in a second player, DawDreamer, in a helper process (installed automatically the first time). Any
  other plugin that stays silent is tried in DawDreamer automatically. With DawDreamer the plugin window is for
  choosing the kit only (no live sound while it is open).
- Plugin window: you hear the plugin – drums clicked in its window play through the audio output chosen on
  step 3 (Windows default, or e.g. your Focusrite). The window can stay open while SmartKit is used (Find sounds
  re-reads the kit from it); close it or press the button again when the kit is chosen. Loading a plugin no
  longer freezes SmartKit's window (plugins now load on their own thread).
- After loading a kit SmartKit checks how the plugin makes sound (MIDI channel 1 or 10, fast or real-time
  playback) and uses that; no more waiting up to 3 minutes for a plugin that stays silent.
- Start window: create a new kit (name suggested) or open a saved one (newest first, with date and number
  of sounds). Also File → Open kit….
- Find sounds is instant when the kit layout is read from the plugin (Superior Drummer, EZdrummer, SSD5): the
  sounds are listed without playing them; ring time and level are measured with ▶ Play or while recording.
- Steven Slate Drums 5: the kit layout (drums, articulations, notes) is read from the plugin, like Superior
  Drummer – no scan of all 128 notes, with real names
  (Snare Rimshot, Hi-Hat Tip 2/5 Open …) and the right types, codes and hi-hat positions.
- Other plugins: the note scan tries each note once, then looks again only at the silent ones – much faster.
- Crash log (smartkit_errors.txt) is trimmed when it grows past 2 MB.

## 0.13
- New look: dark theme for dark studios (View → Light for daylight), step bar, dark title bar on Windows,
  help text that folds away (click WHAT TO DO). An `icon.ico` / `icon.png` next to the program is used as the
  window icon.
- The kit name sits in the header on every step: type to rename the kit, pick another kit from the list, or
  File → New kit. Shows how many sounds are in the kit.
- Clean up (File menu and step 5): after testing the kit on the module, move its recordings, Find-sounds test
  hits, a kit built into the project folder or the whole project to the Recycle Bin, with sizes shown.
- Levels → "Every instrument at full level, kit pads keep the plugin's mix": each instrument is raised to
  −1 dBFS and its kit pad Level is turned down by how much quieter it was in the plugin (loudest = Level 90, leaving room to turn it up on the module).
- The Strike's pad Level curve is built in, measured on a Strike Pro (fw 1.5): about 0.4 dB per step in the
  middle, Level 90 = −4.3 dB, 70 = −12.1 dB, 50 = −19.9 dB, 20 = −34.7 dB (see docs/STRIKE_FORMATS.md).
- App icon (window, taskbar and helper windows); popup menus (File / View / Help and right-click menus) drawn
  in the theme instead of Windows' light menus; "double-click to play" in the sound column heading.
- Safer names: kit, folder and file names can no longer be "." / ".." / empty or a reserved Windows name, so
  nothing is written outside the kit's folders; Clean up only works inside Projects.
- Step 5: **Record + build** records what still needs recording, then builds the kit.
- Pages scroll when the window is smaller than their content (Sources, Settings, Strike settings).
- Fixed: changing the kit name opened an empty project, so a kit made from a sample folder built nothing.
  A new kit name now renames the project and keeps its sounds, sources and recordings; Build kit explains
  when there is nothing to build.

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
