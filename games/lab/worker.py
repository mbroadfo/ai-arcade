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
    """Time left on the step being recorded."""
    try:
        return max(int(info.get("time") or 0), 0)
    except (TypeError, ValueError):
        return 0


def _metric(info: dict) -> int:
    try:
        return int(info.get("score") or 0)
    except (TypeError, ValueError):
        return 0


class LifeTracker:
    """Decides which life to keep. This class does not import a learning library.

    Maximize keeps the high-water mark and the buttons that reached it.
    Minimize keeps the finished episode. The first finished episode is the
    mark until a later episode beats it. A floor of 0 does not block sharing.
    """

    def __init__(self, seat_dir: Path, meta: dict):
        self.seat_dir = Path(seat_dir)
        self.meta = meta
        named = meta.get("sense")
        self.sense = named if named in ("maximize", "minimize") else "maximize"
        self.minimize = self.sense == "minimize"
        self.best_score = None if self.minimize else 0
        self.saved_score = None if self.minimize else 0
        self.episode_mark = None if self.minimize else 0
        self.episode_actions: list[int] = []
        self.episode_scores: list[int] = []
        self.mark_world = None
        self.mark_stage = None
        self.mark_context = None
        self.mark_time = 0
        self.tape_score = None if self.minimize else 0
        self.tape_time = None
        self.tape_presses = 0
        self.best_flag = False
        self.episodes = 0
        self.deaths = 0

    def published_score(self):
        if self.best_score is None:
            return None if self.minimize else 0
        return int(self.best_score)

    def published_replay(self):
        if self.saved_score is None:
            return None if self.minimize else 0
        return int(self.saved_score)

    def status(self, steps: int, finished: bool) -> dict:
        return {
            **self.meta,
            "steps": int(steps),
            "episodes": self.episodes,
            "deaths": self.deaths,
            "score": self.published_score(),
            "replay_score": self.published_replay(),
            "flag": self.best_flag,
            "finished": bool(finished),
        }

    def restore(self, status: dict | None, tape: dict | None) -> None:
        """Continue a maximize seat from the numbers it already wrote.

        A minimize seat with no finished episode does not treat a stored 0
        as a completed time.
        """
        if isinstance(status, dict):
            try:
                self.episodes = int(status.get("episodes") or 0)
            except (TypeError, ValueError):
                self.episodes = 0
            try:
                self.deaths = int(status.get("deaths") or 0)
            except (TypeError, ValueError):
                self.deaths = 0
            self.best_flag = bool(status.get("flag"))
            if self.minimize:
                if self.episodes > 0 and status.get("score") is not None:
                    try:
                        self.best_score = int(status["score"])
                    except (TypeError, ValueError):
                        self.best_score = None
                if self.episodes > 0 and status.get("replay_score") is not None:
                    try:
                        self.saved_score = int(status["replay_score"])
                    except (TypeError, ValueError):
                        self.saved_score = None
            else:
                self.best_score = status.get("score") or 0
                self.saved_score = status.get("replay_score") or 0
                self.tape_score = self.saved_score
        if isinstance(tape, dict):
            from games.lab.tape import comparable, pace
            score = comparable(tape)
            if self.minimize:
                if score >= 0:
                    self.tape_score = score
            else:
                self.tape_score = max(score, 0)
            self.tape_time = pace(tape)
            actions = tape.get("actions")
            if isinstance(actions, list):
                self.tape_presses = len(actions)

    def record(self, info: dict) -> None:
        if not self.episode_actions:
            self._prepend(info)
        score = _metric(info)
        applied = info.get("applied_action")
        if applied is not None:
            try:
                self.episode_actions.append(int(applied))
                self.episode_scores.append(score)
            except (TypeError, ValueError):
                pass
        if self.minimize:
            self._note_flag(info)
            return
        if score > self.episode_mark:
            self.episode_mark = score
            self.mark_time = _clock(info)
            self._remember(info)
        if self.episode_mark > self.best_score:
            self.best_score = self.episode_mark
        self._note_flag(info)

    def close(self, info: dict, keep) -> bool:
        """Commit the episode. keep() saves a film and weights when it returns true."""
        self.episodes += 1
        if info.get("dead"):
            self.deaths += 1
        if self.minimize:
            if self.episode_scores:
                self.episode_mark = self.episode_scores[-1]
            else:
                self.episode_mark = _metric(info)
            self.mark_time = _clock(info)
            self._remember(info)
            if self._improved(self.episode_mark, self.best_score):
                self.best_score = self.episode_mark
        if self._saves() and self._save_run():
            self.tape_score = int(self.episode_mark)
            self.tape_time = int(self.mark_time)
            self.tape_presses = len(self._kept_actions())
        kept_film = False
        if self._improved(self.episode_mark, self.saved_score) and keep():
            self.saved_score = self.episode_mark
            kept_film = True
        self.episode_actions = []
        self.episode_scores = []
        self.episode_mark = None if self.minimize else 0
        self.mark_time = 0
        self.mark_world = None
        self.mark_stage = None
        self.mark_context = None
        return kept_film

    def _note_flag(self, info: dict) -> None:
        if "flag_get" in info and info.get("flag_get"):
            self.best_flag = True

    def _remember(self, info: dict) -> None:
        for key, attr in (("world", "mark_world"), ("stage", "mark_stage")):
            if key not in info or info.get(key) is None:
                continue
            try:
                setattr(self, attr, int(info[key]))
            except (TypeError, ValueError):
                continue
        context = info.get("context")
        if isinstance(context, dict):
            self.mark_context = dict(context)

    def _prepend(self, info: dict) -> None:
        # These buttons were played inside reset. They belong on the saved run.
        for item in info.get("demonstration_log") or []:
            try:
                action = int(item["action"])
                score = int(item["score"])
            except (KeyError, TypeError, ValueError):
                continue
            self.episode_actions.append(action)
            self.episode_scores.append(score)
            if self.minimize or score <= self.episode_mark:
                continue
            self.episode_mark = score
            try:
                self.mark_time = max(int(item.get("time") or 0), 0)
            except (TypeError, ValueError):
                self.mark_time = 0
            self._remember(item)

    def _improved(self, score, incumbent) -> bool:
        if score is None:
            return False
        if incumbent is None:
            return True
        from games.lab.contract import better
        return better(self.sense, score, incumbent)

    def _kept_actions(self) -> list[int]:
        if self.minimize:
            return [int(action) for action in self.episode_actions]
        from games.lab.tape import peak_prefix
        return peak_prefix(self.episode_actions, self.episode_scores, sense=self.sense)

    def _saves(self) -> bool:
        from games.lab.tape import further_or_faster
        actions = self._kept_actions()
        if not actions or self.episode_mark is None:
            return False
        if self.tape_score is None:
            return True
        return further_or_faster(
            int(self.episode_mark),
            int(self.mark_time),
            len(actions),
            int(self.tape_score),
            self.tape_time,
            self.tape_presses,
            sense=self.sense,
        )

    def _short_of_floor(self, score: int) -> bool:
        from games.lab.tape import floor_value
        try:
            floor = int(self.meta.get("floor") or 0)
        except (TypeError, ValueError):
            floor = 0
        bar = floor_value(floor)
        if self.minimize:
            if bar == 0:
                return False
            return int(score) > bar
        return int(score) < bar

    def _save_run(self) -> bool:
        from games.lab.tape import (
            TAPE_NAME,
            better,
            comparable,
            make_tape,
            publish,
            read_tape,
            write_tape,
        )
        actions = self._kept_actions()
        try:
            n_actions = int(self.meta.get("n_actions") or 0)
        except (TypeError, ValueError):
            n_actions = 0
        if not actions or n_actions <= 0 or self.episode_mark is None:
            return False
        tape = make_tape(
            actions,
            int(self.episode_mark),
            self.mark_world,
            self.mark_stage,
            int(self.meta.get("seat") or 0),
            str(self.meta.get("name") or ""),
            n_actions,
            self.meta.get("objective"),
            scored_clear=True,
            time=int(self.mark_time),
            integration=self.meta.get("integration") or None,
            sense=self.sense,
            context=self.mark_context,
        )
        try:
            write_tape(self.seat_dir / TAPE_NAME, tape)
            shared = self.meta.get("tape")
            path = Path(shared) if shared else self.seat_dir.parent.parent / TAPE_NAME
            # A missing shared file still has to reach the generation's start.
            # A file that is already there is replaced when this life did better.
            if read_tape(path) is None and self._short_of_floor(comparable(tape)):
                return True
            if publish(path, tape):
                return True
            current = read_tape(path)
            return current is not None and not better(tape, current)
        except (OSError, TypeError, ValueError):
            return False


