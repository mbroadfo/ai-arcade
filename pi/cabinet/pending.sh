#!/bin/bash
# Run a game the Observatory asked for, before EmulationStation starts (the autostart hook; pi/cabinet/cabinet.py).
# The request is two lines, system and ROM path, written by cabinet.py launch after it checked both. Used once.
# A gamepad EmulationStation has not met gets the standard layout (pi/mame_human/pad_map.py --es): whatever is plugged in works.
python3 /home/pi/ai-arcade/mame_human/pad_map.py --es > /dev/null 2>&1
REQUEST=/dev/shm/ai-arcade-launch
[ -f "$REQUEST" ] || exit 0
{ read -r system; read -r rom; } < "$REQUEST"
rm -f "$REQUEST"
[ -n "$system" ] && [ -f "$rom" ] || exit 0
/opt/retropie/supplementary/runcommand/runcommand.sh 0 _SYS_ "$system" "$rom"
