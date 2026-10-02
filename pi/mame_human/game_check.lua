-- Watches one game during an automatic check (pi/mame_human/game_check.py), inside MAME 0.251 via -autoboot_script.
-- Facts only: when the coin and start inputs reach the game, how much of the screen changes after each, the emulation
-- speed, and screenshots at each step (for a person, or Claude, to look at). The checker decides what they mean.
-- Writes lines to $CHECK_LOG; screenshots go to the snapshot directory the checker passes.

local log = io.open(os.getenv("CHECK_LOG") or "/tmp/game_check.log", "w")
local function out(...) log:write(table.concat({...}, " "), "\n"); log:flush() end

local machine = manager.machine
local ioport = machine.ioport
local screen
for _, s in pairs(machine.screens) do screen = s; break end
local COIN = ioport:token_to_input_type("COIN1")
local START = ioport:token_to_input_type("START1")

-- A coarse fingerprint of the screen: every 37th pixel's bytes.
local function sample()
  if not screen then return nil end
  local ok, pixels = pcall(function() return screen:pixels() end)
  if not ok or not pixels then return nil end
  local t, step = {}, 4 * 37
  for i = 1, #pixels - 3, step do t[#t + 1] = pixels:byte(i + 1) * 65536 + pixels:byte(i + 2) * 256 + pixels:byte(i + 3) end
  return t
end
local function changed(a, b)
  if not a or not b or #a ~= #b or #a == 0 then return -1 end
  local n = 0
  for i = 1, #a do if a[i] ~= b[i] then n = n + 1 end end
  return n / #a
end
local function snap(name) if screen then pcall(function() screen:snapshot(name .. ".png") end) end end

out("START", machine.system.name, machine.system.description)
local frame, coin_at, start_at = 0, nil, nil
local was_coin, was_start = false, false
local idle_a, before_coin, at_start

FRAME_HOOK = (emu.add_machine_frame_notifier or emu.register_frame)(function()
  frame = frame + 1
  if frame % 30 == 0 then
    local ok, speed = pcall(function() return machine.video.speed_percent end)
    out("FRAME", frame, ok and string.format("%.1f", speed * 100) or "?")  -- speed_percent is a ratio (1.0 = full)
  end
  if frame == 420 then idle_a = sample() end
  if frame == 540 then out("IDLE_CHANGE", string.format("%.3f", changed(idle_a, sample()))) end

  local coin = ioport:type_pressed(COIN, 0)
  if coin and not was_coin and not coin_at then
    coin_at = frame; before_coin = sample(); snap("1-before-coin"); out("COIN_SEEN", frame)
  end
  was_coin = coin
  if coin_at and frame == coin_at + 120 then
    out("COIN_CHANGE", string.format("%.3f", changed(before_coin, sample()))); snap("2-after-coin")
  end

  local start = ioport:type_pressed(START, 0)
  if start and not was_start and not start_at then
    start_at = frame; at_start = sample(); out("START_SEEN", frame)
  end
  was_start = start
  if start_at and frame == start_at + 240 then
    out("START_CHANGE", string.format("%.3f", changed(at_start, sample()))); snap("3-after-start")
  end
end)

EXIT_HOOK = (emu.add_machine_stop_notifier or emu.register_stop)(function() out("STOP", frame) end)