class SeatCallback:
    """Writes status.json, a live thumbnail, and the furthest life of this seat.

    The furthest life is seats/N/best.gif plus the weights at that moment (best.zip).
    Its buttons are best.tape.json. A better metric replaces the run the other
    seats replay. The same place replaces it when this life got there with more
    time left, or in fewer presses. The periodic checkpoint is the latest policy.
    """

    def __init__(self, seat_dir: Path, meta: dict):
        from stable_baselines3.common.callbacks import BaseCallback
        self._base = BaseCallback
        life = LifeTracker(seat_dir, meta)

        class _Cb(BaseCallback):
            def __init__(self):
                super().__init__()
                self.meta = meta
                self.life = life
                self.episode_frames: list = []
                self._stride = 2
                self._tick = 0
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
                self.life.record(info)
                self._shield(info)
                # The vec env has already reset when done is true, so this rgb is the next life.
                # The info is still the life that just ended, including the button it played.
                if bool(dones[0]):
                    def keep() -> bool:
                        if not self.episode_frames:
                            return False
                        return self._keep()

                    if self.life.close(info, keep):
                        self._status()
                    self.episode_frames = []
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
                    atomic_json(
                        self.seat_dir / "status.json",
                        self.life.status(int(self.num_timesteps), finished=False),
                    )
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
    old = json.loads(previous.read_text(encoding="utf-8")) if previous.is_file() else None
    from games.lab.tape import TAPE_NAME, read_tape
    # comparable() asks the adapter to correct a legacy file. A life that
    # does better replaces it. The same place replaces it when the new life
    # got there faster.
    callback.life.restore(old, read_tape(seat_dir / TAPE_NAME))
    try:
        if remaining > 0:
            model.learn(remaining, callback=callback, reset_num_timesteps=reset)
        model.save(str(seat_dir / "checkpoint"))
        if stamp:
            write_stamp(seat_dir / "checkpoint.zip", stamp)
    finally:
        env.close()
    # learn() may not have fired the callback if remaining was 0. Write the final line either way.
    info = callback.life.status(int(getattr(model, "num_timesteps", steps)), finished=True)
    atomic_json(seat_dir / "status.json", info)
    return info


