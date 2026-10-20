-- Watches what MAME makes of the panel: lists its joysticks in the order it numbers them (JOYCODE_1, 2, ...), writes how
-- it reads the controller file for the controls it was asked about, and logs every change of those input fields, of the
-- menu and of pause, with the frame number. Used by tools/check_mame_panel.py; changes nothing in the game.
--
--   /tmp/panel-watch-names.txt   input field names to watch, one per line ("P1 Button 1", "Coin 1", ...)
--   /tmp/panel-watch.log         the output, tab separated: J (joystick), Q (a field's sequence), F (field changed),
--                                S (state: ready, menu, paused), E (error)

local machine = manager.machine
local log = io.open("/tmp/panel-watch.log", "w")
local function out(line) log:write(line .. "\n"); log:flush() end

local watch, fields, last = {}, {}, {}
local f = io.open("/tmp/panel-watch-names.txt", "r")
if f then for l in f:lines() do if l ~= "" then watch[l] = true end end f:close() end

local frame, ready, last_menu, last_pause = 0, false, nil, nil

local function setup()
  local ok, err = pcall(function()
    local input = machine.input
    local i = 0
    for _, dev in pairs(input.device_classes["joystick"].devices) do
      i = i + 1
      out(string.format("J\t%d\t%s", i, tostring(dev.name)))
    end
    for _, port in pairs(machine.ioport.ports) do
      for name, field in pairs(port.fields) do
        if watch[name] then
          fields[#fields + 1] = {name = name, port = port, field = field}
          last[name] = false
          local okq, text = pcall(function() return input:seq_name(field:input_seq("standard")) end)
          out(string.format("Q\t%s\t%s", name, okq and tostring(text) or "?"))
          out("W\t" .. name)
        end
      end
    end
    out("F\tfields\t" .. #fields)
  end)
  if not ok then out("E\tsetup\t" .. tostring(err)) end
end

local function pressed(item)
  local mask = item.field.mask
  return (item.port:read() & mask) ~= (item.field.defvalue & mask)
end

local notify = emu.add_machine_frame_notifier or emu.register_frame_done or emu.register_frame
PANEL_WATCH = notify(function()
  frame = frame + 1
  if frame == 20 and not ready then ready = true; setup(); out("S\t20\tready\t1") end
  if not ready then return end
  for _, item in ipairs(fields) do
    local okp, now = pcall(pressed, item)
    if okp and now ~= last[item.name] then
      last[item.name] = now
      out(string.format("F\t%d\t%s\t%d", frame, item.name, now and 1 or 0))
    end
  end
  local okm, menu = pcall(function() return manager.ui.menu_active end)
  if okm and menu ~= last_menu then last_menu = menu; out(string.format("S\t%d\tmenu\t%s", frame, tostring(menu))) end
  local paused = machine.paused
  if paused ~= last_pause then last_pause = paused; out(string.format("S\t%d\tpaused\t%s", frame, tostring(paused))) end
end)
