-- Lists main CPU program-space map entries (RAM/ROM/IO) so RAM regions can be found per game.
local log = io.open("/tmp/ai-arcade-map.log", "w")
local function out(m) log:write(m .. "\n"); log:flush() end
local function attr(o, n) local ok, v = pcall(function() return o[n] end); return ok and tostring(v) or "?" end
local space = manager:machine().devices[":maincpu"].spaces["program"]
out("space name=" .. attr(space, "name") .. " addr_width=" .. attr(space, "address_mask"))
local ok, map = pcall(function() return space.map end)
out("map ok=" .. tostring(ok) .. " type=" .. type(map))
if ok and map then
  local ok2, entries = pcall(function() return map.entries end)
  out("entries ok=" .. tostring(ok2))
  if ok2 and entries then
    for k, e in pairs(entries) do
      out(string.format("entry[" .. tostring(k) .. "] %s-%s read=%s write=%s mask=%s",
        attr(e, "address_start"), attr(e, "address_end"), attr(e, "read"), attr(e, "write"), attr(e, "mask")))
    end
  end
end
out("done")
