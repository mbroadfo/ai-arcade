"""The lab page. It starts a round and reads the run directory. It does not decide a move.

    python -m games.lab.server
    http://localhost:8790/
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from games.lab.lineage import collapsed_history, load_rows
from games.lab.models import registry
from games.lab.paths import REPO_ROOT, runs_root
from games.lab.seats import SEATS
from games.lab.supervisor import chain_running, load_catalog, read_chain, round_running

PAGE = Path(__file__).with_name("static") / "index.html"
PORT = int(os.environ.get("LAB_PORT", "8790"))


def _rounds() -> list[dict]:
    root = runs_root()
    if not root.is_dir():
        return []
    found = []
    for path in sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True):
        results = path / "results.json"
        if not results.is_file():
            continue
        data = json.loads(results.read_text(encoding="utf-8"))
        data["id"] = path.name
        found.append(data)
    return found[:24]


def _current() -> dict | None:
    pointer = runs_root() / "current.json"
    if not pointer.is_file():
        return None
    try:
        data = json.loads(pointer.read_text(encoding="utf-8"))
        run_dir = Path(data["path"])
        state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, KeyError):
        return None
    seats = []
    for index in range(6):
        status_path = run_dir / "seats" / str(index) / "status.json"
        if status_path.is_file():
            seat = _read_json(status_path)
            if seat is None:
                seat = dict(manifest["seats"][index])
            else:
                seat["replay"] = (status_path.parent / "best.gif").is_file()
            seats.append(seat)
        else:
            seats.append(manifest["seats"][index])
    chain = read_chain()
    running = round_running() or chain_running()
    phase = chain.get("phase") if running and chain and chain.get("status") == "running" else None
    return {
        "state": state,
        "manifest": manifest,
        "seats": seats,
        "running": running,
        "phase": phase,
    }


def _hall(current: dict | None) -> dict:
    rows = load_rows(runs_root()) or collapsed_history(_rounds())
    live = None
    chain = read_chain()
    if current and current.get("running") and chain and chain.get("status") == "running":
        ranked = [seat for seat in current.get("seats") or [] if "score" in seat]
        leader = max(ranked, key=lambda seat: (seat.get("score") or 0, -int(seat.get("seat") or 0))) if ranked else None
        steps = max((int(seat.get("steps") or 0) for seat in ranked), default=0)
        manifest = current.get("manifest") or {}
        live = {
            "generation": chain.get("generation"),
            "phase": chain.get("phase"),
            "parent_score": chain.get("parent_score"),
            "parent_name": chain.get("parent_name"),
            "leader": None if leader is None else leader.get("name"),
            "score": 0 if leader is None else int(leader.get("score") or 0),
            "steps": steps,
            "budget": manifest.get("steps"),
        }
    record = max(rows, key=lambda row: (row.get("score") or 0, -int(row.get("generation") or 0))) if rows else None
    return {"rows": rows, "live": live, "record": record}


def _safe_run(run_id: str) -> Path:
    if not run_id or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" for ch in run_id):
        raise KeyError(run_id)
    path = runs_root() / run_id
    if not path.is_dir():
        raise KeyError(run_id)
    return path


def _read_shared(path: Path) -> bytes | None:
    """The seat replaces latest.jpg while the page is reading it."""
    for _ in range(4):
        try:
            return path.read_bytes()
        except PermissionError:
            time.sleep(0.02)
    return None


def _read_json(path: Path) -> dict | None:
    """The seat replaces status.json while the page is reading it."""
    for _ in range(6):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except PermissionError:
            time.sleep(0.02)
            continue
        except (OSError, json.JSONDecodeError):
            time.sleep(0.02)
            continue
        return data if isinstance(data, dict) else None
    return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload) -> None:
        self._send(code, json.dumps(payload).encode(), "application/json")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/api/catalog":
            try:
                games = [game.to_json() for game in load_catalog()]
            except Exception as exc:
                self._json(500, {"error": str(exc)})
                return
            self._json(200, {"games": games})
            return
        if path == "/api/models":
            self._json(200, {"models": registry.describe(), "seats": list(SEATS)})
            return
        if path == "/api/status":
            current = _current()
            self._json(200, {
                "current": current,
                "hall": _hall(current),
                "stop_requested": (runs_root() / "stop.request").is_file() and bool(current and current.get("running")),
            })
            return
        if path.startswith("/thumb/"):
            seat = path.removeprefix("/thumb/")
            if seat not in {str(i) for i in range(6)}:
                self._json(404, {"error": "no such seat"})
                return
            current = _current()
            if current is None:
                self._json(404, {"error": "no round"})
                return
            image = runs_root() / current["state"]["id"] / "seats" / seat / "latest.jpg"
            if not image.is_file():
                self._json(404, {"error": "no frame yet"})
                return
            payload = _read_shared(image)
            if payload is None:
                self._json(404, {"error": "no frame yet"})
                return
            self._send(200, payload, "image/jpeg")
            return
        if path.startswith("/replay/"):
            rest = path.removeprefix("/replay/")
            run_id, _, seat = rest.partition("/")
            if seat not in {str(i) for i in range(6)}:
                self._json(404, {"error": "no such seat"})
                return
            try:
                run_dir = _safe_run(run_id)
            except KeyError:
                self._json(404, {"error": "no such round"})
                return
            gif = run_dir / "seats" / seat / "best.gif"
            if not gif.is_file():
                self._json(404, {"error": "no life saved"})
                return
            self._send(200, gif.read_bytes(), "image/gif")
            return
        if path.startswith("/video/"):
            try:
                run_dir = _safe_run(path.removeprefix("/video/"))
            except KeyError:
                self._json(404, {"error": "no such round"})
                return
            for name, content_type in (("best.mp4", "video/mp4"), ("best.gif", "image/gif")):
                video = run_dir / name
                if video.is_file():
                    self._send(200, video.read_bytes(), content_type)
                    return
            self._json(404, {"error": "no video"})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/stop":
            (runs_root() / "stop.request").write_text("stop\n", encoding="utf-8")
            self._json(200, {"ok": True})
            return
        if path != "/api/start":
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 1_000_000:
            self._json(400, {"error": "bad body"})
            return
        try:
            body = json.loads(self.rfile.read(length).decode())
            game_id = body["game_id"]
            steps = int(body.get("steps") or 200_000)
            seats = body.get("seats")
            if seats is None:
                seats = [{"model": "ppo_cnn", "seed": index + 1} for index in range(6)]
            if len(seats) != 6 or not 256 <= steps <= 5_000_000:
                raise ValueError("need six seats and a step budget from 256 to 5000000")
            if round_running() or chain_running():
                raise ValueError("training is already running")
            # Validate before detaching so the page gets the reason.
            from games.lab.catalog import by_id
            from games.lab.integrations import get
            games = by_id(load_catalog())
            game = games[game_id]
            if not game.selectable:
                raise ValueError(game.reason or "that game cannot be started")
            integration = get(game.integration)
            for seat in seats:
                registry.check(seat["model"], integration)
                int(seat["seed"])
        except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
            return
        cmd = [
            sys.executable, "-m", "games.lab.supervisor",
            "--game", game_id, "--steps", str(steps), "--seats", json.dumps(seats), "--chain",
        ]
        stop = runs_root() / "stop.request"
        if stop.is_file():
            stop.unlink()
        _spawn_supervisor(cmd)
        self._json(200, {"ok": True})


class _Server(ThreadingHTTPServer):
    """One socket for localhost. Browsers try ::1 before 127.0.0.1."""

    address_family = socket.AF_INET6

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()


def _spawn_supervisor(cmd: list[str]) -> None:
    """Start the round off this console. A console Ctrl+C was killing the page."""
    log_path = runs_root() / "supervisor.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = open(log_path, "a", encoding="utf-8")
    kwargs = {
        "cwd": str(REPO_ROOT),
        "stdin": subprocess.DEVNULL,
        "stdout": log,
        "stderr": log,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.CREATE_NO_WINDOW
        )
        kwargs["close_fds"] = True
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)


def _ignore_ctrl_c() -> None:
    if sys.platform != "win32":
        return
    import ctypes
    ctypes.windll.kernel32.SetConsoleCtrlHandler(None, True)


def main() -> int:
    _ignore_ctrl_c()
    server = _Server(("::", PORT), Handler)
    print(f"Training lab at http://localhost:{PORT}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Training lab stopped by console interrupt", flush=True)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
