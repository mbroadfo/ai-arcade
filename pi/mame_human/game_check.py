#!/usr/bin/env python3
"""Check that arcade games work in MAME 0.251 the way EmulationStation will run them (mame_human.sh), one by one:
it launches, the coin and start keys reach it, and Escape quits it.

A virtual keyboard (uinput) presses 5 (coin), then 1 (start), then Escape; game_check.lua, inside MAME, records when
each input arrives, how much of the screen changed after each, the speed, and screenshots. EmulationStation holds the
screen, so it is closed for the run and started again afterwards.

    python3 game_check.py --out DIR game [game ...]     # one JSON line per game on stdout and in DIR/results.jsonl
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

from evdev import UInput, ecodes as e

HERE = Path(__file__).resolve().parent
LAUNCHER = HERE / "mame_human.sh"
LUA = HERE / "game_check.lua"
ES_PROCESS = "/emulationstation/emulationstation( |$)"
BOOT_FRAMES = 1200    # 20 s of emulated time before the coin goes in (attract mode, self tests)
MIN_SPEED = 95.0      # percent of full speed, median over the run
BOOT_TIMEOUT = 30     # seconds to reach BOOT_FRAMES, warning screens included
STALL = 4             # seconds without a new frame before pressing Space to dismiss a warning screen


def tap(keyboard, key, hold=0.15):
    keyboard.write(e.EV_KEY, key, 1); keyboard.syn()
    time.sleep(hold)
    keyboard.write(e.EV_KEY, key, 0); keyboard.syn()


def read_log(path):
    facts = {"frames": 0, "speeds": []}
    if not path.exists():
        return facts
    for line in path.read_text(errors="replace").splitlines():
        word, *rest = line.split(" ")
        if word == "START":
            facts["machine"] = rest[0] if rest else None
            facts["description"] = " ".join(rest[1:])
        elif word == "FRAME" and len(rest) == 2:
            facts["frames"] = int(rest[0])
            if rest[1] != "?":
                facts["speeds"].append(float(rest[1]))
        elif word in ("COIN_SEEN", "START_SEEN", "STOP"):
            facts[word.lower()] = int(rest[0])
        elif word in ("COIN_CHANGE", "START_CHANGE", "IDLE_CHANGE"):
            facts[word.lower()] = float(rest[0])
    return facts


def wait_frames(log, proc, frames, timeout, keyboard, result):
    """Wait for the game to run `frames` frames. MAME holds a game on its warning screen ("this machine is not
    working perfectly... press any key") without running it; when nothing has moved for STALL seconds, Space (a game
    button, harmless before a coin) dismisses it, up to twice. Counted in result["warning_dismissed"]."""
    deadline = time.time() + timeout
    last, moved_at = -1, time.time()
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        now = read_log(log)["frames"]
        if now >= frames:
            return True
        if now != last:
            last, moved_at = now, time.time()
        elif time.time() - moved_at > STALL and result["warning_dismissed"] < 2:
            tap(keyboard, e.KEY_SPACE)
            result["warning_dismissed"] += 1
            moved_at = time.time()
        time.sleep(0.25)
    return False


def check(game, keyboard, out, boot_frames=BOOT_FRAMES):
    folder = out / game
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*"):
        if old.is_file():
            old.unlink()
    log = folder / "check.log"
    env = dict(os.environ, CHECK_LOG=str(log))
    started = time.time()
    with open(folder / "mame.out", "w") as mame_out:
        proc = subprocess.Popen([str(LAUNCHER), game, "-autoboot_script", str(LUA), "-snapshot_directory", str(folder)],
                                stdout=mame_out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env,
                                start_new_session=True)
    result = {"game": game, "warning_dismissed": 0}
    booted = wait_frames(log, proc, boot_frames, BOOT_TIMEOUT + boot_frames / 60, keyboard, result)
    if booted:
        tap(keyboard, e.KEY_5)
        time.sleep(2.5)
        tap(keyboard, e.KEY_1)
        time.sleep(4.5)
        tap(keyboard, e.KEY_ESC)
    try:
        proc.wait(timeout=10)
        exited = True
    except subprocess.TimeoutExpired:
        exited = False
        os.killpg(proc.pid, 9)  # MAME on a warning screen ignores a polite stop
        proc.wait()
    facts = read_log(log)
    speeds = facts.pop("speeds")
    result.update(facts)
    result.update({
        "launched": booted,
        "exit_code": proc.returncode,
        "quit_on_escape": booted and exited and proc.returncode == 0,
        "speed": round(statistics.median(speeds), 1) if speeds else None,
        "seconds": round(time.time() - started, 1),
        "coin_reached_game": "coin_seen" in facts,
        "start_reached_game": "start_seen" in facts,
        "screenshots": sorted(p.name for p in folder.glob("*.png")),
    })
    if not booted:
        tail = (folder / "mame.out").read_text(errors="replace").strip().splitlines()[-6:]
        result["mame_said"] = tail
    result["auto_pass"] = bool(result["launched"] and result["coin_reached_game"] and result["start_reached_game"]
                               and result["quit_on_escape"] and (result["speed"] or 0) >= MIN_SPEED)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--keep-es-closed", action="store_true", help="leave EmulationStation closed afterwards")
    parser.add_argument("--boot-seconds", type=float, default=BOOT_FRAMES / 60,
                        help="emulated seconds before the coin (longer for games with slow first-run setup)")
    parser.add_argument("games", nargs="+")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # Never take the screen from someone playing: a game EmulationStation started runs under runcommand.sh.
    while subprocess.run(["pgrep", "-f", "runcommand.sh"], capture_output=True).returncode == 0:
        print("someone is playing a game; waiting", file=sys.stderr, flush=True)
        time.sleep(60)
    subprocess.run(["pkill", "-f", ES_PROCESS])
    subprocess.run(["timeout", "10", "sh", "-c", f"while pgrep -f '{ES_PROCESS}' >/dev/null; do sleep 0.2; done"])
    keyboard = UInput({e.EV_KEY: [e.KEY_5, e.KEY_1, e.KEY_ESC, e.KEY_SPACE]}, name="AI Arcade check keyboard")
    time.sleep(1)  # let udev announce it before MAME enumerates keyboards
    try:
        with open(out / "results.jsonl", "a") as results:
            for game in args.games:
                result = check(game, keyboard, out, int(args.boot_seconds * 60))
                line = json.dumps(result)
                print(line, flush=True)
                results.write(line + "\n")
                results.flush()
    finally:
        keyboard.close()
        if not args.keep_es_closed:
            subprocess.run(["sudo", "systemctl", "restart", "getty@tty1"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
