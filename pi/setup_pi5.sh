#!/bin/sh
# One-time setup of a Raspberry Pi 5 (Raspberry Pi OS Bookworm Lite, 64-bit) as the AI Arcade cabinet.
# Everything this does to the system is in this file (README: persistent changes are captured in automation).
#
#   scp pi/setup_pi5.sh pi@<pi>:~ && ssh pi@<pi> 'sh ~/setup_pi5.sh mame'       # minutes
#   ssh pi@<pi> 'nohup sh ~/setup_pi5.sh retropie > ~/setup_retropie.log 2>&1 &'  # an hour or more (builds from source)
#
# Steps (each can be run on its own, and again):
#   mame       standalone MAME from Raspberry Pi OS (0.251 on Bookworm), for AI mode (tools/start_pi_game.py)
#   retropie   RetroPie-Setup's basic install: EmulationStation and RetroArch, for human mode
# ROMs and BIOS files are copied separately from the old cabinet (docs/PI_SETUP.md); this repository holds none.
set -eu

step_mame() {
    sudo apt-get update
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y mame git python3-evdev
    mame -version
}

step_retropie() {
    [ -d "$HOME/RetroPie-Setup" ] || git clone --depth=1 https://github.com/RetroPie/RetroPie-Setup.git "$HOME/RetroPie-Setup"
    cd "$HOME/RetroPie-Setup"
    git pull --ff-only || true
    sudo __nodialog=1 ./retropie_packages.sh setup basic_install
    echo "retropie basic install finished"
}

case "${1:-}" in
    mame) step_mame ;;
    retropie) step_retropie ;;
    *) echo "usage: $0 mame|retropie" >&2; exit 2 ;;
esac
