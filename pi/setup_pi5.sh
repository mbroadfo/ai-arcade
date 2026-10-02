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
#   emulators  the extra RetroPie emulators and ports the cabinet's ROM folders use (after retropie); a module that
#              fails is reported and the rest carry on; one already installed is skipped. lr-mame2000 stands in for
#              the Pi 3's MAME4All (the same 0.37b5 ROM sets; MAME4All has no 64-bit build).
#              Then tools/migrate_pi_settings.py brings over the old cabinet's emulator choices.
#   autostart  boot straight into EmulationStation (console autologin on the screen, then ES); AI mode closes it
#              (tools/start_pi_game.py) and tools/human_mode.py brings it back
#   audio      sound through a USB audio adapter (the Pi 5 has no headphone jack): it becomes the default ALSA card
# ROMs and BIOS files are copied separately from the old cabinet (docs/PI_SETUP.md); this repository holds none.
set -eu

# RetroPie module, then the ROM folder it serves
EMULATORS="
lr-mame2000  arcade,mame-mame4all
lr-quicknes  nes
advmame      mame-advmame
sdltrs       trs-80
frotz        zmachine
alephone     ports/alephone
dxx-rebirth  ports/descent1-2
lr-prboom    ports/doom
eduke32      ports/duke3d
lr-tyrquake  ports/quake
ioquake3     ports/quake3
wolf4sdl     ports/wolf3d
cannonball   ports/cannonball
lr-mrboom    ports/mrboom
opentyrian   ports/opentyrian
"

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

step_emulators() {
    cd "$HOME/RetroPie-Setup"
    echo "$EMULATORS" | while read -r module folder; do
        [ -n "$module" ] || continue
        if ls -d /opt/retropie/*/"$module" >/dev/null 2>&1; then
            echo "=== $module already installed"
            continue
        fi
        echo "=== $module ($folder)"
        if sudo __nodialog=1 ./retropie_packages.sh "$module"; then
            echo "=== $module installed"
        else
            echo "=== $module FAILED"
        fi
    done
    echo "emulators finished; any failures are marked FAILED above"
}

step_autostart() {
    cd "$HOME/RetroPie-Setup"
    sudo __nodialog=1 ./retropie_packages.sh autostart enable
    cat /opt/retropie/configs/all/autostart.sh
    echo "EmulationStation starts at boot; to start it now without rebooting: sudo systemctl restart getty@tty1"
}

step_audio() {
    card=$(sed -n 's/^ *[0-9]* \[\([^ ]*\) *\]: USB-Audio.*/\1/p' /proc/asound/cards | head -n 1)
    if [ -z "$card" ]; then
        echo "no USB audio adapter found; plug it in and run this step again" >&2
        cat /proc/asound/cards >&2
        exit 1
    fi
    printf 'defaults.pcm.card %s\ndefaults.ctl.card %s\n' "$card" "$card" | sudo tee /etc/asound.conf
    for control in PCM Speaker Headphone; do
        amixer -q -c "$card" sset "$control" 90% unmute 2>/dev/null || true
    done
    echo "default sound card is now $card; test with: speaker-test -c 2 -t sine -l 1"
}

case "${1:-}" in
    mame) step_mame ;;
    retropie) step_retropie ;;
    emulators) step_emulators ;;
    autostart) step_autostart ;;
    audio) step_audio ;;
    *) echo "usage: $0 mame|retropie|emulators|autostart|audio" >&2; exit 2 ;;
esac
