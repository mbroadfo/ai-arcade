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
exec mame -inipath "$CONFIG" "${set:-$game}" "$@"
