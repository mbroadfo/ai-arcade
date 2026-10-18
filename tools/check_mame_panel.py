"""Does MAME 0.251 obey the panel's controller file? Press the pretend panel (tools/synth_panel.py) while MAME runs a
game headless with tools/mame_panel_watch.lua, and compare what MAME's input fields did with what each control should do.

The pretend encoders are extra joysticks (they come after the real ones), so the check first asks MAME for its joystick
order, then builds a test copy of the controller file with the pretend encoders' numbers (panel_profiles.mame_ctrlr with
joy1 and joy2 moved): the buttons, sticks and keys are the production file's, only the joystick numbers differ. It also
reports MAME's own order of the real encoders (the production numbering, JOYCODE_1 and 2).

    python tools/check_mame_panel.py [--host ADDRESS]

Stops EmulationStation for the run (a pretend press would drive its menu) and starts it again; do not run it while
someone is playing. Writes nothing but /home/pi/.mame/ctrlr/panel-test.cfg (removed afterwards) and files in /tmp.
"""
import argparse
import sys
import time

import paramiko

import panel_profiles as pp
from gamelib import DEFAULT_PI_HOST, ROOT
from probe_mame_input import run
from synth_panel import SynthPanel

LUA = ROOT / "tools" / "mame_panel_watch.lua"
REMOTE_LUA = "/home/pi/ai-arcade/mame_panel_watch.lua"
LOG = "/tmp/panel-watch.log"
CTRLR_TEST = "/home/pi/.mame/ctrlr/panel-test.cfg"
SYNTH_NAME = "SYNTH-PANEL"

PLAYERS = ("P1", "P2")
STICK_ROW = [(p, d) for p in PLAYERS for d in ("UP", "DOWN", "LEFT", "RIGHT")]
BUTTONS_ROW = [(p, c) for p in PLAYERS for c in ("A", "B", "X", "Y", "SNOWFLAKE", "STAR")] + [("P2", "FLIGHT1"), ("P2", "FLIGHT2")]
COIN_ROW = [(p, c) for p in PLAYERS for c in ("COIN", "START")]
# game, what is pressed (in order)
# Battlezone: two tread sticks. The P1 encoder's stick is the left tread and the P2 encoder's stick the right tread.
BZONE = {("P1", "UP"): ["P1 Left Stick/Up"], ("P1", "DOWN"): ["P1 Left Stick/Down"],
         ("P2", "UP"): ["P1 Right Stick/Up"], ("P2", "DOWN"): ["P1 Right Stick/Down"],
         ("P1", "A"): ["P1 Button 1"], ("P1", "COIN"): ["Coin 1"], ("P1", "START"): ["1 Player Start"]}
RUNS = [("pacman", STICK_ROW + COIN_ROW, None), ("skydiver", BUTTONS_ROW, None), ("bzone", list(BZONE), BZONE)]


def mame_command(game, seconds, ctrlr):
    return (f"nohup mame {game} -inipath /opt/retropie/configs/mame-0251 -ctrlr {ctrlr} -video none -sound none "
            f"-skip_gameinfo -seconds_to_run {seconds} -autoboot_script {REMOTE_LUA} > /tmp/panel-watch-mame.txt 2>&1 &")


def read_log(ssh):
    rows = [line.split("\t") for line in run(ssh, f"cat {LOG} 2>/dev/null || true").splitlines() if line]
    return rows


def wait_ready(ssh, seconds=40):
    end = time.time() + seconds
    while time.time() < end:
        rows = read_log(ssh)
        if any(r[0] == "S" and len(r) > 2 and r[2] == "ready" for r in rows) and any(r[0] == "F" and r[1] == "fields" for r in rows):
            return rows
        time.sleep(1)
    raise RuntimeError("MAME never reported ready:\n" + run(ssh, "tail -5 /tmp/panel-watch-mame.txt"))


def start(ssh, game, names, ctrlr, seconds=120):
    run(ssh, "pkill -x mame || true; rm -f " + LOG)
    run(ssh, f"printf '%s\\n' {' '.join(repr(n) for n in names)} > /tmp/panel-watch-names.txt")
    run(ssh, mame_command(game, seconds, ctrlr))
    return wait_ready(ssh)


def stop(ssh):
    run(ssh, "pkill -x mame || true")


def joystick_order(rows):
    return [r[2] for r in rows if r[0] == "J"]


