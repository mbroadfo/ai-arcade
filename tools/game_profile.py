"""Build a machine-readable profile for any MAME romset, with no per-game hand work.

Combines three automatic sources into games/<system>/<romset>/profile.json:
  1. Controls: MAME's own port enumeration (tools/mame_ports_probe.lua) mapped to the
     broker's canonical controls.
  2. Score/high-score RAM: MAME's hiscore.dat (addresses MAME itself uses to persist scores).
  3. Named variables (lives, energy, timers...): the community cheat.dat database.

Usage: python tools/game_profile.py pacman [--system arcade]
"""
import argparse
import json
import re
import time
from pathlib import Path

import paramiko

from probe_mame_input import run
from gamelib import DEFAULT_PI_HOST

PI_HISCORE = "/usr/share/games/mame/plugins/hiscore/hiscore.dat"
PI_CHEAT = "/opt/retropie/libretrocores/lr-mame2003/metadata/cheat.dat"
PI_ROMS = "/home/pi/RetroPie/roms"
PORTS_LUA = "mame_ports_probe.lua"
PORTS_LOG = "/tmp/ai-arcade-ports.log"

PROFILES_DIR = Path(__file__).resolve().parent.parent / "games"


def parse_hiscore(text, romset):
    """hiscore.dat groups romset names ('pacman:' lines) above '@:cpu,space,addr,len,..' lines."""
    entries, names, in_names = [], [], False
    for raw in text.splitlines():
        line = raw.split(";")[0].strip()
        if not line:
            continue
        if line.startswith("@") or re.match(r"^[0-9a-fA-F]+,", line):
            if in_names:
                in_names = False
            if romset in names:
                m = re.match(r"@?:?([\w:]*),(\w+),([0-9a-fA-F]+),([0-9a-fA-F]+)", line)
                if m:
                    entries.append({"cpu": m.group(1) or ":maincpu", "space": m.group(2),
                                    "address": int(m.group(3), 16), "length": int(m.group(4), 16)})
        elif line.endswith(":"):
            if not in_names:
                names, in_names = [], True
            names.append(line[:-1])
    return entries


def parse_cheat(text, romset):
    """cheat.dat rows: romset:cpu:address:value:flags:description (address 0000 rows are menu text)."""
    found = []
    for line in text.splitlines():
        parts = line.split(":", 5)
        if len(parts) == 6 and parts[0] == romset and parts[2] != "0000":
            found.append({"cpu": int(parts[1], 16), "address": int(parts[2], 16),
                          "value": int(parts[3], 16), "description": parts[5].strip()})
    return found


def canonical_control(name):
    """Map a MAME field name to the broker's canonical control, or None."""
    m = re.match(r"^P(\d) (Up|Down|Left|Right)$", name)
    if m:
        return int(m.group(1)), m.group(2).upper()
    m = re.match(r"^P(\d) Button (\d)$", name)
    if m:
        return int(m.group(1)), f"BUTTON_{m.group(2)}"
    return None


def parse_ports(log_text):
    controls, analog, other, shared = {}, [], [], {}
    game = ""
    for line in log_text.splitlines():
        cols = line.split("\t")
        if cols[0] == "game":
            game = cols[2]
        elif cols[0] == "field":
            name, attrs = cols[2], cols[3]
            if "analog=true" in attrs:
                analog.append(name)
                continue
            slot = re.match(r"^Coin (\d)$", name)
            start = re.match(r"^(\d) Players? Start$", name)
            canon = canonical_control(name)
            if slot:
                shared.setdefault("coin_slots", []).append(int(slot.group(1)))
            elif start:
                shared.setdefault("start_buttons", []).append(int(start.group(1)))
            elif canon:
                controls.setdefault(f"player{canon[0]}", []).append(canon[1])
            else:
                other.append(name)
    for key in controls:
        controls[key] = sorted(set(controls[key]))
    controls.update({k: sorted(set(v)) for k, v in shared.items()})
    return game, controls, analog, other


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("romset")
    parser.add_argument("--system", default="arcade", help="EmulationStation system folder (arcade, nes, ...)")
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    parser.add_argument("--user", default="pi")
    args = parser.parse_args()

    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(hostname=args.host, username=args.user, timeout=10)
    try:
        sftp = ssh.open_sftp()
        hiscore = sftp.open(PI_HISCORE).read().decode("latin-1")
        cheat = sftp.open(PI_CHEAT).read().decode("latin-1")
        run(ssh, "mkdir -p /home/pi/ai-arcade")
        sftp.put(str(Path(__file__).with_name(PORTS_LUA)), f"/home/pi/ai-arcade/{PORTS_LUA}")
        sftp.close()

        run(ssh, "pkill -9 -x mame || true")
        run(ssh, f"rm -f {PORTS_LOG}")
        run(ssh, f"nohup mame {args.romset} -rompath {PI_ROMS}/{args.system} -sound none -video accel "
                 f"-nowindow -skip_gameinfo -autoboot_script /home/pi/ai-arcade/{PORTS_LUA} "
                 "> /tmp/ai-arcade-mame.log 2>&1 < /dev/null &")
        ports_text = ""
        for _ in range(40):
            time.sleep(1)
            ports_text = run(ssh, f"cat {PORTS_LOG} 2>/dev/null || true")
            if ports_text.rstrip().endswith("done"):
                break
        else:
            raise RuntimeError("ports probe never finished; see /tmp/ai-arcade-mame.log on the Pi")
        run(ssh, "pkill -9 -x mame || true")
    finally:
        ssh.close()

    game, controls, analog, other = parse_ports(ports_text)
    profile = {
        "romset": args.romset,
        "description": game,
        "controls": controls,
        "analog_inputs": analog,
        "other_inputs": other,
        "score_ram": parse_hiscore(hiscore, args.romset),
        "named_ram": parse_cheat(cheat, args.romset),
    }
    path = PROFILES_DIR / args.system / args.romset / "profile.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=2) + "\n")
    print(json.dumps(profile, indent=2))
    print(f"\nWrote {path}")


if __name__ == "__main__":
    main()
