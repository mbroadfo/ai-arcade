"""Does EmulationStation obey the panel? Drive it with the pretend panel (tools/synth_panel.py) and compare with the
AI Arcade broker's pads, which are known to work.

Each trial restarts EmulationStation (so it starts from the same place), sends a short sequence of presses, and looks at
which game EmulationStation launched (runcommand's command line). The same sequence is sent once through the broker's
virtual pad (the baseline) and once through the pretend panel; the panel passes when it launches the same game.

    python tools/check_es_panel.py [--host ADDRESS] [--only NAME ...]

Restarts EmulationStation and starts (then ends) games on the Pi: do not run it while someone is playing.
Names: A is accept, B back, RIGHT/LEFT/UP/DOWN move, STAR is page up, SNOWFLAKE page down.
"""
import argparse
import re
import sys
import time

import paramiko

from controller_client import send
from gamelib import DEFAULT_PI_HOST
from probe_mame_input import run
from synth_panel import SynthPanel

BROKER = {"A": "BUTTON_1", "B": "BUTTON_2", "STAR": "BUTTON_5", "SNOWFLAKE": "BUTTON_6",
          "RIGHT": "RIGHT", "LEFT": "LEFT", "UP": "UP", "DOWN": "DOWN"}
SEQUENCES = {
    "open and launch": ["A", "A"],
    "right, open, launch": ["RIGHT", "A", "A"],
    "down in the list": ["A", "DOWN", "A"],
    "right then left cancel": ["RIGHT", "LEFT", "A", "A"],
    "down then up cancel": ["A", "DOWN", "UP", "A"],
    "back out of a list": ["A", "B", "RIGHT", "A", "A"],
    "page down": ["A", "SNOWFLAKE", "A"],
    "page down then up": ["A", "SNOWFLAKE", "STAR", "A"],
}
GAP = 1.4  # seconds between presses: EmulationStation animates its transitions


def restart_es(ssh):
    run(ssh, "sudo systemctl restart getty@tty1")
    run(ssh, "timeout 20 sh -c \"until pgrep -f '/emulationstation$' >/dev/null; do sleep 0.5; done\"")
    time.sleep(14)  # it loads the game lists before it takes input


def launched(ssh, wait=9):
    """The game EmulationStation launched, as 'system/rom', or 'nothing'."""
    end = time.time() + wait
    while time.time() < end:
        out = run(ssh, "ps -eo args | grep 'runcommand.sh' | grep -v grep | head -1")
        m = re.search(r"runcommand\.sh \d+ _SYS_ (\S+) (.+)$", out.strip())
        if m:
            return f"{m.group(1)}/{m.group(2).rsplit('/', 1)[-1]}"
        time.sleep(0.7)
    return "nothing"


def via_broker(host, names):
    for name in names:
        send(host, 8765, {"op": "tap", "player": 1, "action": BROKER[name], "ms": 150})
        time.sleep(GAP)


def via_panel(panel, names, player="P1"):
    for name in names:
        panel.press(player, name)
        time.sleep(GAP)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    parser.add_argument("--only", nargs="*", help="run only these sequences (names as in SEQUENCES)")
    args = parser.parse_args()
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(args.host, username="pi", timeout=10)
    results = []
    try:
        with SynthPanel(ssh) as panel:
            for title, names in SEQUENCES.items():
                if args.only and title not in args.only:
                    continue
                restart_es(ssh)
                via_broker(args.host, names)
                base = launched(ssh)
                restart_es(ssh)
                via_panel(panel, names)
                got = launched(ssh)
                results.append((title, names, base, got))
                print(f"{title:<26} baseline: {base:<34} panel: {got:<34} {'OK' if base == got and base != 'nothing' else 'DIFFERENT'}",
                      flush=True)
        restart_es(ssh)  # leave EmulationStation fresh, not a game
    finally:
        ssh.close()
    bad = [r for r in results if r[2] != r[3] or r[2] == "nothing"]
    print(f"\n{len(results) - len(bad)} of {len(results)} sequences match the broker's pads.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
