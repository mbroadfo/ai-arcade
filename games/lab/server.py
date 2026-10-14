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
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from games.lab.hints import HINTS_NAME, add_hint, change_hint, labels, parse_actions, read_hints
from games.lab.lineage import collapsed_history, load_rows
from games.lab.models import registry
from games.lab.models.networks import network_for
from games.lab.paths import REPO_ROOT, pause_requested, runs_root, stop_requested
from games.lab.playback import FILM_NAME, STAMP_NAME, film_matches
from games.lab.ranking import generation_rank
from games.lab.seats import SEATS, default_seat_specs
from games.lab.supervisor import _alive, abandon_pause, chain_running, load_catalog, read_chain, read_pause, round_running
from games.lab.tape import TAPE_NAME, comparable, compatible, floor_value, read_tape

PAGE = Path(__file__).with_name("static") / "index.html"
WATCH = Path(__file__).with_name("static") / "watch.html"
CHALLENGE_PAGE = Path(__file__).with_name("static") / "challenge.html"
PORT = int(os.environ.get("LAB_PORT", "8790"))
_play_lock = threading.Lock()


def _page_adapter():
    """The adapter for the live round, or the only installed adapter."""
    from games.lab.registry import get, registered
    manifest = (_current() or {}).get("manifest") or {}
    integration_id = manifest.get("integration")
    if integration_id:
        try:
            return get(integration_id)
        except KeyError:
            return None
    adapters = registered()
    if len(adapters) == 1:
        return adapters[0]
    return None


def _buttons() -> list[str]:
    adapter = _page_adapter()
    actions = getattr(adapter, "actions", None) if adapter is not None else None
    if not actions:
        return []
    return labels(list(actions))


def _rank_sense(current: dict | None) -> str:
    from games.lab.contract import SURVIVAL_SENSE, sense_of
    manifest = (current or {}).get("manifest") or {}
    if manifest.get("sense") in ("maximize", "minimize"):
        return manifest["sense"]
    sensed = sense_of(_page_adapter())
    return sensed or SURVIVAL_SENSE


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
    if not running and read_pause() is not None:
        phase = "paused"
    elif running and chain and chain.get("status") == "running":
        phase = chain.get("phase")
    else:
        phase = None
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


def _parent_score(current: dict | None):
    manifest = (current or {}).get("manifest") or {}
    parent = manifest.get("parent_score")
    if parent is None:
        return None
    try:
        return int(parent)
    except (TypeError, ValueError):
        return None


def _practice(current: dict | None) -> dict:
    """Whether this generation is playing the shared best run."""
    parent = _parent_score(current)
    floor = 0 if parent is None else parent
    empty = {"active": False, "floor": floor}
    run_id = ((current or {}).get("state") or {}).get("id")
    if not run_id:
        return empty
    tape = read_tape(runs_root() / str(run_id) / TAPE_NAME)
    objective = ((current or {}).get("manifest") or {}).get("objective")
    if not isinstance(tape, dict):
        return empty
    try:
        score = int(tape.get("score") or 0)
        n_actions = int(tape.get("n_actions") or 0)
    except (TypeError, ValueError):
        return empty
    actions = tape.get("actions") if isinstance(tape.get("actions"), list) else []
    reached = comparable(tape)
    return {
        "active": reached > 0 and reached >= floor_value(floor) and compatible(tape, n_actions, objective),
        "score": score,
        "name": tape.get("name") or "",
        "presses": len(actions),
        "world": tape.get("world"),
        "stage": tape.get("stage"),
        "floor": floor,
    }


def _seat_index(seat: str) -> bool:
    return seat in {str(index) for index in range(6)}


def _busy_playback(except_dir: Path) -> bool:
    root = runs_root()
    if not root.is_dir():
        return False
    for path in root.glob("*/seats/*/play.json"):
        if path.parent == except_dir:
            continue
        data = _read_json(path)
        if not data or data.get("state") != "preparing":
            continue
        try:
            pid = int(data.get("pid") or 0)
        except (TypeError, ValueError):
            continue
        if _alive(pid):
            return True
    return False


