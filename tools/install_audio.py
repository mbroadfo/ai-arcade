"""Send the cabinet's sound out of the USB audio adapter (RCA to the amplifier), for every mode.

Installs pi/audio/asound.conf as /etc/asound.conf (the original is kept once as asound.conf.before-ai-arcade): the
adapter becomes ALSA's default output, found by its card name, so EmulationStation, the games people play (MAME via
runcommand) and AI mode (tools/start_pi_game.py runs MAME with SDL_AUDIODRIVER=alsa) all use it. Sets the adapter's
volume (its one control, "Headphone"), unmuted, and saves it (alsactl store) so it survives a reboot. Tells
EmulationStation to use that control for its volume setting. Plays a short test tone unless --no-tone. Safe to re-run.

    python tools/install_audio.py [--host ADDRESS] [--volume 90] [--no-tone]
"""
import argparse
import sys

import paramiko

from gamelib import DEFAULT_PI_HOST, ROOT
from probe_mame_input import run

CARD = "Audio"  # the adapter's ALSA card name (/proc/asound/cards: "KT USB Audio")
CONTROL = "Headphone"  # its only mixer control
ES_SETTINGS = "/opt/retropie/configs/all/emulationstation/es_settings.cfg"


def es_setting(ssh, name, value):
    """Set one EmulationStation string setting, creating the settings file if there is none (ES fills in the rest)."""
    line = f'<string name="{name}" value="{value}" />'
    run(ssh, f"test -f {ES_SETTINGS} || printf '<?xml version=\"1.0\"?>\\n' > {ES_SETTINGS}")
    run(ssh, f"grep -q 'name=\"{name}\"' {ES_SETTINGS} && "
             f"sed -i 's|<string name=\"{name}\" value=\"[^\"]*\" />|{line}|' {ES_SETTINGS} || "
             f"echo '{line}' >> {ES_SETTINGS}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    parser.add_argument("--volume", type=int, default=90, help="the adapter's volume, percent")
    parser.add_argument("--no-tone", action="store_true", help="skip the test tone")
    args = parser.parse_args()
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(args.host, username="pi", timeout=10)
    try:
        cards = run(ssh, "cat /proc/asound/cards")
        if f"[{CARD}" not in cards.replace(" ", ""):
            print(f"The USB audio adapter (card '{CARD}') is not plugged in or not seen:\n{cards}")
            return 1
        sftp = ssh.open_sftp()
        sftp.put(str(ROOT / "pi" / "audio" / "asound.conf"), "/tmp/ai-arcade-asound.conf")
        sftp.close()
        run(ssh, "test -e /etc/asound.conf.before-ai-arcade || sudo cp -p /etc/asound.conf /etc/asound.conf.before-ai-arcade "
                 "2>/dev/null || true")
        run(ssh, "sudo install -m 644 /tmp/ai-arcade-asound.conf /etc/asound.conf")
        run(ssh, f"amixer -c {CARD} -q sset {CONTROL} {args.volume}% unmute")
        run(ssh, "sudo alsactl store")
        es_setting(ssh, "AudioCard", "default")
        es_setting(ssh, "AudioDevice", CONTROL)
        print(run(ssh, f"amixer -c {CARD} sget {CONTROL} | tail -2").strip())
        print(run(ssh, f"grep -i audio {ES_SETTINGS}").strip())
        if not args.no_tone:
            print("Playing a test tone for 3 seconds (left, then right)...")
            print(run(ssh, "timeout 6 speaker-test -D default -c 2 -t sine -f 440 -l 1 2>&1 | grep -i -E 'front|error' "
                           "|| true").strip())
        print(f"Sound now goes to the USB adapter (card '{CARD}'). The original /etc/asound.conf is kept as "
              "/etc/asound.conf.before-ai-arcade.")
    finally:
        ssh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
