#!/bin/bash
# RetroPie runs this before every game (/opt/retropie/configs/all/runcommand-onstart.sh; args: system emulator rom command).
# For a RetroArch core: give any gamepad plugged in a RetroArch layout and write who is Player 1..4 to
# /dev/shm/ai-arcade-pads.cfg, which RetroArch's global config includes (pad_map.py --ra). Any other emulator: empty file.
: > /dev/shm/ai-arcade-pads.cfg
case "$2" in lr-*) python3 /home/pi/ai-arcade/mame_human/pad_map.py --ra > /dev/null 2>&1 ;; esac
exit 0
