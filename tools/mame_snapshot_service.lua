-- On-demand RAM snapshot service for standalone MAME (used by tools/discover_state.py).
-- Reads /home/pi/ai-arcade/regions.lua ({ {start,end}, ... }). When /dev/shm/ai-arcade-snap.req
-- exists, deletes it and publishes the regions (4-byte LE sequence number first) to
-- /dev/shm/ai-arcade-snap.bin via atomic rename. Idle cost per frame: one failed io.open.

local REQ = "/dev/shm/ai-arcade-snap.req"
local OUT = "/dev/shm/ai-arcade-snap.bin"
local TMP = OUT .. ".tmp"

local regions = dofile("/home/pi/ai-arcade/regions.lua")
local mem = manager:machine().devices[":maincpu"].spaces["program"]
local seq = 0

local function u32le(n)
  return string.char(n & 0xff, (n >> 8) & 0xff, (n >> 16) & 0xff, (n >> 24) & 0xff)
end

emu.register_frame(function()
  local req = io.open(REQ, "rb")
  if not req then return end
  req:close()
  os.remove(REQ)
  seq = seq + 1
  local chunks = { u32le(seq) }
  for _, r in ipairs(regions) do
    local bytes = {}
    for addr = r[1], r[2] do bytes[#bytes + 1] = string.char(mem:read_u8(addr)) end
    chunks[#chunks + 1] = table.concat(bytes)
  end
  local f = io.open(TMP, "wb")
  f:write(table.concat(chunks))
  f:close()
  os.rename(TMP, OUT)
end)
