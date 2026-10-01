"""Try MAME audio settings on the Pi: play a coin and the start jingle, count ALSA underruns, measure speed.

Each variant runs a clean 30 emulated seconds, so it ends by itself and prints MAME's own
"Average speed". Listen while it runs and say which variant sounded right.

    python tools/mame_audio_test.py
"""
import argparse
import re
import sys
import time

import paramiko

from controller_client import send
from probe_mame_input import run

LOG = "/tmp/ai-arcade-audio.log"
VARIANTS = [
    ("A default sound", ""),
    ("B 22050 Hz", "-samplerate 22050"),
    ("C 22050 Hz, latency 4", "-samplerate 22050 -audio_latency 4"),
    ("D 44100 Hz, latency 5", "-samplerate 44100 -audio_latency 5"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.10.155")
    parser.add_argument("--user", default="pi")
    parser.add_argument("--only", help="run just the variant whose label starts with this letter")
    args = parser.parse_args()

    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(hostname=args.host, username=args.user, timeout=10)
    try:
        for label, flags in VARIANTS:
            if args.only and not label.startswith(args.only.upper()):
                continue
            print(f"\n== {label}  (listen now)", flush=True)
            run(ssh, "pkill -9 -x mame || true")
            run(ssh, f"rm -f {LOG}")
            run(ssh, "nohup env SDL_AUDIODRIVER=alsa mame pacman -rompath /home/pi/RetroPie/roms/arcade "
                     "-video accel -nowindow -skip_gameinfo -joystick -joystickprovider sdl "
                     "-ctrlrpath /home/pi/.mame/ctrlr -ctrlr aiarcade -seconds_to_run 30 "
                     f"{flags} > {LOG} 2>&1 < /dev/null &")
            time.sleep(8)
            send(args.host, 8765, {"op": "tap", "player": 1, "action": "COIN", "ms": 200})
            time.sleep(3)
            send(args.host, 8765, {"op": "tap", "player": 1, "action": "START", "ms": 200})
            for _ in range(60):  # wait for the run to end on its own
                time.sleep(2)
                if not run(ssh, "pgrep -x mame || true").strip():
                    break
            text = run(ssh, f"cat {LOG}")
            speed = re.search(r"Average speed: ([\d.]+)%", text)
            underruns = len(re.findall(r"underrun|xrun|ALSA", text, re.IGNORECASE))
            print(f"   speed {speed.group(1) + '%' if speed else '?'}   ALSA underrun/error lines: {underruns}")
            if underruns:
                print("   sample:", [l for l in text.splitlines() if re.search(r"underrun|xrun|ALSA", l, re.I)][:2])
    finally:
        run(ssh, "pkill -9 -x mame || true")
        ssh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
