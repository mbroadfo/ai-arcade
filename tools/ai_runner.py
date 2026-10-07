"""An AI run started from the Observatory: clear the cabinet's screen, start MAME for the game (start_pi_game.py), then
the player (play.py, which reports to the Observatory like any run). Stop asks the player to end cleanly first.

States: idle, starting (with the step), running, stopping, ended, failed. `on_change(state)` is called on every change.
The player's output goes to runs/observatory-logs/<time>-<game>.log; the last lines are in the state for the page.
"""
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

from gamelib import ROOT

TOOLS = Path(__file__).resolve().parent
LOGS = ROOT / "runs" / "observatory-logs"
STOP_WAIT = 20  # seconds for the player to finish its files after being asked to stop


class Runner:
    def __init__(self, cabinet, ask_player, on_change, host):
        """ask_player(message) -> how many players got it (the Observatory's command to running players)."""
        self.cabinet, self.ask_player, self.on_change, self.host = cabinet, ask_player, on_change, host
        self.lock = threading.Lock()
        self.proc = None
        self.tail = deque(maxlen=12)
        self.state = {"state": "idle"}

    def _set(self, **state):
        with self.lock:
            self.state = {**state, "tail": list(self.tail), "t": round(time.time(), 3)}
            snapshot = dict(self.state)
        self.on_change(snapshot)

    def busy(self):
        return self.state["state"] in ("starting", "running", "stopping")

    def start(self, game, play_args, speed=0.85, script="play.py", fresh=True):
        """fresh=False: the game is already up (an earlier run left it): start only the player, not MAME again."""
        if self.busy():
            raise RuntimeError("an AI run is already going")
        self.tail.clear()
        self._set(state="starting", game=game, step="Clearing the screen" if fresh else "Starting the player",
                  args=play_args)
        threading.Thread(target=self._run, args=(game, play_args, speed, script, fresh), daemon=True).start()

    def _run(self, game, play_args, speed, script="play.py", fresh=True):
        try:
            if fresh:
                self.cabinet.clear()
                self._set(state="starting", game=game, step="Starting MAME and the streams", args=play_args)
                p = subprocess.run([sys.executable, str(TOOLS / "start_pi_game.py"), "--game", game, "--host",
                                    self.host, "--speed", f"{speed:.2f}"],
                                   cwd=TOOLS, capture_output=True, text=True, timeout=120)
                self.tail.extend((p.stdout + p.stderr).strip().splitlines()[-6:])
                if p.returncode != 0:
                    self._set(state="failed", game=game, step="MAME did not start", args=play_args)
                    return
            self._set(state="starting", game=game, step="Starting the player", args=play_args)
            LOGS.mkdir(parents=True, exist_ok=True)
            log_path = LOGS / f"{time.strftime('%Y%m%d-%H%M%S')}-{game.replace('/', '_')}.log"
            with open(log_path, "w", encoding="utf-8") as log:
                self.proc = subprocess.Popen([sys.executable, "-u", str(TOOLS / script), "--host", self.host] + play_args,
                                             cwd=TOOLS, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                             encoding="utf-8", errors="replace")
                self._set(state="running", game=game, args=play_args, log=str(log_path))
                for line in self.proc.stdout:
                    log.write(line)
                    log.flush()
                    if line.strip():
                        self.tail.append(line.rstrip())
                code = self.proc.wait()
            self._set(state="ended" if code == 0 else "failed", game=game, args=play_args, log=str(log_path),
                      step=None if code == 0 else f"the player stopped with code {code}")
        except Exception as exc:  # the page must hear about it; the cabinet keeps whatever state it reached
            self.tail.append(str(exc))
            self._set(state="failed", game=game, step=str(exc), args=play_args)
        finally:
            self.proc = None

    def stop(self):
        """Ask the player to end the run; force it after STOP_WAIT seconds. Returns at once."""
        proc = self.proc
        if proc is None:
            return False
        self._set(**{**self.state, "state": "stopping"})

        def finish():
            self.ask_player({"op": "stop"})
            try:
                proc.wait(timeout=STOP_WAIT)
            except subprocess.TimeoutExpired:
                proc.terminate()
        threading.Thread(target=finish, daemon=True).start()
        return True
