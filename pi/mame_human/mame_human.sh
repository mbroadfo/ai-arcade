#!/bin/sh
# EmulationStation's launcher for standalone MAME 0.251 in human mode: mame_human.sh <rom name> [extra MAME options]
#
# The rom name is the zip's name in ~/RetroPie/roms/arcade. A game whose zip was rebuilt for 0.251 under another name
# (an older revision, say asteroid -> asteroid2) is listed in sets.tsv, "zip name<TAB>0.251 name"; anything else runs
# under its own name.
CONFIG=/opt/retropie/configs/mame-0251
game="$1"
shift
set=$(awk -F '\t' -v g="$game" '$1 == g { print $2; exit }' "$CONFIG/sets.tsv" 2>/dev/null)
# Sound goes through ALSA, whose default device is the USB audio adapter (pi/audio/asound.conf), as in AI mode
# (tools/start_pi_game.py): without this SDL picks its own audio driver from whatever the login session offers.
# Controls adapt to whatever is plugged in (pad_map.py): the panel, any gamepad, the keyboard; the AI pads are hidden.
# If it cannot run, mame.ini's own controller file (the panel's) applies.
PAD_ARGS=
eval "$(python3 "$(dirname "$0")/pad_map.py" 2>/dev/null)"
# shellcheck disable=SC2086
exec env SDL_AUDIODRIVER=alsa mame -inipath "$CONFIG" $PAD_ARGS "${set:-$game}" "$@"
