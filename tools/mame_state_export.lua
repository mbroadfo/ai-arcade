-- Generic game-state exporter for standalone MAME.
-- Reads /home/pi/ai-arcade/regions.lua: { {start, end [, every]}, ... } where `every` is how many
-- frames between refreshes of that region (default 1). Slow-changing regions (e.g. the maze) can
-- be refreshed rarely, which keeps per-frame work small on a Pi.
-- Publishes a 4-byte little-endian frame counter followed by every region's latest bytes,
-- concatenated in list order, to /dev/shm/ai-arcade-state.bin (atomic rename).

local REGIONS_FILE = "/home/pi/ai-arcade/regions.lua"
local OUT_FILE = "/dev/shm/ai-arcade-state.bin"
local TMP_FILE = OUT_FILE .. ".tmp"

local regions = dofile(REGIONS_FILE)
local mem = manager:machine().devices[":maincpu"].spaces["program"]

local function u32le(n)
  return string.char(n & 0xff, (n >> 8) & 0xff, (n >> 16) & 0xff, (n >> 24) & 0xff)
end

local function read_region(r)
  local bytes = {}
  for addr = r[1], r[2] do bytes[#bytes + 1] = string.char(mem:read_u8(addr)) end
  return table.concat(bytes)
end

local cache = {}
local frame = 0
emu.register_frame(function()
  frame = frame + 1
  local chunks = { u32le(frame) }
  for i, r in ipairs(regions) do
    if cache[i] == nil or frame % (r[3] or 1) == 0 then cache[i] = read_region(r) end
    chunks[#chunks + 1] = cache[i]
  end
  local f = io.open(TMP_FILE, "wb")
  f:write(table.concat(chunks))
  f:close()
  os.rename(TMP_FILE, OUT_FILE)
end)
