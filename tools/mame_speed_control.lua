-- Game speed for AI mode, changeable while the game runs (the Observatory's slider; pi/cabinet/cabinet.py speed).
-- Twice a second it reads /dev/shm/ai-arcade-speed (a number: 1.0 = full speed, 0.85 = 85 %) and sets MAME's throttle
-- rate to it; /dev/shm/ai-arcade-speed.now says the rate in force. The player measures the speed it actually gets
-- (tools/play.py logs every change), so a run's results always say how fast the game ran. Runs beside the exporters.

local REQUEST, NOW = "/dev/shm/ai-arcade-speed", "/dev/shm/ai-arcade-speed.now"
local MIN, MAX = 0.2, 1.0

local machine = manager.machine
local frame, applied = 0, nil

local function apply()
  local f = io.open(REQUEST, "r")
  if not f then return end
  local value = tonumber(f:read("*l") or "")
  f:close()
  if not value then return end
  value = math.max(MIN, math.min(MAX, value))
  if value ~= applied then
    machine.video.throttle_rate = value
    applied = value
    local out = io.open(NOW, "w")
    out:write(string.format("%.3f\n", value))
    out:close()
  end
end

SPEED_NOTIFIER = (emu.add_machine_frame_notifier or emu.register_frame)(function()  -- global: kept alive
  frame = frame + 1
  if frame % 30 == 1 then pcall(apply) end
end)
