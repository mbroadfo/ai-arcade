-- Reports which MAME input tokens fire while physical controls are pressed.
-- Runs inside standalone MAME (0.206 or later) via -autoboot_script. Writes to /tmp/ai-arcade-probe.log.

local log = io.open("/tmp/ai-arcade-probe.log", "w")
local function out(msg)
  log:write(msg .. "\n")
  log:flush()
end

-- MAME 0.206 has methods (manager:machine(), machine:system()); 0.227 and later have properties (manager.machine).
-- get() reads either way, so this runs on the Pi 3 (0.206) and the Pi 5 (0.251).
local function get(obj, name)
  local v = obj[name]
  if type(v) == "function" then return v(obj) end
  return v
end
local on_frame = emu.add_machine_frame_notifier or emu.register_frame

local machine = get(manager, "machine")
local input = get(machine, "input")
out("probe loaded; machine=" .. get(machine, "system").name)

local tokens = {}
for joy = 1, 2 do
  for b = 1, 16 do
    tokens[#tokens + 1] = string.format("JOYCODE_%d_BUTTON%d", joy, b)
  end
  for _, name in ipairs({ "SELECT", "START",
                          "XAXIS_LEFT_SWITCH", "XAXIS_RIGHT_SWITCH",
                          "YAXIS_UP_SWITCH", "YAXIS_DOWN_SWITCH" }) do
    tokens[#tokens + 1] = string.format("JOYCODE_%d_%s", joy, name)
  end
end

local seqs = {}
for _, token in ipairs(tokens) do
  local ok, seq = pcall(function() return input:seq_from_tokens(token) end)
  if ok and seq then
    seqs[#seqs + 1] = { token = token, seq = seq }
  else
    out("cannot parse token: " .. token .. " (" .. tostring(seq) .. ")")
  end
end
out("tracking " .. #seqs .. " tokens; press controls now")

local was_down = {}
FRAME_NOTIFIER = on_frame(function()  -- kept global: newer MAME drops a notifier that is garbage-collected
  for _, entry in ipairs(seqs) do
    local down = input:seq_pressed(entry.seq)
    if down ~= (was_down[entry.token] or false) then
      was_down[entry.token] = down
      out(string.format("%s %s  (MAME name: %s)",
        down and "DOWN" or "UP  ", entry.token, input:seq_name(entry.seq)))
    end
  end
end)
