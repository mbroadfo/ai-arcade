-- Enumerates every input port/field MAME defines for the loaded game.
-- Generic across ROMs: lets us learn a game's real controls without guessing.
-- Writes tab-separated rows to /tmp/ai-arcade-ports.log.

local log = io.open("/tmp/ai-arcade-ports.log", "w")
local function out(msg) log:write(msg .. "\n"); log:flush() end

local function attr(obj, name)
  local ok, v = pcall(function() return obj[name] end)
  if ok and v ~= nil then return tostring(v) end
  return "?"
end

local machine = manager:machine()
out("game\t" .. machine:system().name .. "\t" .. machine:system().description)

local ports = machine:ioport().ports
for port_tag, port in pairs(ports) do
  for field_name, field in pairs(port.fields) do
    out(string.format("field\t%s\t%s\ttype=%s player=%s analog=%s joy=%s way=%s mask=%s",
      port_tag, field_name, attr(field, "type"), attr(field, "player"),
      attr(field, "is_analog"), attr(field, "is_digital_joystick"),
      attr(field, "way"), attr(field, "mask")))
  end
end
out("done")
