#!/usr/bin/env python3
"""The cabinet's own controls for the Observatory: what is on the screen, what can be played, and switching between them.

    python3 cabinet.py status            JSON: menu / human (system, rom) / ai (romset) / launching / idle
    python3 cabinet.py catalog           JSON: every system with games, each game's name and emulator
    python3 cabinet.py launch SYSTEM ROM start a game for a person, the way EmulationStation would (runcommand)
    python3 cabinet.py stop              end the game on the screen (a person's or the AI's MAME)
    python3 cabinet.py clear             end everything on the screen, menu included (before AI mode takes it)
    python3 cabinet.py menu              back to EmulationStation
    python3 cabinet.py speed 0.85        AI mode's game speed, now (tools/mame_speed_control.lua applies it)
    python3 cabinet.py pause on|off      pause or resume AI mode's game (the same script)

A launch is handed to the console session: the request goes in LAUNCH_FILE, the session restarts, and the autostart
hook (pending.sh, run by /opt/retropie/configs/all/autostart.sh before EmulationStation) runs it, so the game gets the
screen and the keyboard as if it had been chosen in the menu. When it ends, EmulationStation starts.

Standard library only. Decides nothing about play; it only does what the operator asked.
"""
import json
import os
import re
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

HOME = os.path.expanduser("~")
SYSTEMS_CFG = "/etc/emulationstation/es_systems.cfg"
USER_SYSTEMS_CFG = os.path.join(HOME, ".emulationstation", "es_systems.cfg")
GAMELISTS = os.path.join(HOME, ".emulationstation", "gamelists")
ROMS = os.path.join(HOME, "RetroPie", "roms")
CONFIGS = "/opt/retropie/configs"
LAUNCH_FILE = "/dev/shm/ai-arcade-launch"
ES_PROCESS = "/emulationstation/emulationstation( |$)"
AI_SCRIPT = "/home/pi/ai-arcade/autoboot.lua"  # tools/start_pi_game.py's MAME (AI mode)
SPEED_FILE, SPEED_NOW = "/dev/shm/ai-arcade-speed", "/dev/shm/ai-arcade-speed.now"
PAUSE_FILE, PAUSE_NOW = "/dev/shm/ai-arcade-pause", "/dev/shm/ai-arcade-pause.now"
MAME_SYSTEMS = re.compile(r"^(arcade|mame.*|fba|neogeo)$")  # systems whose files are MAME sets


