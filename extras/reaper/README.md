# SmartKit Render (REAPER script) – experimental

An older, untested way to record a drum plugin: a REAPER ReaScript that plays every note of the drum plugin on
the selected track and renders one WAV per note plus `_notes.csv`. Build a kit from that folder with

```
python smartkit.py <renders folder> <output folder or SD card> --kit "My Kit"
```

SmartKit Studio (`smartkit_app.py`) hosts the plugin itself and is the recommended way.
