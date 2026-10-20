-- per game: how many of Player 2's input fields are cocktail-only, and is there a Cabinet dipswitch
local machine = manager.machine
local notify = emu.add_machine_frame_notifier or emu.register_frame_done or emu.register_frame
local frames = 0
notify(function()
  frames = frames + 1
  if frames == 20 then
    local p2, cock, real, cab, p3 = 0, 0, 0, "no", 0
    for tag, port in pairs(machine.ioport.ports) do
      for name, field in pairs(port.fields) do
        local ok, pl = pcall(function() return field.player end)
        local okt, ty = pcall(function() return field.type_class end)
        if name:lower():find("cabinet") then cab = "yes" end
        if ok and pl == 1 and (name:find("^P2") or name:find("Joystick") or name:find("Button") or name:find("Dial") or name:find("Paddle") or name:find("Track") or name:find("Stick") or name:find("Pedal") or name:find("Up$") or name:find("Down$") or name:find("Left$") or name:find("Right$")) and not name:find("Start") and not name:find("Coin") then
          p2 = p2 + 1
          if field.cocktail then cock = cock + 1 else real = real + 1 end
        end
        if ok and pl == 2 then p3 = p3 + 1 end
      end
    end
    print(string.format("TURNS p2=%d cocktail=%d real=%d cabinet_dip=%s p3=%d", p2, cock, real, cab, p3))
  end
end)
