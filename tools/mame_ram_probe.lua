-- Proves Lua access to the Pac-Man Z80 address space and logs working-RAM changes.
-- Runs inside standalone MAME via -autoboot_script. Writes to /tmp/ai-arcade-ram.log.

local log = io.open("/tmp/ai-arcade-ram.log", "w")
local function out(msg)
  log:write(msg .. "\n")
  log:flush()
end

local cpu = manager:machine().devices[":maincpu"]
local mem = cpu.spaces["program"]
out("maincpu space ok; 0x4C00 = " .. string.format("%02X", mem:read_u8(0x4C00)))

local WORK_LO, WORK_HI = 0x4C00, 0x4FFF
local VID_LO, VID_HI = 0x4000, 0x47FF

local prev = {}
for a = VID_LO, WORK_HI do prev[a] = mem:read_u8(a) end

local frame = 0
emu.register_frame(function()
  frame = frame + 1
  local vid_changes = 0
  for a = VID_LO, WORK_HI do
    local v = mem:read_u8(a)
    if v ~= prev[a] then
      if a >= WORK_LO then
        out(string.format("f%d %04X: %02X -> %02X", frame, a, prev[a], v))
      elseif a <= VID_HI then
        vid_changes = vid_changes + 1
      end
      prev[a] = v
    end
  end
  if vid_changes > 0 then
    out(string.format("f%d video/color RAM bytes changed: %d", frame, vid_changes))
  end
end)
