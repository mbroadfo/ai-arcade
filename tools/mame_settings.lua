-- Put every operator setting (DIP switch) in a known state at start-up: the game package's declared ones as declared,
-- all others at the factory default (MAME saves switches on exit, so a setting must never carry over from an earlier
-- run). Then reset once so the game reads them, and write every switch to /dev/shm/ai-arcade-settings.now as
-- "name=setting" lines ("! ..." for a problem). The declared settings come from /home/pi/ai-arcade/settings.lua:
-- return { {"Coinage", "Free Play"}, ... }, written by tools/start_pi_game.py from the game's SETTINGS. Any game.
local WANTED = "/home/pi/ai-arcade/settings.lua"
local NOW = "/dev/shm/ai-arcade-settings.now"
local applied = false
local frames = 0

local function apply()
    local ok, wanted = pcall(dofile, WANTED)
    if not ok or type(wanted) ~= "table" then
        wanted = {}
    end
    local declared, lines, changed, seen = {}, {}, false, {}
    for _, pair in ipairs(wanted) do
        declared[pair[1]] = pair[2]
    end
    for _, port in pairs(manager.machine.ioport.ports) do
        for name, field in pairs(port.fields) do
            if field.type_class == "dipswitch" then
                local value = field.defvalue
                if declared[name] then
                    seen[name] = true
                    value = nil
                    for v, label in pairs(field.settings) do
                        if label == declared[name] then value = v end
                    end
                    if value == nil then
                        lines[#lines + 1] = "! " .. name .. ": no setting called " .. declared[name]
                        value = field.defvalue
                    end
                end
                if field.user_value ~= value then
                    field.user_value = value
                    changed = true
                end
                lines[#lines + 1] = name .. "=" .. tostring(field.settings[field.user_value])
                    .. (declared[name] and "" or " (default)")
            end
        end
    end
    for name, _ in pairs(declared) do
        if not seen[name] then lines[#lines + 1] = "! no switch called " .. name end
    end
    table.sort(lines)
    local f = io.open(NOW, "w")
    if f then
        f:write(table.concat(lines, "\n") .. "\n")
        f:close()
    end
    return changed
end

settings_frame_sub = emu.register_frame(function()
    frames = frames + 1
    if not applied and frames >= 2 then
        applied = true
        if apply() then
            manager.machine:soft_reset()  -- many games read their switches only at power-on
        end
    end
end)
