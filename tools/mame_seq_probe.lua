-- Lists every input field of the loaded game with the keys and joystick codes assigned to it (what MAME's Tab menu,
-- Input Assignments (this system), shows). Writes to /tmp/ai-arcade-seqs.log.
local log = io.open("/tmp/ai-arcade-seqs.log", "w")
local machine = manager.machine
local input = machine.input
local rows = {}
for tag, port in pairs(machine.ioport.ports) do
  for name, field in pairs(port.fields) do
    local ok, seq = pcall(function() return input:seq_name(field:input_seq("standard")) end)
    rows[#rows + 1] = string.format("%s\t%s\t%s", tag, name, ok and seq or "?")
  end
end
table.sort(rows)
for _, r in ipairs(rows) do log:write(r .. "\n") end
log:write("done\n")
log:close()
