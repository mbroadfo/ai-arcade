-- Write which input fields are active (pressed) to /tmp/ai-arcade-inputs.txt every 6 frames, one line per write:
-- "frame name|name|...". Lets a controller mapping be checked from outside without looking at the screen.
local OUT = "/tmp/ai-arcade-inputs.txt"
local count = 0
local function active()
    local names = {}
    for _, port in pairs(manager.machine.ioport.ports) do
        local value = port:read()
        for _, field in pairs(port.fields) do
            if field.type_class ~= "dipswitch" and field.type_class ~= "config"
                    and (value & field.mask) ~= (field.defvalue & field.mask) then
                names[#names + 1] = field.name
            end
        end
    end
    table.sort(names)
    return table.concat(names, "|")
end
inputs_probe_sub = emu.register_frame(function()
    count = count + 1
    if count % 6 == 0 then
        local f = io.open(OUT, "w")
        if f then
            f:write(count .. " " .. active() .. "\n")
            f:close()
        end
    end
end)
