"""Does AdvanceMAME obey the panel's input mapping? Runs a game on the Pi's screen with AdvanceMAME's input recorder
(--record) and presses the pretend panel (tools/synth_panel.py) while it runs:

  * input: two runs with nobody pressing (they must match each other) and one with presses; every press that reaches the
    game shows as a separate burst of changed frames in the recording;
  * pause and menu: while the game is paused or the main menu is open it runs no frames, so the recording comes out
    shorter by the time spent there;
  * exit: Esc in the attract mode (no coins) must end the game.

The test uses a copy of advmame.rc with the generated mapping (panel_profiles.advmame_inputs) pointed at the pretend
encoders, which AdvanceMAME names after the real pair (..._3 and _4), and starts AdvanceMAME the way the launcher does,
with the AI Arcade pads hidden from SDL. The real rc is not touched. Stops EmulationStation for the run and starts it
again. The recordings are kept in runs/advmame-*.inp.

    python tools/check_advmame_panel.py [--game joust] [--host ADDRESS]
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
STRIDE = 120  # bytes in one recorded frame
FRAMES_PER_SECOND = 41
INPUT_PRESSES = [("P1", "UP"), ("P1", "DOWN"), ("P1", "COIN"), ("P1", "START"), ("P1", "A"), ("P2", "UP"), ("P2", "COIN"),
                 ("P2", "START"), ("P2", "A")]


def start(ssh, game, name, seconds):
    run(ssh, f"rm -f {DIR}/{name}.inp {DIR}/advmame.log; pkill -x advmame || true")
    run(ssh, f"nohup sh -c 'cd {DIR} && env {pp.ADV_HIDE_AI_PADS} timeout {seconds} /opt/retropie/emulators/advmame/bin/advmame "
             f"{game} -cfg {DIR}/advmame.rc --record {DIR}/{name}.inp --log > {DIR}/out.txt 2>&1' > /dev/null 2>&1 < /dev/null &")
    time.sleep(7)


def finish(ssh, sftp, name):
    run(ssh, "pkill -x advmame || true")
    time.sleep(2)
    sftp.get(f"{DIR}/{name}.inp", str(ROOT / "runs" / f"advmame-{name}.inp"))
    return (ROOT / "runs" / f"advmame-{name}.inp").read_bytes()


def data_length(recording):
    return len(recording.rstrip(b"\0"))


def episodes(base, pressed):
    """The runs of consecutive recorded frames where the pressed run's input differs from the quiet one: one per press
    that reached the game. [(first frame, last frame, byte in the frame, value)]."""
    out = []
    for i in range(64, min(len(base), len(pressed))):
        if base[i] != pressed[i]:
            frame, offset = i // STRIDE, i % STRIDE
            if out and frame - out[-1][1] <= 1 and offset == out[-1][2] and pressed[i] == out[-1][3]:
                out[-1][1] = frame
            else:
                out.append([frame, frame, offset, pressed[i]])
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game", default="joust")
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    args = parser.parse_args()
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(args.host, username="pi", timeout=10)
    sftp = ssh.open_sftp()
    panel_def = pp.load_panel()
    problems = []
    try:
        run(ssh, "sudo systemctl stop getty@tty1")
        run(ssh, f"mkdir -p {DIR}")
        live = sftp.open(RC_LIVE).read().decode()
        with SynthPanel(ssh) as panel:
            test = pp.merge_advmame_rc(live, pp.advmame_inputs(panel_def, pp.ADV_JOY + "_3", pp.ADV_JOY + "_4"))
            with sftp.open(f"{DIR}/advmame.rc", "w") as f:
                f.write(test.encode())
            rec = {}
            for name in ("base1", "base2"):
                start(ssh, args.game, name, 26)
                time.sleep(14)
                rec[name] = finish(ssh, sftp, name)
            start(ssh, args.game, "pressed", 26)
            for who, ctl in INPUT_PRESSES:
                panel.press(who, ctl, ms=300)
                time.sleep(0.7)
            rec["pressed"] = finish(ssh, sftp, "pressed")
            print("input: two quiet runs", "match" if rec["base1"] == rec["base2"] else "DIFFER (frame counts or timing)")
            eps = episodes(rec["base1"], rec["pressed"])
            print(f"input: {len(eps)} separate presses reached the game (of {len(INPUT_PRESSES)} pressed; a game ignores controls it "
                  "does not use). First frame, last, byte, value:")
            for e in eps:
                print("  ", e)
            if not eps:
                problems.append("no press reached the game")
            # pause and menu: the recording stops growing while the game is paused or the menu is open; compared with a
            # quiet run of the same length
            start(ssh, args.game, "quiet", 30)
            time.sleep(5 + 4 + 0.6)
            rec["quiet"] = finish(ssh, sftp, "quiet")
            for label, press_open, press_close in (("pause (P2 Pause)", ("P2", "PAUSE"), ("P2", "PAUSE")),
                                                   ("menu (P1 Tab, closed with Esc)", ("P1", "TAB"), ("P1", "ESC"))):
                name = "pause" if "Pause" in label else "menu"
                start(ssh, args.game, name, 30)
                panel.press(*press_open, ms=300)
                time.sleep(5)
                panel.press(*press_close, ms=300)
                time.sleep(4)
                rec[name] = finish(ssh, sftp, name)
                lost = (data_length(rec["quiet"]) - data_length(rec[name])) / STRIDE / FRAMES_PER_SECOND
                ok = lost > 2.5  # 5 s were spent paused or in the menu
                print(f"{label}: the recording is {lost:.1f} s shorter than a quiet run: {'ok' if ok else 'NOT PAUSED'}")
                if not ok:
                    problems.append(label)
            # exit: AdvanceMAME asks for confirmation (misc_safequit): Esc, then Enter on the confirmation
            start(ssh, args.game, "exit", 40)
            panel.press("P1", "ESC", ms=400)
            time.sleep(3)
            after_esc = run(ssh, "pgrep -x advmame || true").strip() == ""
            panel.press("P2", "ENTER", ms=400)
            time.sleep(5)
            gone = run(ssh, "pgrep -x advmame || true").strip() == ""
            print("exit: after Esc the game", "ended" if after_esc else "is still running (a confirmation menu)",
                  "; after Enter it", "ended: ok" if gone else "is still running: FAILED")
            if not gone:
                problems.append("exit")
    finally:
        run(ssh, "pkill -x advmame || true")
        run(ssh, "sudo systemctl start getty@tty1")
        ssh.close()
    print("\n" + ("all passed" if not problems else "problems: " + ", ".join(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
