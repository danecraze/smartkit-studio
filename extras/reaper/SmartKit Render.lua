--[[
  SmartKit Render  (REAPER ReaScript, Lua)          v0.1 – untested on a real REAPER yet
  ---------------------------------------------------------------------------------------
  Records every sound of the drum VST on the selected track (e.g. Superior Drummer 3)
  so the SmartKit converter can build a Strike kit from it.

  How to use
    1. In REAPER: put Superior Drummer 3 on a track, load your kit, select that track.
       (Turn off SD3's Humanize / velocity randomising so each velocity is exact.)
    2. Actions > Show action list > New action > Load ReaScript... > pick this file > Run.
    3. Answer the questions (defaults are fine). Press OK.

  What it does
    Pass 1 (probe): plays every MIDI note once at velocity 127 and listens which notes
                    make a sound and how long each one rings.
    Pass 2 (render): for every note that made a sound it plays a velocity ladder
                    (e.g. 127,123,...,3) x N repeats (round robins), spaced so each hit can
                    ring out, and renders one WAV per note:  "<out folder>\N036.wav".
    The converter splits those WAVs into single hits, so nothing else is needed here.
]]

local function msg(s) reaper.ShowConsoleMsg(tostring(s) .. "\n") end

local track = reaper.GetSelectedTrack(0, 0)
if not track then
  reaper.ShowMessageBox("Select the track that has Superior Drummer (or another drum VST) on it first.", "SmartKit Render", 0)
  return
end

local defaults = "0-119,4,3,C:\\Users\\Dane\\Documents\\Claude\\Drums\\SmartKit Renders"
local ok, answer = reaper.GetUserInputs("SmartKit Render", 4,
  "MIDI notes (e.g. 0-119 or 36 38 40),Velocity step (1 = all 127),Repeats per velocity (round robins),Output folder,extrawidth=320",
  defaults)
if not ok then return end
local notes_s, step_s, reps_s, outdir = answer:match("([^,]+),([^,]+),([^,]+),(.+)")
local vstep, reps = tonumber(step_s) or 4, tonumber(reps_s) or 3

local notes = {}
for part in notes_s:gmatch("[^;%s]+") do
  for a, b in part:gmatch("(%d+)%-(%d+)") do for n = tonumber(a), tonumber(b) do notes[#notes + 1] = n end end
  if not part:find("-") then for n in part:gmatch("%d+") do notes[#notes + 1] = tonumber(n) end end
end
reaper.RecursiveCreateDirectory(outdir, 0)

------------------------------------------------------------------ helpers
local function clear_items()
  for i = reaper.CountTrackMediaItems(track) - 1, 0, -1 do
    reaper.DeleteTrackMediaItem(track, reaper.GetTrackMediaItem(track, i))
  end
end

local function clear_regions()
  local _, nm, nr = reaper.CountProjectMarkers(0)
  for i = nm + nr - 1, 0, -1 do
    local _, isrgn, _, _, _, idx = reaper.EnumProjectMarkers(i)
    if isrgn then reaper.DeleteProjectMarker(0, idx, true) end
  end
end

-- one MIDI item with hits = list of {time, velocity}
local function add_hits(note, t0, hits, len)
  local item = reaper.CreateNewMIDIItemInProj(track, t0, t0 + len, false)
  local take = reaper.GetActiveTake(item)
  for _, h in ipairs(hits) do
    local p0 = reaper.MIDI_GetPPQPosFromProjTime(take, t0 + h[1])
    local p1 = reaper.MIDI_GetPPQPosFromProjTime(take, t0 + h[1] + 0.05)
    reaper.MIDI_InsertNote(take, false, false, p0, p1, 0, note, h[2], true)
  end
  reaper.MIDI_Sort(take)
  return item
end

local function render_regions(folder, pattern)
  reaper.GetSetProjectInfo_String(0, "RENDER_FILE", folder, true)
  reaper.GetSetProjectInfo_String(0, "RENDER_PATTERN", pattern, true)
  reaper.GetSetProjectInfo_String(0, "RENDER_FORMAT", "ZXZhdyAAAA==", true)  -- WAV, 32-bit float
  reaper.GetSetProjectInfo(0, "RENDER_SETTINGS", 0, true)       -- master mix
  reaper.GetSetProjectInfo(0, "RENDER_BOUNDSFLAG", 3, true)     -- all project regions
  reaper.GetSetProjectInfo(0, "RENDER_SRATE", 44100, true)
  reaper.GetSetProjectInfo(0, "RENDER_CHANNELS", 2, true)
  reaper.GetSetProjectInfo(0, "RENDER_TAILFLAG", 0, true)
  reaper.Main_OnCommand(42230, 0)  -- File: Render project, using the most recent render settings, auto-close dialog
end

-- read a rendered WAV back and measure: peak and seconds until it falls 60 dB below that peak
local function measure(path)
  local src = reaper.PCM_Source_CreateFromFile(path)
  if not src then return nil end
  local sr = reaper.GetMediaSourceSampleRate(src)
  local len = reaper.GetMediaSourceLength(src)
  local item = reaper.AddMediaItemToTrack(track)
  local take = reaper.AddTakeToMediaItem(item)
  reaper.SetMediaItemTake_Source(take, src)
  reaper.SetMediaItemInfo_Value(item, "D_LENGTH", len)
  local acc = reaper.CreateTakeAudioAccessor(take)
  local block = 4410  -- 0.1 s
  local buf = reaper.new_array(block * 2)
  local env = {}
  local t = 0
  while t < len do
    buf.clear()
    reaper.GetAudioAccessorSamples(acc, sr, 2, t, block, buf)
    local pk = 0
    for i = 1, block * 2 do local v = math.abs(buf[i]); if v > pk then pk = v end end
    env[#env + 1] = pk
    t = t + block / sr
  end
  reaper.DestroyAudioAccessor(acc)
  reaper.DeleteTrackMediaItem(track, item)
  return env
end

------------------------------------------------------------------ pass 1: probe
local PROBE_SLOT = 12.0   -- seconds per note in the probe (long enough for a crash to die away)
reaper.Undo_BeginBlock()
reaper.PreventUIRefresh(1)
clear_items(); clear_regions()
for i, n in ipairs(notes) do
  local t0 = (i - 1) * PROBE_SLOT
  add_hits(n, t0, {{0.5, 127}}, PROBE_SLOT)
end
local total = #notes * PROBE_SLOT
reaper.AddProjectMarker2(0, true, 0, total, "probe", -1, 0)
reaper.PreventUIRefresh(-1)
render_regions(outdir, "_probe")

local env = measure(outdir .. "\\_probe.wav")
if not env then
  reaper.ShowMessageBox("Could not read the probe render. Check the output folder.", "SmartKit Render", 0)
  return
end

local found = {}
local per = math.floor(PROBE_SLOT / 0.1 + 0.5)
for i, n in ipairs(notes) do
  local pk, last = 0, 0
  for k = 1, per do local v = env[(i - 1) * per + k] or 0; if v > pk then pk = v end end
  if pk > 0.001 then  -- louder than -60 dBFS: this note plays something
    for k = 1, per do if (env[(i - 1) * per + k] or 0) > pk * 0.001 then last = k end end
    local ring = math.max(1.5, last * 0.1)   -- seconds from the hit (at 0.5 s) to -60 dB, plus 0.5 s margin
    found[#found + 1] = {note = n, ring = math.min(ring, 20)}
  end
end
msg(("SmartKit: %d of %d notes make a sound."):format(#found, #notes))

------------------------------------------------------------------ pass 2: render every sounding note
local vels = {}
for v = 127, 1, -vstep do vels[#vels + 1] = v end
if vels[#vels] ~= 1 then vels[#vels + 1] = 1 end

reaper.PreventUIRefresh(1)
clear_items(); clear_regions()
local t = 0
local list = io.open(outdir .. "\\_notes.csv", "w")
list:write("note,file,ring_seconds,velocities,repeats\n")
for _, f in ipairs(found) do
  local hits, x = {}, 0.5
  for _, v in ipairs(vels) do
    for r = 1, reps do hits[#hits + 1] = {x, v}; x = x + f.ring end
  end
  local len = x + 0.5
  add_hits(f.note, t, hits, len)
  local name = ("N%03d"):format(f.note)
  reaper.AddProjectMarker2(0, true, t, t + len, name, -1, 0)
  list:write(("%d,%s.wav,%.1f,%s,%d\n"):format(f.note, name, f.ring, table.concat(vels, " "), reps))
  t = t + len + 1.0
end
list:close()
reaper.PreventUIRefresh(-1)
reaper.UpdateArrange()
render_regions(outdir, "$region")
reaper.Undo_EndBlock("SmartKit Render", -1)
reaper.ShowMessageBox(("Done. %d notes rendered to\n%s\n\nNext: run SmartKit on that folder."):format(#found, outdir), "SmartKit Render", 0)
