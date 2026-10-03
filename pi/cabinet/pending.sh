#!/bin/bash
# Run a game the Observatory asked for, before EmulationStation starts (the autostart hook; pi/cabinet/cabinet.py).
# The request is two lines, system and ROM path, written by cabinet.py launch after it checked both. Used once.
REQUEST=/dev/shm/ai-arcade-launch
[ -f "$REQUEST" ] || exit 0
{ read -r system; read -r rom; } < "$REQUEST"
rm -f "$REQUEST"
[ -n "$system" ] && [ -f "$rom" ] || exit 0
/opt/retropie/supplementary/runcommand/runcommand.sh 0 _SYS_ "$system" "$rom"
