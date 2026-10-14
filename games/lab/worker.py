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


def _clock(info: dict) -> int:
    """Time left on the step that first reached a new high score."""
    try:
        return max(int(info.get("time") or 0), 0)
    except (TypeError, ValueError):
        return 0


class SeatCallback:
    """Writes status.json, a live thumbnail, and the furthest life of this seat.

    The furthest life is seats/N/best.gif plus the weights at that moment (best.zip).
    Its buttons, through every world reached before that life died, are best.tape.json.
    A higher score replaces the run the other seats replay. The same place replaces
    it when this life got there with more time left, or in fewer presses.
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
                self.episode_actions: list[int] = []
                self.episode_scores: list[int] = []
                self.peak_world = 1
                self.peak_stage = 1
                self.peak_time = 0
                self.tape_score = 0
                self.tape_time = None
                self.tape_presses = 0
                self._stride = 2
                self._tick = 0
                self.best_flag = False
                self.episodes = 0
                self.deaths = 0
                self.last_thumb = 0.0
                self.last_save = 0.0
                self.seat_dir = seat_dir

            def _on_step(self) -> bool:
                from games.lab.paths import hold_requested
                if hold_requested():
                    return False
                infos = self.locals.get("infos") or [{}]
                info = infos[0]
                dones = self.locals.get("dones") or [False]
                if not self.episode_actions:
                    self._prepend_demonstration(info)
                try:
                    score = int(info.get("score") or 0)
                except (TypeError, ValueError):
                    score = 0
                flag = bool(info.get("flag_get"))
                applied = info.get("applied_action")
                if applied is not None:
                    try:
                        self.episode_actions.append(int(applied))
                        self.episode_scores.append(score)
                    except (TypeError, ValueError):
                        pass
                if score > self.episode_peak:
                    self.episode_peak = score
                    self.peak_time = _clock(info)
                    try:
                        self.peak_world = int(info.get("world") or 1)
                        self.peak_stage = int(info.get("stage") or 1)
                    except (TypeError, ValueError):
                        pass
                if self.episode_peak > self.best_score:
                    self.best_score = self.episode_peak
                if flag:
                    self.best_flag = True
                self._shield(info)
                # The vec env has already reset when done is true, so this rgb is the next life.
                # The info is still the life that just ended, including the button it played.
                if bool(dones[0]):
                    self.episodes += 1
                    if info.get("dead"):
                        self.deaths += 1
                    if self._saves_tape() and self._save_run():
                        self.tape_score = self.episode_peak
                        self.tape_time = self.peak_time
                        self.tape_presses = self._prefix_len()
                    if self.episode_frames and self.episode_peak > self.saved_score and self._keep():
                        self.saved_score = self.episode_peak
                        self._status()
                    self.episode_frames = []
                    self.episode_actions = []
                    self.episode_scores = []
                    self.episode_peak = 0
                    self.peak_time = 0
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
                        self._stamp(self.seat_dir / "checkpoint.zip")
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

            def _prepend_demonstration(self, info: dict) -> None:
                # These buttons were played inside reset. They belong on the saved
                # run. They are not transitions in the PPO rollout or the DQN replay.
                for item in info.get("demonstration_log") or []:
                    try:
                        action = int(item["action"])
                        score = int(item["score"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    self.episode_actions.append(action)
                    self.episode_scores.append(score)
                    if score > self.episode_peak:
                        self.episode_peak = score
                        try:
                            self.peak_time = max(int(item.get("time") or 0), 0)
                            self.peak_world = int(item.get("world") or 1)
                            self.peak_stage = int(item.get("stage") or 1)
                        except (TypeError, ValueError):
                            pass

            def _shield(self, info: dict) -> None:
                # shield_reward is a backstop for a forced step that still reached
                # learn(). RouteEnv plays the shared run inside reset, so this step
                # is the policy's own button. Zeroing the reward does not remove a
                # transition. learnable_transition is false for both PPO and DQN
                # when a step was forced, and that step stays out of step().
                from games.lab.tape import learnable_transition, shield_reward
                on_policy = getattr(self.model, "rollout_buffer", None) is not None
                shield_reward(
                    self.locals.get("rewards"),
                    self.locals.get("actions"),
                    info,
                    on_policy,
                )
                algorithm = "ppo" if on_policy else "dqn"
                if not learnable_transition(info, algorithm=algorithm):
                    rewards = self.locals.get("rewards")
                    if rewards is not None:
                        rewards[0] = 0.0

            def _prefix_len(self) -> int:
                from games.lab.tape import peak_prefix
                return len(peak_prefix(
                    self.episode_actions,
                    self.episode_scores,
                    sense=self.meta.get("sense") or "maximize",
                ))

            def _saves_tape(self) -> bool:
                from games.lab.tape import further_or_faster
                presses = self._prefix_len()
                if presses <= 0:
                    return False
                return further_or_faster(
                    self.episode_peak,
                    self.peak_time,
                    presses,
                    self.tape_score,
                    self.tape_time,
                    self.tape_presses,
                    sense=self.meta.get("sense") or "maximize",
                )

            def _save_run(self) -> bool:
                from games.lab.tape import (
                    TAPE_NAME,
                    better,
                    comparable,
                    floor_value,
                    make_tape,
                    peak_prefix,
                    publish,
                    read_tape,
                    write_tape,
                )
                prefix = peak_prefix(
                    self.episode_actions,
                    self.episode_scores,
                    sense=self.meta.get("sense") or "maximize",
                )
                n_actions = int(self.meta.get("n_actions") or 0)
                if not prefix or n_actions <= 0:
                    return False
                tape = make_tape(
                    prefix,
                    self.episode_peak,
                    self.peak_world,
                    self.peak_stage,
                    int(self.meta.get("seat") or 0),
                    str(self.meta.get("name") or ""),
                    n_actions,
                    self.meta.get("objective"),
                    scored_clear=True,
                    time=self.peak_time,
                    integration=self.meta.get("integration") or None,
                    sense=self.meta.get("sense"),
                )
                try:
                    write_tape(self.seat_dir / TAPE_NAME, tape)
                    shared = self.meta.get("tape")
                    path = Path(shared) if shared else self.seat_dir.parent.parent / TAPE_NAME
                    floor = int(self.meta.get("floor") or 0)
                    # A missing shared file still has to reach the generation's start.
                    # A file that is already there is replaced when this life went
                    # further, or reached the same place faster.
                    if read_tape(path) is None and comparable(tape) < floor_value(floor):
                        return True
                    if publish(path, tape):
                        return True
                    # A lost race against a better run is still done. A lock miss retries.
                    current = read_tape(path)
                    return current is not None and not better(tape, current)
                except (OSError, TypeError, ValueError):
                    return False

            def _keep(self) -> bool:
                try:
                    from games.lab.record import save_gif
                    save_gif(self.episode_frames, self.seat_dir / "best.gif", self._stride)
                    self.model.save(str(self.seat_dir / "best"))
                    self._stamp(self.seat_dir / "best.zip")
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

            def _stamp(self, zip_path: Path) -> None:
                stamp = self.meta.get("stamp")
                if not stamp:
                    return
                from games.lab.stamp import write_stamp
                write_stamp(zip_path, stamp)

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
    from games.lab.stamp import matches, write_stamp
    seat_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = seat_dir / "checkpoint.zip"
    stamp = meta.get("stamp")

    def fresh():
        return registry.build(model_id, env, seed), steps, True

    if resume:
        if not checkpoint.is_file():
            raise FileNotFoundError(checkpoint)
        if matches(checkpoint, stamp):
            model = registry.load(model_id, str(checkpoint), env)
            remaining = steps - int(model.num_timesteps)
            reset = False
        else:
            model, remaining, reset = fresh()
    elif seed_from is not None:
        if not Path(seed_from).is_file():
            raise FileNotFoundError(seed_from)
        if matches(Path(seed_from), stamp):
            model = registry.load(model_id, str(seed_from), env)
            model.set_random_seed(int(seed))
            remaining = steps
            reset = True
        else:
            model, remaining, reset = fresh()
    else:
        model, remaining, reset = fresh()
    callback = SeatCallback(seat_dir, meta).cb
    previous = seat_dir / "status.json"
    if previous.is_file():
        old = json.loads(previous.read_text(encoding="utf-8"))
        callback.best_score = old.get("score") or 0
        callback.saved_score = old.get("replay_score") or 0
        callback.best_flag = bool(old.get("flag"))
        callback.episodes = old.get("episodes") or 0
        callback.deaths = old.get("deaths") or 0
        callback.tape_score = callback.saved_score
    from games.lab.tape import TAPE_NAME, comparable, pace, read_tape
    existing = read_tape(seat_dir / TAPE_NAME)
    if existing is not None:
        # comparable() asks the adapter to correct a legacy file. A life that
        # does better replaces it. The same place replaces it when the new life
        # got there faster.
        callback.tape_score = max(comparable(existing), 0)
        callback.tape_time = pace(existing)
        actions = existing.get("actions")
        if isinstance(actions, list):
            callback.tape_presses = len(actions)
    try:
        if remaining > 0:
            model.learn(remaining, callback=callback, reset_num_timesteps=reset)
        model.save(str(seat_dir / "checkpoint"))
        if stamp:
            write_stamp(seat_dir / "checkpoint.zip", stamp)
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
    from games.lab.paths import hold_requested
    # A seat relaunched after Stop or Pause must exit before it builds a new env.
    if hold_requested():
        return 0

    from games.lab.contract import SURVIVAL_SENSE, sense_of
    from games.lab.env import RouteEnv, make_env
    from games.lab.lineage import champion
    from games.lab.registry import get
    from games.lab.paths import runs_root
    from games.lab.hints import HINTS_NAME
    from games.lab.tape import TAPE_NAME, parent_floor, seed_run
    integration = get(args.integration or None)
    env = make_env(args.system, Path(args.rom), integration)
    seat_dir = Path(args.seat_dir)
    n_actions = int(env.action_space.n)
    meta = {
        "seat": args.seat,
        "name": args.name,
        "color": args.color,
        "model": args.model,
        "seed": args.seed,
        "objective": args.objective,
        "n_actions": n_actions,
        "tape": str(seat_dir.parent.parent / TAPE_NAME),
        "integration": integration.id if integration is not None else "",
        "sense": sense_of(integration) if integration is not None else SURVIVAL_SENSE,
    }
    if integration is not None and hasattr(integration, "stamp"):
        meta["stamp"] = integration.stamp()
    floor = parent_floor(seat_dir.parent.parent)
    if floor == 0:
        found = champion(runs_root(), args.model, meta.get("stamp"), sense=meta["sense"])
        floor = int(found["score"]) if found else 0
    meta["floor"] = floor
    # The supervisor process may have started before this rule existed. Copy here
    # as well, so a run that reaches the parent score is practiced.
    seed_run(seat_dir.parent.parent, runs_root(), n_actions, args.objective, floor)
    env = RouteEnv(
        env,
        seat_dir.parent.parent / TAPE_NAME,
        n_actions,
        args.objective,
        floor,
        runs_root() / HINTS_NAME,
    )
    seed_from = Path(args.seed_from) if args.seed_from else None
    train(env, args.model, args.seed, args.steps, seat_dir, meta, args.resume, seed_from)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