def _start_playback(run_dir: Path, seat: str) -> int:
    """One extra game, off the training seats. It only writes that seat's video."""
    log_path = runs_root() / "playback.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = open(log_path, "a", encoding="utf-8")
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = ""
    env["SDL_AUDIODRIVER"] = "dummy"
    kwargs = {
        "cwd": str(REPO_ROOT),
        "stdin": subprocess.DEVNULL,
        "stdout": log,
        "stderr": log,
        "env": env,
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
    proc = subprocess.Popen(
        [sys.executable, "-m", "games.lab.playback", "--run-dir", str(run_dir), "--seat", seat],
        **kwargs,
    )
    return int(proc.pid)


def _film_view(run_dir: Path, seat: str, retry: bool) -> dict:
    manifest = _read_json(run_dir / "manifest.json") or {}
    seats = manifest.get("seats") if isinstance(manifest.get("seats"), list) else []
    seat_meta = seats[int(seat)] if int(seat) < len(seats) and isinstance(seats[int(seat)], dict) else {}
    model_id = str(seat_meta.get("model") or "")
    seat_dir = run_dir / "seats" / seat
    tape = read_tape(seat_dir / TAPE_NAME)
    view = {
        "name": seat_meta.get("name") or (tape or {}).get("name") or "",
        "color": seat_meta.get("color") or "",
        "model": model_id,
        "network": network_for(model_id) if model_id else None,
        "generation": manifest.get("generation"),
    }
    try:
        n_actions = int((tape or {}).get("n_actions") or 0)
    except (TypeError, ValueError):
        n_actions = 0
    if not compatible(tape, n_actions, manifest.get("objective")):
        view["state"] = "empty"
        return view
    actions = tape["actions"]
    view.update({
        "score": int(tape["score"]),
        "presses": len(actions),
        "world": tape.get("world"),
        "stage": tape.get("stage"),
    })
    film = seat_dir / FILM_NAME
    if film.is_file() and film_matches(_read_json(seat_dir / STAMP_NAME), tape):
        view["state"] = "ready"
        view["url"] = f"/film/{run_dir.name}/{seat}"
        return view
    current = _read_json(seat_dir / PLAY_NAME) or {}
    try:
        pid = int(current.get("pid") or 0)
    except (TypeError, ValueError):
        pid = 0
    if current.get("state") == "preparing" and _alive(pid):
        view["state"] = "preparing"
        view["frame"] = int(current.get("frame") or 0)
        view["total"] = int(current.get("total") or 0)
        return view
    if current.get("state") in {"preparing", "error"} and not retry:
        view["state"] = "error"
        view["error"] = str(current.get("error") or "the recording stopped")
        return view
        view["state"] = "error"
        view["error"] = str(current.get("error") or "the recording failed")
        return view
    if _busy_playback(seat_dir):
        view["state"] = "busy"
        return view
    pid = _start_playback(run_dir, seat)
    from games.lab.worker import atomic_json
    atomic_json(seat_dir / PLAY_NAME, {
        "state": "preparing",
        "pid": pid,
        "seat": int(seat),
        "frame": 0,
        "total": 1 + len(actions) * 4,
        "score": int(tape["score"]),
        "name": tape.get("name") or "",
        "presses": len(actions),
    })
    view["state"] = "preparing"
    view["frame"] = 0
    view["total"] = 1 + len(actions) * 4
    return view


PLAY_NAME = "play.json"


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
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, payload: bytes, content_type: str) -> None:
        header = self.headers.get("Range")
        size = len(payload)
        if not header or not header.startswith("bytes="):
            self._send(200, payload, content_type)
            return
        spec = header.removeprefix("bytes=").split(",")[0].strip()
        start_text, _, end_text = spec.partition("-")
        try:
            start = int(start_text) if start_text else 0
            end = int(end_text) if end_text else size - 1
        except ValueError:
            start, end = 0, size - 1
        if start < 0 or start >= size or end < start:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return
        end = min(end, size - 1)
        chunk = payload[start:end + 1]
        self.send_response(206)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(chunk)))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(chunk)

    def _json(self, code: int, payload) -> None:
        self._send(code, json.dumps(payload).encode(), "application/json")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/challenge":
            self._send(200, CHALLENGE_PAGE.read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/api/challenges":
            from games.lab.challenge import catalog
            self._json(200, {"challenges": catalog()})
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
            self._json(200, {
                "models": registry.describe(),
                "seats": list(SEATS),
                "defaults": default_seat_specs(),
            })
            return
        if path == "/api/status":
            current = _current()
            self._json(200, {
                "current": current,
                "hall": _hall(current),
                "ranking": generation_rank(
                    (current or {}).get("seats") or [],
                    _parent_score(current),
                    sense=_rank_sense(current),
                ),
                "practice": _practice(current),
                "hints": read_hints(runs_root() / HINTS_NAME, len(_buttons()) or None),
                "buttons": _buttons(),
                "stop_requested": stop_requested() and bool(current and current.get("running")),
                "pause_requested": pause_requested() and bool(current and current.get("running")),
                "paused": (not (round_running() or chain_running())) and read_pause() is not None,
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
        if path.startswith("/watch/"):
            rest = path.removeprefix("/watch/")
            _run_id, _, seat = rest.partition("/")
            if not _seat_index(seat):
                self._json(404, {"error": "no such seat"})
                return
            self._send(200, WATCH.read_bytes(), "text/html; charset=utf-8")
            return
        if path.startswith("/api/play/"):
            rest = path.removeprefix("/api/play/")
            run_id, _, seat = rest.partition("/")
            if not _seat_index(seat):
                self._json(404, {"error": "no such seat"})
                return
            try:
                run_dir = _safe_run(run_id)
            except KeyError:
                self._json(404, {"error": "no such round"})
                return
            retry = parse_qs(urlparse(self.path).query).get("retry", ["0"])[0] == "1"
            with _play_lock:
                self._json(200, _film_view(run_dir, seat, retry))
            return
        if path.startswith("/film/"):
            rest = path.removeprefix("/film/")
            run_id, _, seat = rest.partition("/")
            if not _seat_index(seat):
                self._json(404, {"error": "no such seat"})
                return
            try:
                run_dir = _safe_run(run_id)
            except KeyError:
                self._json(404, {"error": "no such round"})
                return
            film = run_dir / "seats" / seat / FILM_NAME
            if not film.is_file():
                self._json(404, {"error": "no recording yet"})
                return
            self._send_file(film.read_bytes(), "video/mp4")
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/stop":
            if round_running() or chain_running():
                (runs_root() / "stop.request").write_text("stop\n", encoding="utf-8")
            else:
                abandon_pause()
            self._json(200, {"ok": True})
            return
        if path == "/api/pause":
            if not (round_running() or chain_running()):
                self._json(400, {"error": "training is not running"})
                return
            (runs_root() / "pause.request").write_text("pause\n", encoding="utf-8")
            self._json(200, {"ok": True})
            return
        if path == "/api/resume":
            if round_running() or chain_running():
                self._json(400, {"error": "training is already running"})
                return
            if read_pause() is None:
                self._json(400, {"error": "nothing is paused"})
                return
            _spawn_supervisor([sys.executable, "-m", "games.lab.supervisor", "--resume-chain"])
            self._json(200, {"ok": True})
            return
        if path == "/api/hints":
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > 200_000:
                self._json(400, {"error": "bad body"})
                return
            try:
                body = json.loads(self.rfile.read(length).decode())
                store = runs_root() / HINTS_NAME
                adapter = _page_adapter()
                names = _buttons()
                n_actions = len(names) or None
                accept = getattr(adapter, "accept_hint_context", None) if adapter is not None else None
                if body.get("id"):
                    hints = change_hint(
                        store,
                        str(body["id"]),
                        enabled=None if "enabled" not in body else bool(body.get("enabled")),
                        remove=bool(body.get("remove")),
                        n_actions=n_actions,
                    )
                else:
                    actions = parse_actions(str(body.get("actions") or ""), names)
                    spec = {
                        "title": body.get("title"),
                        "note": body.get("note") or "",
                        "actions": actions,
                    }
                    if isinstance(body.get("context"), dict):
                        spec["context"] = body["context"]
                    else:
                        spec["world"] = body.get("world")
                        spec["stage"] = body.get("stage")
                    add_hint(store, spec, n_actions, accept)
                    hints = read_hints(store, n_actions)
            except (ValueError, TypeError, json.JSONDecodeError, OSError) as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(200, {"ok": True, "hints": hints})
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
                seats = default_seat_specs()
            if len(seats) != 6 or not 256 <= steps <= 5_000_000:
                raise ValueError("need six seats and a step budget from 256 to 5000000")
            if round_running() or chain_running():
                raise ValueError("training is already running")
            # Validate before detaching so the page gets the reason.
            from games.lab.catalog import by_id
            from games.lab.registry import get
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
        for name in ("stop.request", "pause.request", "pause.json"):
            path = runs_root() / name
            if path.is_file():
                path.unlink()
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


def _listen() -> ThreadingHTTPServer:
    """Dual-stack when the host has IPv6. Docker's bridge often has IPv4 only."""
    try:
        return _Server(("::", PORT), Handler)
    except OSError:
        return ThreadingHTTPServer(("0.0.0.0", PORT), Handler)


def main() -> int:
    _ignore_ctrl_c()
    server = _listen()
    print(f"Training lab at http://localhost:{PORT}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Training lab stopped by console interrupt", flush=True)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
