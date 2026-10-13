"""Play one seat's saved buttons in a separate game, at full speed.

The training seats are other processes. This one only reads the saved run and
writes a video. Sixty frames a second matches the NES; each saved button is
four of those frames.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

FRAME_SKIP = 4
PLAY_NAME = "play.json"
STAMP_NAME = "best.play.json"
FILM_NAME = "best.mp4"


def drive(actions, buttons_for, frame_skip: int, step_frame, on_frame) -> int:
    """Show every frame of the saved buttons. Returns how many frames were shown."""
    shown = 0
    for action in actions:
        buttons = buttons_for(int(action))
        for _ in range(int(frame_skip)):
            on_frame(step_frame(buttons))
            shown += 1
    return shown


def film_matches(stamp: dict | None, tape: dict | None) -> bool:
    if not isinstance(stamp, dict) or not isinstance(tape, dict):
        return False
    actions = tape.get("actions")
    if not isinstance(actions, list) or not actions:
        return False
    try:
        return (
            int(stamp.get("score")) == int(tape.get("score"))
            and int(stamp.get("presses")) == len(actions)
            and int(stamp.get("n_actions")) == int(tape.get("n_actions"))
            and int(stamp.get("frames") or 0) > 0
        )
    except (TypeError, ValueError):
        return False


def _status(path: Path, payload: dict) -> None:
    from games.lab.worker import atomic_json
    atomic_json(path, payload)


def _encode(width: int, height: int, dest: Path) -> subprocess.Popen:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is not installed")
    return subprocess.Popen(
        [
            ffmpeg, "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", "60",
            "-i", "-", "-an",
            "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23",
            "-f", "mp4", str(dest),
        ],
        stdin=subprocess.PIPE,
    )


def play_tape(run_dir: Path, seat: int) -> int:
    """Record seats/N/best.tape.json to best.mp4. Training is not this process."""
    if hasattr(os, "nice"):
        try:
            os.nice(10)
        except OSError:
            pass
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    from games.lab.tape import TAPE_NAME, compatible, read_tape
    from games.lab.worker import atomic_json

    run_dir = Path(run_dir)
    seat_dir = run_dir / "seats" / str(seat)
    status = seat_dir / PLAY_NAME
    tape = read_tape(seat_dir / TAPE_NAME)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    n_actions = int((tape or {}).get("n_actions") or 0)
    if not compatible(tape, n_actions, manifest.get("objective")):
        _status(status, {"state": "empty", "seat": seat})
        return 2
    actions = [int(action) for action in tape["actions"]]
    total = 1 + len(actions) * FRAME_SKIP
    base = {
        "state": "preparing",
        "pid": os.getpid(),
        "seat": seat,
        "frame": 0,
        "total": total,
        "score": int(tape["score"]),
        "name": tape.get("name") or "",
        "presses": len(actions),
    }
    _status(status, base)
    integration_id = manifest.get("integration")
    if not integration_id and manifest.get("system") == "nes" and manifest.get("objective") == "progress":
        integration_id = "smb_1_1"
    film = seat_dir / FILM_NAME
    # ffmpeg picks the format from the extension. ".mp4.part" is not mp4.
    partial = seat_dir / "best.part.mp4"
    env = None
    encoder = None
    frames = 0
    try:
        from games.lab.env import make_env
        from games.lab.integrations import get
        env = make_env(manifest["system"], Path(manifest["rom"]), get(integration_id), frame_skip=FRAME_SKIP)
        obs, _info = env.reset()
        runner = env.unwrapped.runner
        encoder = _encode(int(runner.width), int(runner.height), partial)

        def push(rgb) -> None:
            nonlocal frames
            encoder.stdin.write(rgb.tobytes())
            frames += 1
            if frames == 1 or frames % 30 == 0:
                _status(status, {**base, "frame": frames})

        def buttons_for(action: int):
            return set(env.unwrapped.actions[action])

        def step_frame(buttons):
            runner.frame(buttons)
            return runner.rgb

        push(obs)
        drive(actions, buttons_for, env.unwrapped.frame_skip, step_frame, push)
        encoder.stdin.close()
        encoder.stdin = None
        code = encoder.wait(timeout=180)
        if code != 0:
            raise RuntimeError(f"ffmpeg exited {code}")
        os.replace(partial, film)
        atomic_json(seat_dir / STAMP_NAME, {
            "score": int(tape["score"]),
            "presses": len(actions),
            "n_actions": n_actions,
            "frames": frames,
        })
        _status(status, {**base, "state": "ready", "frame": frames, "frames": frames})
        return 0
    except Exception as exc:
        _status(status, {**base, "state": "error", "error": str(exc), "frame": frames})
        return 1
    finally:
        if encoder is not None and encoder.poll() is None:
            if encoder.stdin is not None:
                try:
                    encoder.stdin.close()
                except OSError:
                    pass
            encoder.kill()
            encoder.wait(timeout=10)
        try:
            partial.unlink()
        except OSError:
            pass
        if env is not None:
            env.close()


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--seat", type=int, required=True)
    args = parser.parse_args(argv)
    if not 0 <= args.seat <= 5:
        return 2
    return play_tape(Path(args.run_dir), args.seat)


if __name__ == "__main__":
    sys.exit(main())
