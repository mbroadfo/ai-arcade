#!/bin/bash
# RetroPie runs this before every game (/opt/retropie/configs/all/runcommand-onstart.sh; args: system emulator rom command).
# For a RetroArch core: give any gamepad plugged in a RetroArch layout, and set who is Player 1..4 (pad_map.py --ra).
case "$2" in lr-*) python3 /home/pi/ai-arcade/mame_human/pad_map.py --ra > /dev/null 2>&1 ;; esac
exit 0