def check_run(ssh, panel, game, controls, expected):
    """Press each control in turn; return [(player, control, wanted fields, pressed, status)]. status is ok, FAIL, or
    n/a when the game has no such input field."""
    out = []
    names = sorted({n for c in controls for n in expected.get(c, [])})
    rows = start(ssh, game, names, "panel-test")
    have = {r[1] for r in rows if r[0] == "W"}
    for player, control in controls:
        want = expected.get((player, control), [])
        if not want or not all(w in have for w in want):
            out.append((player, control, want, [], "n/a"))
            continue
        before = len(read_log(ssh))
        panel.press(player, control, ms=300)
        time.sleep(0.6)
        events = [r for r in read_log(ssh)[before:] if r[0] == "F"]
        pressed = [r[2] for r in events if r[3] == "1"]
        released = [r[2] for r in events if r[3] == "0"]
        out.append((player, control, want, pressed, "ok" if pressed == want and released == want else "FAIL"))
    stop(ssh)
    return out


def check_ui(ssh, panel):
    """Menu, back and pause from the panel's buttons, on Pac-Man."""
    results = []
    start(ssh, "pacman", [], "panel-test")
    rows = lambda: read_log(ssh)  # noqa: E731

    def state(key):
        values = [r[3] for r in rows() if r[0] == "S" and len(r) > 3 and r[2] == key]
        return values[-1] if values else None

    panel.press("P1", "TAB", 300)
    time.sleep(0.8)
    results.append(("Tab opens MAME's menu", state("menu") == "true", state("menu")))
    panel.press("P1", "ESC", 300)
    time.sleep(0.8)
    results.append(("Esc closes it", state("menu") == "false", state("menu")))
    panel.press("P2", "PAUSE", 300)
    time.sleep(0.8)
    results.append(("Pause pauses", state("paused") == "true", state("paused")))
    panel.press("P2", "PAUSE", 300)
    time.sleep(0.8)
    results.append(("Pause again resumes", state("paused") == "false", state("paused")))
    panel.press("P1", "ESC", 300)  # no menu open: leaves MAME
    time.sleep(6)
    alive = run(ssh, "pgrep -x mame || true").strip()
    results.append(("Esc with no menu leaves MAME", alive == "", "still running" if alive else "ended"))
    stop(ssh)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    args = parser.parse_args()
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(args.host, username="pi", timeout=10)
    panel_def = pp.load_panel()
    expected = pp.expected_mame_fields(panel_def)
    failures = 0
    sftp = ssh.open_sftp()
    run(ssh, "mkdir -p /home/pi/ai-arcade")
    sftp.put(str(LUA), REMOTE_LUA)
    try:
        run(ssh, "sudo systemctl stop getty@tty1")  # EmulationStation would act on the pretend presses
        with SynthPanel(ssh, name=SYNTH_NAME) as panel:
            rows = start(ssh, "pacman", [], "panel")
            order = joystick_order(rows)
            stop(ssh)
            print("MAME's joysticks, in the order it numbers them (JOYCODE_1 first):")
            for n, name in enumerate(order, 1):
                print(f"  {n}  {name}")
            if SYNTH_NAME not in order:
                raise RuntimeError("MAME did not see the pretend encoders")
            first = order.index(SYNTH_NAME) + 1
            test = pp.mame_ctrlr(panel_def, joy1=first, joy2=first + 1)
            with sftp.open(CTRLR_TEST, "w") as f:
                f.write(test.encode())
            print(f"\nTest file uses joysticks {first} and {first + 1} (the pretend encoders); production uses 1 and 2.\n")
            for game, controls, special in RUNS:
                results = check_run(ssh, panel, game, controls, special or expected)
                print(f"{game}:")
                for player, control, want, saw, status in results:
                    print(f"  {player} {control:<10} should press {want}, MAME saw {saw}  {status}")
                    failures += status == "FAIL"
            print("\nMAME's menu keys:")
            for name, ok, value in check_ui(ssh, panel):
                print(f"  {name:<32} {'ok' if ok else 'FAIL'}  ({value})")
                failures += 0 if ok else 1
    finally:
        stop(ssh)
        run(ssh, f"rm -f {CTRLR_TEST}")
        run(ssh, "sudo systemctl start getty@tty1")
        ssh.close()
    print(f"\n{'all passed' if not failures else str(failures) + ' check(s) failed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
