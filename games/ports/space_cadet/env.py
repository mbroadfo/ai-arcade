"""Space Cadet on the cabinet Pi, as a Python object: start the bridged game there (headless, time stepped), reach its socket
through an SSH tunnel, ask for the state, press and release inputs, and advance time.

    with SpaceCadet() as game:
        game.new_game()
        state = game.step(100)

Everything the game does is the game's own (physics, scoring, tilt); this file only moves messages. No playing decisions here.
"""
import json
import socket
import subprocess
import time

HOST = "pi@192.168.10.122"
GAME = "~/ai-arcade-pinball"
DATA = "~/RetroPie/ports/space-cadet-pinball/data/microsoft-original"
PORT = 7788
PID_FILE = "/tmp/scp-agent.pid"
INPUTS = ("left", "right", "plunger", "nudge_left", "nudge_right", "nudge_up")
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8"]


class SpaceCadet:
    def __init__(self, host=HOST, port=PORT, show=False):
        """show: draw on the cabinet's screen (EmulationStation must not be using it); otherwise headless."""
        self.host, self.port, self.show = host, port, show
        self.proc = self.tunnel = self.sock = self.reader = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()

    def _remote(self, command, **kw):
        return subprocess.run(SSH + [self.host, command], capture_output=True, text=True, timeout=30, **kw)

    def start(self):
        self._remote(f"[ -f {PID_FILE} ] && kill $(cat {PID_FILE}) 2>/dev/null; rm -f {PID_FILE}")
        video = "" if self.show else "SDL_VIDEODRIVER=dummy "
        launch = (f"cd {DATA} && echo $$ > {PID_FILE} && exec env SCP_AGENT_PORT={self.port} SCP_AGENT_STEP=1 {video}"
                  f"SDL_AUDIODRIVER=dummy XDG_DATA_HOME=/tmp/scp-agent-prefs {GAME}/source/bin/SpaceCadetPinball"
                  + (" -fullscreen" if self.show else ""))
        self.proc = subprocess.Popen(SSH + [self.host, launch], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.tunnel = subprocess.Popen(
            SSH + ["-N", "-L", f"{self.port}:127.0.0.1:{self.port}", self.host],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                self.sock = socket.create_connection(("127.0.0.1", self.port), timeout=10)
                self.reader = self.sock.makefile("r")
                self.ask(cmd="state")
                return
            except (OSError, ValueError):
                time.sleep(0.3)
        self.close()
        raise RuntimeError("could not reach the pinball bridge")

    def close(self):
        for p in (self.sock, self.tunnel):
            try:
                p.close() if p is self.sock else p.terminate()
            except Exception:
                pass
        try:
            self._remote(f"[ -f {PID_FILE} ] && kill $(cat {PID_FILE}) 2>/dev/null; rm -f {PID_FILE}")
        except Exception:
            pass
        if self.proc:
            self.proc.terminate()

    def ask(self, **msg):
        self.sock.sendall((json.dumps(msg) + "\n").encode())
        line = self.reader.readline()
        if not line:
            raise RuntimeError("the pinball bridge closed")
        return json.loads(line)

    def state(self):
        return self.ask(cmd="state")

    def step(self, frames):
        """Advance the game `frames` x 10 ms; returns the state after."""
        return self.ask(cmd="step", frames=int(frames))

    def press(self, name):
        self.ask(cmd="input", name=name, down=True)

    def release(self, name):
        self.ask(cmd="input", name=name, down=False)

    def new_game(self):
        self.ask(cmd="input", name="new_game", down=True)
        self.ask(cmd="input", name="new_game", down=False)
        return self.step(100)