def run(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def processes():
    """{pid: (ppid, argv)} for every process."""
    out = {}
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/stat") as f:
                ppid = int(f.read().rsplit(")", 1)[1].split()[1])
            with open(f"/proc/{name}/cmdline", "rb") as f:
                argv = [a.decode(errors="replace") for a in f.read().split(b"\0") if a]
        except (OSError, ValueError, IndexError):
            continue
        out[int(name)] = (ppid, argv)
    return out


def find(procs, pattern):
    rx = re.compile(pattern)
    return [pid for pid, (_, argv) in procs.items() if argv and rx.search(" ".join(argv))]


def descendants(procs, pid):
    kids = [p for p, (pp, _) in procs.items() if pp == pid]
    out = []
    for k in kids:
        out += descendants(procs, k) + [k]
    return out  # deepest first


def runcommands(procs):
    """The games EmulationStation (or the hook) started: [(pid, system, rom)]."""
    games = []
    for pid, (_, argv) in procs.items():
        if len(argv) >= 6 and argv[0] in ("bash", "/bin/bash") and argv[1].endswith("runcommand.sh") and argv[3] == "_SYS_":
            games.append((pid, argv[4], argv[5]))
    return games


def ai_mame(procs):
    for pid, (_, argv) in procs.items():
        if argv and os.path.basename(argv[0]) == "mame" and AI_SCRIPT in argv:
            return pid, argv[1] if len(argv) > 1 else None
    return None


def status():
    procs = processes()
    human = runcommands(procs)
    ai = ai_mame(procs)
    es = bool(find(procs, ES_PROCESS))
    if human:
        _, system, rom = human[0]
        mode = "human"
    elif ai:
        mode = "ai"
    elif os.path.exists(LAUNCH_FILE):
        mode = "launching"
    elif es:
        mode = "menu"
    else:
        mode = "idle"
    out = {"mode": mode, "es": es, "t": round(time.time(), 3)}
    if human:
        out["human"] = {"system": system, "rom": rom, "stem": os.path.splitext(os.path.basename(rom))[0]}
    if ai:
        try:
            with open(SPEED_NOW) as f:
                speed = float(f.read().strip())
        except (OSError, ValueError):
            speed = None
        try:
            with open(PAUSE_NOW) as f:
                paused = f.read().strip() == "1"
        except OSError:
            paused = False
        out["ai"] = {"romset": ai[1], "speed": speed, "paused": paused,
                     "state_server": bool(find(procs, r"state_server\.py")),
                     "frame_server": bool(find(procs, r"frame_server\.py"))}
    return out


# ---------- catalog ----------

def systems():
    path = USER_SYSTEMS_CFG if os.path.exists(USER_SYSTEMS_CFG) else SYSTEMS_CFG
    out = []
    for node in ET.parse(path).getroot().findall("system"):
        get = lambda tag: (node.findtext(tag) or "").strip()  # noqa: E731
        out.append({"name": get("name"), "fullname": get("fullname"), "path": get("path").replace("~", HOME),
                    "extensions": [e.lower() for e in get("extension").split()]})
    return out


def gamelist(system):
    """path -> {name, playcount, lastplayed} from EmulationStation's list for this system."""
    out = {}
    for path in (os.path.join(GAMELISTS, system, "gamelist.xml"), os.path.join(ROMS, system, "gamelist.xml")):
        try:
            root = ET.parse(path).getroot()
        except (OSError, ET.ParseError):
            continue
        for game in root.findall("game"):
            rel = (game.findtext("path") or "").strip()
            if rel:
                out[os.path.normpath(os.path.join(ROMS, system, rel))] = {
                    "name": (game.findtext("name") or "").strip() or None,
                    "playcount": int(game.findtext("playcount") or 0),
                    "lastplayed": (game.findtext("lastplayed") or "").strip() or None}
    return out


def mame_names(stems):
    """MAME's own title for each set it knows (one call; unknown sets are left out)."""
    if not stems:
        return {}
    p = run("mame", "-listfull", *sorted(stems))
    names = {}
    for line in p.stdout.splitlines()[1:]:
        m = re.match(r'^(\S+)\s+"(.*)"$', line.strip())
        if m:
            names[m.group(1)] = m.group(2)
    return names


def emulators(system):
    def read(path):
        try:
            with open(path) as f:
                return dict(re.findall(r'^\s*([^=\s]+)\s*=\s*"(.*)"', f.read(), re.M))
        except OSError:
            return {}
    return read(os.path.join(CONFIGS, system, "emulators.cfg")).get("default"), read(os.path.join(CONFIGS, "all", "emulators.cfg"))


def catalog():
    out = []
    for s in systems():
        if not os.path.isdir(s["path"]):
            continue
        files = []
        for root, dirs, names in os.walk(s["path"]):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("media", "images", "videos")]
            files += [os.path.join(root, n) for n in names if os.path.splitext(n)[1].lower() in s["extensions"]]
        if not files:
            continue
        listed = gamelist(s["name"])
        stems = {os.path.splitext(os.path.basename(f))[0] for f in files}
        titles = mame_names(stems) if MAME_SYSTEMS.match(s["name"]) else {}
        default, own = emulators(s["name"])
        games = []
        for f in sorted(files):
            stem = os.path.splitext(os.path.basename(f))[0]
            meta = listed.get(os.path.normpath(f), {})
            games.append({"path": f, "stem": stem, "name": meta.get("name") or titles.get(stem) or stem,
                          "playcount": meta.get("playcount", 0), "lastplayed": meta.get("lastplayed"),
                          "emulator": own.get(f"{s['name']}_{stem}") or default})
        out.append({"name": s["name"], "fullname": s["fullname"], "games": games})
    return {"systems": out, "t": round(time.time(), 3)}