def practice(env, steps: int, seat_dir: Path, meta: dict, policy) -> dict:
    """Step a stub policy and save the tape. No checkpoint and no training library."""
    from games.lab.paths import hold_requested
    seat_dir = Path(seat_dir)
    seat_dir.mkdir(parents=True, exist_ok=True)
    life = LifeTracker(seat_dir, meta)
    obs, info = env.reset()
    taken = 0
    limit = max(int(steps), 0)
    while taken < limit:
        if hold_requested():
            break
        try:
            action = int(policy(obs, info))
        except (TypeError, ValueError):
            action = 0
        obs, _reward, terminated, truncated, info = env.step(action)
        info = dict(info)
        if info.get("applied_action") is None:
            info["applied_action"] = action
        taken += 1
        done = bool(terminated or truncated)
        life.record(info)
        if done:
            life.close(info, keep=lambda: False)
            if taken < limit:
                obs, info = env.reset()
    close = getattr(env, "close", None)
    if callable(close):
        close()
    payload = life.status(taken, finished=True)
    atomic_json(seat_dir / "status.json", payload)
    return payload


def _seat_meta(args, integration, n_actions: int, floor: int) -> dict:
    from games.lab.contract import SURVIVAL_SENSE, sense_of
    from games.lab.tape import TAPE_NAME
    seat_dir = Path(args.seat_dir)
    return {
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
        "floor": int(floor),
    }


def _practice_entry(args) -> int:
    """The production entry for a short adapter run. It does not import the trainer."""
    from games.lab.registry import get
    integration = get(args.integration or None)
    opener = getattr(integration, "open_env", None)
    if integration is None or not callable(opener):
        raise SystemExit("practice needs an adapter that opens an environment")
    env = opener(args.rom)
    actions = getattr(integration, "actions", None)
    n_actions = len(actions) if isinstance(actions, (list, tuple)) else 0
    choose = getattr(integration, "practice_policy", None)
    if not callable(choose):
        def choose(_obs, _info):
            return 0
    practice(env, args.steps, Path(args.seat_dir), _seat_meta(args, integration, n_actions, 0), choose)
    return 0


def _train_entry(args) -> int:
    from games.lab.env import RouteEnv, make_env
    from games.lab.lineage import champion
    from games.lab.registry import get
    from games.lab.paths import runs_root
    from games.lab.hints import HINTS_NAME
    from games.lab.tape import TAPE_NAME, parent_floor, seed_run
    integration = get(args.integration or None)
    if integration is not None and callable(getattr(integration, "open_env", None)):
        env = integration.open_env(args.rom)
    else:
        env = make_env(args.system, Path(args.rom), integration)
    seat_dir = Path(args.seat_dir)
    n_actions = int(env.action_space.n)
    floor = parent_floor(seat_dir.parent.parent)
    meta = _seat_meta(args, integration, n_actions, floor)
    if integration is not None and hasattr(integration, "stamp"):
        meta["stamp"] = integration.stamp()
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
    parser.add_argument("--practice", action="store_true")
    args = parser.parse_args(argv)
    from games.lab.paths import hold_requested
    # A seat relaunched after Stop or Pause must exit before it builds a new env.
    if hold_requested():
        return 0
    if args.practice:
        return _practice_entry(args)
    return _train_entry(args)


if __name__ == "__main__":
    raise SystemExit(main())
