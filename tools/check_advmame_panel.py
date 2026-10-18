"""Does AdvanceMAME obey the panel's input mapping? Run a game on the Pi's screen with AdvanceMAME's input recorder
(--record) three times: twice with nobody pressing (to see how much two identical runs differ) and once while the pretend
panel (tools/synth_panel.py) presses controls. A control that reaches the game changes the recorded input.

The test uses a copy of advmame.rc with the generated mapping (panel_profiles.advmame_inputs) pointed at the pretend
encoders, which AdvanceMAME names after the real pair (0079_0006_3 and _4). The real rc is
not touched. Stops EmulationStation for the run and starts it again. The recordings are kept in runs/advmame-*.inp.

    python tools/check_advmame_panel.py [--game bzone] [--host ADDRESS]
"""
import argparse
import sys
import time

import paramiko

import panel_profiles as pp
from gamelib import DEFAULT_PI_HOST, ROOT
from probe_mame_input import run
from synth_panel import SynthPanel

RC_LIVE = "/opt/retropie/configs/mame-advmame/advmame.rc"
DIR = "/tmp/advtest"
SECONDS = 24
PRESSES = [("P1", "UP"), ("P1", "DOWN"), ("P1", "COIN"), ("P1", "START"), ("P2", "UP"), ("P2", "DOWN"), ("P2", "COIN"),
           ("P2", "START"), ("P1", "B"), ("P2", "A")]


def record(ssh, game, name, presses=None, panel=None):
    """Run the game recording its input to DIR/name.inp; press the controls from the 7th second."""
    run(ssh, f"rm -f {DIR}/{name}.inp {DIR}/advmame.log; pkill -x advmame || true")
    run(ssh, f"nohup sh -c 'cd {DIR} && timeout {SECONDS} /opt/retropie/emulators/advmame/bin/advmame {game} "
             f"-cfg {DIR}/advmame.rc --record {DIR}/{name}.inp --log > {DIR}/out.txt 2>&1' > /dev/null 2>&1 < /dev/null &")
    time.sleep(7)
    for player, control in presses or []:
        panel.press(player, control, ms=300)
        time.sleep(0.7)
    time.sleep(max(1, SECONDS - 7 - 0.7 * len(presses or [])) + 1)
    run(ssh, "pkill -x advmame || true")
    time.sleep(2)


def compare(base1, base2, pressed):
    """Describe how the recordings differ. An .inp holds the input of every frame, so identical runs match byte for byte
    up to the shorter length; the first differing byte after the header shows where input first changed."""
    n = min(len(base1), len(base2), len(pressed))

    def first_diff(a, b):
        return next((i for i in range(64, n) if a[i] != b[i]), None)

    lines = [f"sizes: base1 {len(base1)}, base2 {len(base2)}, pressed {len(pressed)}"]
    d12, d1p = first_diff(base1, base2), first_diff(base1, pressed)
    lines.append(f"two runs with no presses differ first at byte {d12}" if d12 is not None else "two runs with no presses are identical")
    lines.append(f"the pressed run differs from base1 first at byte {d1p}" if d1p is not None else "the pressed run is identical to base1")
    reached = d1p is not None and (d12 is None or d1p < d12)
    return lines, reached


def exit_chord(ssh, game, panel):
    """Hold the P1 encoder's coin and start together (the exit chord): does the game end?"""
    run(ssh, f"rm -f {DIR}/advmame.log; pkill -x advmame || true")
    run(ssh, f"nohup sh -c 'cd {DIR} && timeout 40 /opt/retropie/emulators/advmame/bin/advmame {game} -cfg {DIR}/advmame.rc "
             f"--log > {DIR}/out.txt 2>&1' > /dev/null 2>&1 < /dev/null &")
    time.sleep(8)
    alive_before = run(ssh, "pgrep -x advmame || true").strip() != ""
    panel.press_together([("P1", "COIN"), ("P1", "START")], ms=600)
    time.sleep(5)
    alive_after = run(ssh, "pgrep -x advmame || true").strip() != ""
    run(ssh, "pkill -x advmame || true")
    return alive_before, alive_after


def episodes(base, pressed, stride=120):
    """The runs of consecutive recorded frames where the pressed run's input differs from the quiet one: one run per press
    that reached the game. [(first frame, last frame, byte in the frame, value)]; stride is the bytes in a frame record."""
    out = []
    for i in range(64, min(len(base), len(pressed))):
        if base[i] != pressed[i]:
            frame, offset = i // stride, i % stride
            if out and frame - out[-1][1] <= 1 and offset == out[-1][2] and pressed[i] == out[-1][3]:
                out[-1][1] = frame
            else:
                out.append([frame, frame, offset, pressed[i]])
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game", default="bzone")
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    args = parser.parse_args()
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(args.host, username="pi", timeout=10)
    sftp = ssh.open_sftp()
    panel_def = pp.load_panel()
    reached = False
    try:
        run(ssh, "sudo systemctl stop getty@tty1")
        run(ssh, f"mkdir -p {DIR}")
        live = sftp.open(RC_LIVE).read().decode()
        with SynthPanel(ssh) as panel:
            test = pp.merge_advmame_rc(live, pp.advmame_inputs(panel_def, pp.ADV_JOY + "_3", pp.ADV_JOY + "_4"))
            with sftp.open(f"{DIR}/advmame.rc", "w") as f:
                f.write(test.encode())
            for name, presses in (("base1", None), ("base2", None), ("pressed", PRESSES)):
                record(ssh, args.game, name, presses, panel)
                sftp.get(f"{DIR}/{name}.inp", str(ROOT / "runs" / f"advmame-{name}.inp"))
                print(name, "recorded", flush=True)
            print("exit chord (P1 coin + start):", end=" ", flush=True)
            before, after = exit_chord(ssh, args.game, panel)
            print("game ended" if before and not after else f"FAILED (running before: {before}, after: {after})")
        data = {n: open(ROOT / "runs" / f"advmame-{n}.inp", "rb").read() for n in ("base1", "base2", "pressed")}
        lines, reached = compare(data["base1"], data["base2"], data["pressed"])
        print("\n".join(lines))
        print("\nPress-driven change reached the game." if reached else "\nNo sign that any press reached the game.")
    finally:
        run(ssh, "pkill -x advmame || true")
        run(ssh, "sudo systemctl start getty@tty1")
        ssh.close()
    return 0 if reached else 1


if __name__ == "__main__":
    sys.exit(main())
