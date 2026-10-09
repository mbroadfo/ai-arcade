"""One seat. Trains in chunks of the library's own loop and overwrites a single thumbnail."""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")


def atomic_json(path: Path, data: dict) -> None:
    """Write JSON by replace. Retry when Windows has the destination open."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    delay = 0.02
    for _ in range(8):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(delay)
            delay = min(delay * 2, 0.2)
    os.replace(tmp, path)


def base_gym(vec):
    while hasattr(vec, "venv"):
        vec = vec.venv
    return vec.envs[0]


class SeatCallback:
    """Writes status.json, a live thumbnail, and the furthest life of this seat.

    The furthest life is seats/N/best.gif plus the weights at that moment (best.zip).
    The periodic checkpoint is the latest policy, which can walk the wrong way.
    """

    def __init__(self, seat_dir: Path, meta: dict):
        from stable_baselines3.common.callbacks import BaseCallback
        self._base = BaseCallback

        class _Cb(BaseCallback):
            def __init__(self):
                super().__init__()
                self.meta = meta
                self.best_score = 0
                self.saved_score = 0
                self.episode_peak = 0
                self.episode_frames: list = []
                self._stride = 2
                self._tick = 0
                self.best_flag = False
                self.episodes = 0
                self.deaths = 0
                self.last_thumb = 0.0
                self.last_save = 0.0
                self.seat_dir = seat_dir

            def _on_step(self) -> bool:
                infos = self.locals.get("infos") or [{}]
                info = infos[0]
                dones = self.locals.get("dones") or [False]
                try:
                    score = int(info.get("score") or 0)
                except (TypeError, ValueError):
                    score = 0
                flag = bool(info.get("flag_get"))
                if score > self.episode_peak:
                    self.episode_peak = score
                if self.episode_peak > self.best_score:
                    self.best_score = self.episode_peak
                if flag:
                    self.best_flag = True
                # The vec env has already reset when done is true, so this rgb is the next life.
                if bool(dones[0]):
                    self.episodes += 1
                    if info.get("dead") and not flag:
                        self.deaths += 1
                    if self.episode_frames and self.episode_peak > self.saved_score and self._keep():
                        self.saved_score = self.episode_peak
                        self._status()
                    self.episode_frames = []
                    self.episode_peak = 0
                    self._stride = 2
                    self._tick = 0
                self._capture()
                now = time.time()
                if now - self.last_thumb >= 0.1:
                    self.last_thumb = now
                    self._thumb()
                    self._status()
                if now - self.last_save >= 30:
                    self.last_save = now
                    try:
                        self.model.save(str(self.seat_dir / "checkpoint"))
                    except OSError:
                        pass
                return True

            def _capture(self) -> None:
                # Every other agent step. A full 256x240 copy on every step across six seats
                # is hundreds of megabytes a second, and the window is still smooth at this rate.
                self._tick += 1
                if self._tick % self._stride:
                    return
                try:
                    frame = base_gym(self.model.get_env()).unwrapped.runner.rgb
                except Exception:
                    return
                if frame is None:
                    return
                self.episode_frames.append(frame.copy())
                if len(self.episode_frames) > 480:
                    self.episode_frames = self.episode_frames[::2]
                    self._stride *= 2

            def _keep(self) -> bool:
                try:
                    from games.lab.record import save_gif
                    save_gif(self.episode_frames, self.seat_dir / "best.gif", self._stride)
                    self.model.save(str(self.seat_dir / "best"))
                    return True
                except Exception:
                    return False

            def _thumb(self) -> None:
                try:
                    from PIL import Image
                    frame = base_gym(self.model.get_env()).unwrapped.runner.rgb
                    if frame is None:
                        return
                    dest = self.seat_dir / "latest.jpg"
                    tmp = self.seat_dir / "latest.jpg.tmp"
                    # The temp name ends in .tmp. Pillow will not guess JPEG from that.
                    Image.fromarray(frame).save(tmp, format="JPEG", quality=70)
                    os.replace(tmp, dest)
                except Exception:
                    return

            def _status(self) -> None:
                try:
                    atomic_json(self.seat_dir / "status.json", {
                        **self.meta,
                        "steps": int(self.num_timesteps),
                        "episodes": self.episodes,
                        "deaths": self.deaths,
                        "score": self.best_score,
                        "replay_score": self.saved_score,
                        "flag": self.best_flag,
                        "finished": False,
                    })
                except OSError:
                    return

        self.cb = _Cb()


def train(
    env,
    model_id: str,
    seed: int,
    steps: int,
    seat_dir: Path,
    meta: dict,
    resume: bool,
    seed_from: Path | None = None,
) -> dict:
    """Resume continues a checkpoint. seed_from loads record-life weights and trains a full budget."""
    if seed_from is not None and resume:
        raise ValueError("pass seed-from or resume, not both")
    from games.lab.models import registry
    seat_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = seat_dir / "checkpoint.zip"
    if resume:
        if not checkpoint.is_file():
            raise FileNotFoundError(checkpoint)
        model = registry.load(model_id, str(checkpoint), env)
        remaining = steps - int(model.num_timesteps)
        reset = False
    elif seed_from is not None:
        if not Path(seed_from).is_file():
            raise FileNotFoundError(seed_from)
        model = registry.load(model_id, str(seed_from), env)
        model.set_random_seed(int(seed))
        remaining = steps
        reset = True
    else:
        model = registry.build(model_id, env, seed)
        remaining = steps
        reset = True
    callback = SeatCallback(seat_dir, meta).cb
    previous = seat_dir / "status.json"
    if previous.is_file():
        old = json.loads(previous.read_text(encoding="utf-8"))
        callback.best_score = old.get("score") or 0
        callback.saved_score = old.get("replay_score") or 0
        callback.best_flag = bool(old.get("flag"))
        callback.episodes = old.get("episodes") or 0
        callback.deaths = old.get("deaths") or 0
    try:
        if remaining > 0:
            model.learn(remaining, callback=callback, reset_num_timesteps=reset)
        model.save(str(seat_dir / "checkpoint"))
    finally:
        env.close()
    # learn() may not have fired the callback if remaining was 0. Write the final line either way.
    info = {
        **meta,
        "steps": int(getattr(model, "num_timesteps", steps)),
        "episodes": callback.episodes,
        "deaths": callback.deaths,
        "score": callback.best_score,
        "replay_score": callback.saved_score,
        "flag": callback.best_flag,
        "finished": True,
    }
    atomic_json(seat_dir / "status.json", info)
    return info


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train one seat")
    parser.add_argument("--system", required=True)
    parser.add_argument("--rom", required=True)
    parser.add_argument("--integration", default="")
    parser.add_argument("--model", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--steps", type=int, required=True)
    parser.add_argument("--seat-dir", required=True)
    parser.add_argument("--seat", type=int, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--color", required=True)
    parser.add_argument("--objective", required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--seed-from", default="")
    args = parser.parse_args(argv)

    from games.lab.env import make_env
    from games.lab.integrations import get
    integration = get(args.integration or None)
    env = make_env(args.system, Path(args.rom), integration)
    meta = {
        "seat": args.seat,
        "name": args.name,
        "color": args.color,
        "model": args.model,
        "seed": args.seed,
        "objective": args.objective,
    }
    seed_from = Path(args.seed_from) if args.seed_from else None
    train(env, args.model, args.seed, args.steps, Path(args.seat_dir), meta, args.resume, seed_from)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