# ---------- switching ----------

def end_games(procs=None):
    """End the people's games (runcommand's emulators) and AI mode's MAME and servers. True if anything was running."""
    procs = procs or processes()
    victims = []
    for pid, _, _ in runcommands(procs):
        victims += descendants(procs, pid)
    ai = ai_mame(procs)
    if ai:
        victims.append(ai[0])
    victims += find(procs, r"(state_server|frame_server)\.py")
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in victims:
            try:
                os.kill(pid, sig)
            except OSError:
                pass
        deadline = time.time() + 4
        while time.time() < deadline and any(os.path.exists(f"/proc/{p}") for p in victims):
            time.sleep(0.1)
    deadline = time.time() + 6  # runcommand puts the video mode back and returns
    while time.time() < deadline and runcommands(processes()):
        time.sleep(0.2)
    return bool(victims)


def console(action):
    run("sudo", "systemctl", action, "getty@tty1")


def launch(system, rom):
    known = {s["name"]: s for s in systems()}
    if system not in known:
        raise SystemExit(f"unknown system {system!r}")
    real = os.path.realpath(rom)
    root = os.path.realpath(known[system]["path"])
    if not real.startswith(root + os.sep) or not os.path.isfile(real):
        raise SystemExit(f"{rom!r} is not a game in {system}")
    if "\n" in system or "\n" in rom:
        raise SystemExit("bad name")
    end_games()
    tmp = LAUNCH_FILE + ".tmp"
    with open(tmp, "w") as f:
        f.write(f"{system}\n{rom}\n")
    os.replace(tmp, LAUNCH_FILE)
    console("restart")  # the session ends (menu and all); autologin runs the hook, which runs the game


def main(argv):
    command = argv[1] if len(argv) > 1 else "status"
    if command == "status":
        print(json.dumps(status()))
    elif command == "catalog":
        print(json.dumps(catalog()))
    elif command == "launch" and len(argv) == 4:
        launch(argv[2], argv[3])
        print(json.dumps({"ok": True}))
    elif command == "stop":
        print(json.dumps({"ok": True, "ended": end_games()}))
    elif command == "clear":  # AI mode takes the screen: nothing of the menu may come back meanwhile
        try:
            os.remove(LAUNCH_FILE)
        except OSError:
            pass
        console("stop")
        end_games()
        run("pkill", "-f", ES_PROCESS)
        print(json.dumps({"ok": True}))
    elif command == "speed" and len(argv) == 3:
        value = float(argv[2])
        if not 0.2 <= value <= 1.0:
            raise SystemExit("speed: 0.2 to 1.0")
        tmp = SPEED_FILE + ".tmp"
        with open(tmp, "w") as f:
            f.write(f"{value}\n")
        os.replace(tmp, SPEED_FILE)
        print(json.dumps({"ok": True, "speed": value}))
    elif command == "pause" and len(argv) == 3 and argv[2] in ("on", "off"):
        if not ai_mame(processes()):
            raise SystemExit("no AI-mode game to pause")
        tmp = PAUSE_FILE + ".tmp"
        with open(tmp, "w") as f:
            f.write("1\n" if argv[2] == "on" else "0\n")
        os.replace(tmp, PAUSE_FILE)
        deadline = time.time() + 2  # until MAME has done it, so the answer is the state in force
        want = "1" if argv[2] == "on" else "0"
        while time.time() < deadline:
            try:
                with open(PAUSE_NOW) as f:
                    if f.read().strip() == want:
                        break
            except OSError:
                if want == "0":
                    break
            time.sleep(0.05)
        print(json.dumps({"ok": True, "paused": argv[2] == "on"}))
    elif command == "menu":
        end_games()
        if not find(processes(), ES_PROCESS):
            console("restart")
        print(json.dumps({"ok": True}))
    else:
        raise SystemExit(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
