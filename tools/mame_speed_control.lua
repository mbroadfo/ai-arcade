-- Game speed for AI mode, changeable while the game runs (the Observatory's slider; pi/cabinet/cabinet.py speed).
-- Twice a second it reads /dev/shm/ai-arcade-speed (a number: 1.0 = full speed, 0.85 = 85 %) and sets MAME's throttle
-- rate to it; /dev/shm/ai-arcade-speed.now says the rate in force. The player measures the speed it actually gets
-- (tools/play.py logs every change), so a run's results always say how fast the game ran. Runs beside the exporters.
-- Pause too: /dev/shm/ai-arcade-pause holding 1 pauses the machine, 0 (or no file) runs it; /dev/shm/ai-arcade-pause.now
-- says which is in force. A paused machine runs no frames, so that is read from a periodic callback, not a frame one.

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

local PAUSE, PAUSE_NOW = "/dev/shm/ai-arcade-pause", "/dev/shm/ai-arcade-pause.now"
local calls, paused, last_error = 0, nil, nil

local function apply_pause()
  local f = io.open(PAUSE, "r")
  local want = false
  if f then want = (f:read("*l") or "") == "1"; f:close() end
  if want ~= paused then
    if want then emu.pause() else emu.unpause() end  -- MAME 0.251: emu.pause/unpause (the machine has no such methods)
    paused = want
    local out = io.open(PAUSE_NOW, "w")
    out:write(want and "1\n" or "0\n")
    out:close()
  end
end

if emu.register_periodic then
  PAUSE_NOTIFIER = emu.register_periodic(function()  -- global: kept alive; called many times a second, paused or not
    calls = calls + 1
    if calls % 10 == 1 then
      local ok, err = pcall(apply_pause)
      if not ok and err ~= last_error then  -- said once, in MAME's log
        last_error = err
        print("pause control: " .. tostring(err))
      end
    end
  end)
end

SPEED_NOTIFIER = (emu.add_machine_frame_notifier or emu.register_frame)(function()  -- global: kept alive
  frame = frame + 1
  if frame % 30 == 1 then pcall(apply) end
end)
