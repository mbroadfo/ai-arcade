"""Feasibility probe for the agent bridge: start the patched game headless, play a ball by hand-written steps, and report what
the bridge shows and how fast time can be stepped. Run on the Pi:

    python3 probe.py <game folder> <data folder>
"""
import json
import os
import socket
import subprocess
import sys
import time

game, data = sys.argv[1], sys.argv[2]
PORT = 7788
env = dict(os.environ, SCP_AGENT_PORT=str(PORT), SCP_AGENT_STEP="1", SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy",
           XDG_DATA_HOME="/tmp/scp-probe-prefs")
proc = subprocess.Popen([os.path.join(game, "source/bin/SpaceCadetPinball")], cwd=data, env=env,
                        stdout=open("/tmp/scp-probe.log", "w"), stderr=subprocess.STDOUT)
sock = None
for _ in range(100):
    try:
        sock = socket.create_connection(("127.0.0.1", PORT), timeout=5)
        break
    except OSError:
        time.sleep(0.2)
if sock is None:
    proc.kill()
    sys.exit("could not connect; see /tmp/scp-probe.log")
reader = sock.makefile("r")


def ask(**msg):
    sock.sendall((json.dumps(msg) + "\n").encode())
    return json.loads(reader.readline())


def show(tag, s):
    balls = [(round(b["x"], 2), round(b["y"], 2), round(b["speed"], 2)) for b in s.get("balls", [])]
    print(f"{tag:>22} score={s.get('score')} ball#{s.get('ball_number')} mode={s['game_mode']} balls={balls} "
          f"L={s.get('flippers', {}).get('left', {}).get('angle')} msg={s.get('message')!r}", flush=True)


try:
    show("start", ask(cmd="state"))
    ask(cmd="input", name="new_game", down=True)
    ask(cmd="input", name="new_game", down=False)
    show("after new game", ask(cmd="step", frames=100))
    ask(cmd="input", name="plunger", down=True)
    show("plunger held 1.5s", ask(cmd="step", frames=150))
    ask(cmd="input", name="plunger", down=False)
    for i in range(8):
        show(f"t+{(i + 1) * 0.5:.1f}s", ask(cmd="step", frames=50))
    t = time.time()
    s = ask(cmd="step", frames=5000)
    dt = time.time() - t
    show("after 50 s", s)
    print(f"stepped 5000 frames (50 s of game time) in {dt:.2f} s wall = {50 / dt:.1f}x real time", flush=True)
    ask(cmd="input", name="left", down=True)
    show("left flipper up", ask(cmd="step", frames=20))
    ask(cmd="input", name="left", down=False)
    show("left flipper down", ask(cmd="step", frames=20))
finally:
    proc.kill()
