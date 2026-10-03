-- Video exporter for standalone MAME: the game's own pixels for the Observatory (the dashboard on the PC), not for
-- the decider, which reads the state exporter. Runs beside mame_state_export.lua (both are loaded by autoboot.lua).
-- Every AI_ARCADE_VIDEO_EVERY frames (default 4: 15 a second at 60 Hz) it writes the first screen's bitmap to
-- /dev/shm/ai-arcade-frame.bin (atomic rename):
--   4 bytes  frame counter, little-endian (as in the state file, so the same server code can publish it)
--   2 bytes  width, 2 bytes height, little-endian (the unrotated bitmap, e.g. 288 x 224 for Pac-Man)
--   2 bytes  quarter turns clockwise that make it upright (the machine's orientation: rot90 = 1)
--   width * height * 4 bytes  pixels, B G R X per pixel, rows top to bottom
-- On a Pi 5 a Pac-Man capture costs about 0.4 ms (measured 2026-10-02), so 15 a second does not slow the game.
-- A vector game (Battlezone) draws nothing into the screen bitmap: its frames come from MAME's rendered snapshot
-- instead (video:snapshot_pixels, already upright, 640 x 480: about 6 ms a capture on a Pi 5, measured 2026-10-03,
-- with the game still at full speed).
-- pi/frame_server.py streams it to the PC (port 8767).

local function get(obj, name)  -- methods on MAME 0.206, properties on 0.227 and later
  local v = obj[name]
  if type(v) == "function" then return v(obj) end
  return v
end
local on_frame = emu.add_machine_frame_notifier or emu.register_frame

local OUT_FILE = "/dev/shm/ai-arcade-frame.bin"
local TMP_FILE = OUT_FILE .. ".tmp"
local EVERY = tonumber(os.getenv("AI_ARCADE_VIDEO_EVERY") or "") or 4
local TURNS = { rot0 = 0, rot90 = 1, rot180 = 2, rot270 = 3 }

local machine = get(manager, "machine")
local screen
for _, s in pairs(machine.screens) do screen = s; break end
local turns = TURNS[tostring(get(machine.system, "orientation"))] or 0
local vector = screen ~= nil and tostring(get(screen, "screen_type")) == "vector"

local function capture()
  if vector then
    local video = get(machine, "video")
    local width, height = video:snapshot_size()
    return video:snapshot_pixels(), width, height, 0  -- the snapshot is rendered upright
  end
  local pixels, width, height = screen:pixels()
  return pixels, width, height, turns
end

local function u16le(n) return string.char(n & 0xff, (n >> 8) & 0xff) end
local function u32le(n) return string.char(n & 0xff, (n >> 8) & 0xff, (n >> 16) & 0xff, (n >> 24) & 0xff) end

local frame = 0
VIDEO_NOTIFIER = on_frame(function()  -- kept global: newer MAME drops a notifier that is garbage-collected
  frame = frame + 1
  if not screen or frame % EVERY ~= 0 then return end
  local ok, pixels, width, height, quarter = pcall(capture)
  if not ok or not pixels or not width then return end
  local f = io.open(TMP_FILE, "wb")
  f:write(u32le(frame), u16le(width), u16le(height), u16le(quarter), pixels)
  f:close()
  os.rename(TMP_FILE, OUT_FILE)
end)
