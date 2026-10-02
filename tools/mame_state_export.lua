-- Generic game-state exporter for standalone MAME.
-- Reads /home/pi/ai-arcade/regions.lua: { {start, end [, every [, cpu [, space]]]}, ... } where `every` is how many
-- frames between refreshes of that region (default 1), and cpu/space name the MAME device and address space it is
-- read from (default ":maincpu" and "program"). Slow-changing regions (e.g. the maze) can be refreshed rarely, which
-- keeps per-frame work small on a Pi.
-- Publishes a 4-byte little-endian frame counter followed by every region's latest bytes,
-- concatenated in list order, to /dev/shm/ai-arcade-state.bin (atomic rename).

-- MAME 0.206 has methods (manager:machine(), machine:system()); 0.227 and later have properties (manager.machine).
-- get() reads either way, so this runs on the Pi 3 (0.206) and the Pi 5 (0.251).
local function get(obj, name)
  local v = obj[name]
  if type(v) == "function" then return v(obj) end
  return v
end
local on_frame = emu.add_machine_frame_notifier or emu.register_frame

local REGIONS_FILE = "/home/pi/ai-arcade/regions.lua"
local OUT_FILE = "/dev/shm/ai-arcade-state.bin"
local TMP_FILE = OUT_FILE .. ".tmp"

local regions = dofile(REGIONS_FILE)
local spaces = {}
for i, r in ipairs(regions) do
  local cpu, space = r[4] or ":maincpu", r[5] or "program"
  spaces[i] = get(manager, "machine").devices[cpu].spaces[space]
end

local function u32le(n)
  return string.char(n & 0xff, (n >> 8) & 0xff, (n >> 16) & 0xff, (n >> 24) & 0xff)
end

local function read_region(i, r)
  local mem, bytes = spaces[i], {}
  for addr = r[1], r[2] do bytes[#bytes + 1] = string.char(mem:read_u8(addr)) end
  return table.concat(bytes)
end

local cache = {}
local frame = 0
FRAME_NOTIFIER = on_frame(function()  -- kept global: newer MAME drops a notifier that is garbage-collected
  frame = frame + 1
  local chunks = { u32le(frame) }
  for i, r in ipairs(regions) do
    if cache[i] == nil or frame % (r[3] or 1) == 0 then cache[i] = read_region(i, r) end
    chunks[#chunks + 1] = cache[i]
  end
  local f = io.open(TMP_FILE, "wb")
  f:write(table.concat(chunks))
  f:close()
  os.rename(TMP_FILE, OUT_FILE)
end)
