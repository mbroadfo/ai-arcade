-- Generic game-state exporter for standalone MAME.
-- Reads the regions listed in /home/pi/ai-arcade/regions.lua (returns { {start, end}, ... })
-- from :maincpu program space every frame and publishes them, concatenated, to
-- /dev/shm/ai-arcade-state.bin (atomic rename) with a 4-byte little-endian frame counter first.

local REGIONS_FILE = "/home/pi/ai-arcade/regions.lua"
local OUT_FILE = "/dev/shm/ai-arcade-state.bin"
local TMP_FILE = OUT_FILE .. ".tmp"

local regions = dofile(REGIONS_FILE)
local mem = manager:machine().devices[":maincpu"].spaces["program"]

local function u32le(n)
  return string.char(n & 0xff, (n >> 8) & 0xff, (n >> 16) & 0xff, (n >> 24) & 0xff)
end

local frame = 0
emu.register_frame(function()
  frame = frame + 1
  local chunks = { u32le(frame) }
  for _, r in ipairs(regions) do
    local bytes = {}
    for addr = r[1], r[2] do bytes[#bytes + 1] = string.char(mem:read_u8(addr)) end
    chunks[#chunks + 1] = table.concat(bytes)
  end
  local f = io.open(TMP_FILE, "wb")
  f:write(table.concat(chunks))
  f:close()
  os.rename(TMP_FILE, OUT_FILE)
end)
