"""The button run every seat replays.

Weights stay with the model that learned them. The run is the buttons of the
life that went furthest, through every world reached before that life died.
The same savestate plus those buttons repeats the route, including a clear
into the next world. A later life that goes further replaces the run. The same
place replaces it when that life got there with more time left, or in fewer presses.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

TAPE_NAME = "best.tape.json"
# One life in eight plays its own buttons, so a faster route can replace the shared run.
SEARCH_EVERY = 8


def as_int(value) -> int:
    if isinstance(value, bool):
        raise TypeError("a button index is not a flag")
    if isinstance(value, (list, tuple)):
        return as_int(value[0])
    reshape = getattr(value, "reshape", None)
    if reshape is not None:
        return int(value.reshape(-1)[0])
    return int(value)


def make_tape(
    actions,
    score: int,
    world: int,
    stage: int,
    seat: int,
    name: str,
    n_actions: int,
    objective: str | None,
    scored_clear: bool = False,
    time: int | None = None,
    integration: str | None = None,
    sense: str | None = None,
) -> dict:
    tape = {
        "actions": [int(action) for action in actions],
        "score": int(score),
        "world": int(world),
        "stage": int(stage),
        "seat": int(seat),
        "name": name,
        "n_actions": int(n_actions),
        "objective": objective,
    }
    if integration:
        tape["integration"] = integration
    if sense:
        tape["sense"] = sense
    # scored_clear means the adapter already counted a finished stage.
    # Older files lack this mark. The adapter may correct those.
    if scored_clear:
        tape["scored_clear"] = True
    # Clock remaining at the first step that reached this score. Older files omit it.
    if time is not None:
        tape["time"] = max(int(time), 0)
    return tape


def read_tape(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_tape(path: Path, tape: dict) -> None:
    from games.lab.worker import atomic_json
    atomic_json(path, tape)


def compatible(tape: dict | None, n_actions: int, objective: str | None = None) -> bool:
    """A run from another button list or another score is not playable here."""
    if not isinstance(tape, dict):
        return False
    actions = tape.get("actions")
    if not isinstance(actions, list) or not actions:
        return False
    try:
        declared = int(tape.get("n_actions"))
    except (TypeError, ValueError):
        return False
    if declared != int(n_actions):
        return False
    if objective is not None and tape.get("objective") not in (None, objective):
        return False
    for action in actions:
        if isinstance(action, bool) or not isinstance(action, int):
            return False
        if action < 0 or action >= n_actions:
            return False
    try:
        int(tape.get("score"))
    except (TypeError, ValueError):
        return False
    return True


def comparable(tape: dict | None) -> int:
    """How far a saved run got, after the owning adapter corrects legacy files."""
    if not isinstance(tape, dict):
        return -1
    try:
        score = int(tape.get("score"))
    except (TypeError, ValueError):
        return -1
    if tape.get("scored_clear"):
        return score
    from games.lab.registry import owner_of
    adapter = owner_of(tape)
    hook = getattr(adapter, "correct_progress", None) if adapter else None
    if not callable(hook):
        return score
    try:
        return int(hook(tape, score))
    except (TypeError, ValueError):
        return score


def floor_value(floor: int) -> int:
    """The score a generation has to reach before its shared run is practiced.

    An adapter may correct a legacy floor. A number it does not recognize is unchanged.
    """
    try:
        floor = int(floor)
    except (TypeError, ValueError):
        return 0
    from games.lab.registry import registered
    for adapter in registered():
        hook = getattr(adapter, "correct_floor", None)
        if not callable(hook):
            continue
        try:
            corrected = hook(floor)
        except (TypeError, ValueError):
            continue
        if corrected is not None:
            return int(corrected)
    return max(floor, 0)


def pace(tape: dict | None) -> int | None:
    """Clock remaining when the run first reached its furthest point.

    Older files have no clock. They are not compared on time. Fewer presses
    is the speed signal for those files.
    """
    if not isinstance(tape, dict) or "time" not in tape:
        return None
    try:
        value = tape.get("time")
        if value is None:
            return None
        return max(int(value), 0)
    except (TypeError, ValueError):
        return None


def _presses(tape: dict | None) -> int:
    if not isinstance(tape, dict):
        return 10**9
    actions = tape.get("actions")
    if not isinstance(actions, list):
        return 10**9
    return len(actions)


def further_or_faster(
    score: int,
    clock: int,
    presses: int,
    saved_score: int,
    saved_clock: int | None,
    saved_presses: int,
    *,
    sense: str = "maximize",
) -> bool:
    """A life replaces the saved run when it did better, or as well and faster.

    sense comes from the adapter. At the same metric, more time left wins when
    both runs recorded a clock. Otherwise fewer presses is the faster one.
    A missing clock does not lose to a timed run that took more presses.
    """
    from games.lab.contract import better
    if better(sense, score, saved_score):
        return True
    if score != saved_score:
        return False
    if saved_clock is not None and clock != saved_clock:
        return clock > saved_clock
    return presses < saved_presses


def _tape_sense(tape: dict | None) -> str:
    if isinstance(tape, dict) and tape.get("sense") in ("maximize", "minimize"):
        return tape["sense"]
    from games.lab.registry import owner_of
    from games.lab.contract import sense_of
    return sense_of(owner_of(tape)) or "maximize"


def better(a: dict | None, b: dict | None) -> bool:
    """True when a should replace b."""
    if not isinstance(a, dict):
        return False
    clock = pace(a)
    sense = _tape_sense(a)
    if isinstance(b, dict):
        saved_score = comparable(b)
    else:
        saved_score = 10**12 if sense == "minimize" else -1
    return further_or_faster(
        comparable(a),
        0 if clock is None else clock,
        _presses(a),
        saved_score,
        pace(b) if isinstance(b, dict) else None,
        _presses(b) if isinstance(b, dict) else 10**9,
        sense=sense,
    )


def search_life(life: int, every: int = SEARCH_EVERY) -> bool:
    """True on every Nth life, counted from 1. That life plays its own buttons."""
    try:
        life = int(life)
        every = int(every)
    except (TypeError, ValueError):
        return False
    return every > 0 and life > 0 and life % every == 0


def peak_prefix(actions: list[int], scores: list[int], *, sense: str = "maximize") -> list[int]:
    """Buttons through the best metric this life reached.

    Anything after that step is the life falling apart. Replaying it would
    repeat the failure. sense is the adapter's comparison.
    """
    from games.lab.contract import better
    if not actions or not scores:
        return []
    limit = min(len(actions), len(scores))
    best = scores[0]
    at = 0
    for index in range(limit):
        if better(sense, scores[index], best):
            best = scores[index]
            at = index
    return [int(action) for action in actions[: at + 1]]


def applied_action(
    tape: dict | None,
    index: int,
    agent_action,
    n_actions: int,
    objective: str | None = None,
) -> tuple[int, bool]:
    """The shared run supplies the button until it runs out. Then the policy does."""
    agent = as_int(agent_action)
    if compatible(tape, n_actions, objective) and 0 <= index < len(tape["actions"]):
        return int(tape["actions"][index]), True
    return agent, False


def shield_reward(rewards, actions, info: dict | None, on_policy: bool) -> None:
    """A scripted press must not train whatever button the policy sampled instead.

    The life still follows the shared run. When the sample disagrees, that
    sample's reward becomes zero so the weight update does not treat the wrong
    press as the reason the score went up. A sample that matches keeps the reward.
    """
    if not on_policy or rewards is None or not info or not info.get("forced"):
        return
    try:
        chosen = as_int(actions)
        applied = as_int(info.get("applied_action"))
    except (TypeError, ValueError, IndexError):
        return
    if chosen != applied:
        rewards[0] = 0.0


def learnable_transition(info: dict | None, *, algorithm: str) -> bool:
    """False when a tape or a hint played this step.

    PPO and DQN both skip that step. Zeroing the reward is not enough: the next
    state still came from the external button, so the transition does not belong
    in either buffer. The shared run is played before the policy steps.
    """
    if algorithm not in {"ppo", "dqn"}:
        raise ValueError(algorithm)
    if not info:
        return True
    return not bool(info.get("forced"))


class Route:
    """Which button is played. RouteEnv is the gym wrapper around this.

    A run below min_score is a shorter life. Replaying it pulls every seat back.
    A run that reaches min_score is the best practice so far, so the life plays
    it and then the policy continues. A hint plays after that run, in its stage.
    """

    def __init__(
        self,
        tape_path: Path,
        n_actions: int,
        objective: str | None,
        min_score: int = 0,
        hints_path: Path | None = None,
    ):
        self.tape_path = Path(tape_path)
        self.n_actions = int(n_actions)
        self.objective = objective
        self.min_score = int(min_score)
        self.hints_path = None if hints_path is None else Path(hints_path)
        self._tape: dict | None = None
        self._index = 0
        self._hints: list = []
        self._hint_i = 0
        self._hint_where = None
        self._search = False

    def _reload(self) -> None:
        tape = read_tape(self.tape_path)
        if not compatible(tape, self.n_actions, self.objective):
            return
        score = comparable(tape)
        if score <= 0 or score < floor_value(self.min_score):
            return
        if self._tape is None or better(tape, self._tape):
            self._tape = tape

    def _load_hints(self) -> None:
        from games.lab.hints import read_hints
        if self.hints_path is None:
            self._hints = []
            return
        self._hints = read_hints(self.hints_path, self.n_actions)

    def on_reset(self, search: bool = False) -> None:
        self._index = 0
        self._hint_i = 0
        self._hint_where = None
        self._search = bool(search)
        if not self._search:
            self._reload()
        self._load_hints()

    def on_step(self, agent_action, world=None, stage=None) -> tuple[int, bool]:
        # The previous life publishes its run from the step callback, which runs
        # after reset and before this life presses anything. Pick that up here.
        # A search life keeps its own buttons for the whole life.
        from games.lab.hints import hint_button
        if self._index == 0 and not self._search:
            self._reload()
            self._load_hints()
        if self._search:
            self._index += 1
            return as_int(agent_action), False
        applied, forced = applied_action(
            self._tape, self._index, agent_action, self.n_actions, self.objective
        )
        self._index += 1
        where = _stage(world, stage)
        if not forced and self._hints and where is not None:
            if where != self._hint_where:
                self._hint_where = where
                self._hint_i = 0
            button = hint_button(self._hints, where[0], where[1], self._hint_i, self.n_actions)
            if button is not None:
                applied, forced = button, True
                self._hint_i += 1
        return applied, forced

    def peek_action(self, agent_action, world=None, stage=None) -> tuple[int, bool]:
        """The button on_step would play. The run index and the hint index stay put."""
        from games.lab.hints import hint_button
        if self._search:
            return as_int(agent_action), False
        applied, forced = applied_action(
            self._tape, self._index, agent_action, self.n_actions, self.objective
        )
        if forced:
            return applied, True
        where = _stage(world, stage)
        if self._hints and where is not None:
            hint_i = 0 if where != self._hint_where else self._hint_i
            button = hint_button(self._hints, where[0], where[1], hint_i, self.n_actions)
            if button is not None:
                return button, True
        return applied, False


def take_demonstration(route: Route, place, act=None) -> list[int]:
    """Buttons of the shared run, then a hint for the stage those buttons reach.

    place() returns the world and stage now. act(button) plays that button and
    returns False when the life ended. The policy button is not included.
    A search life returns an empty list. The cap stops a hint that never ends.
    """
    if getattr(route, "_search", False):
        return []
    played: list[int] = []
    for _ in range(100_000):
        if route._index == 0 and not route._search:
            route._reload()
            route._load_hints()
        try:
            world, stage = place()
        except Exception:
            world, stage = None, None
        _button, forced = route.peek_action(0, world, stage)
        if not forced:
            break
        applied, forced = route.on_step(0, world, stage)
        if not forced:
            break
        played.append(int(applied))
        if act is not None and act(int(applied)) is False:
            break
    return played


def _stage(world, stage):
    if world is None or stage is None:
        return None
    try:
        return (int(world), int(stage))
    except (TypeError, ValueError):
        return None


def _acquire(path: Path):
    lock_path = path.with_name(path.name + ".lock")
    deadline = time.time() + 2.0
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            return fd, lock_path
        except FileExistsError:
            try:
                stale = time.time() - lock_path.stat().st_mtime > 30
            except OSError:
                stale = False
            if stale:
                try:
                    lock_path.unlink()
                except OSError:
                    pass
                continue
            if time.time() > deadline:
                raise TimeoutError(lock_path)
            time.sleep(0.01)


def publish(path: Path, tape: dict) -> bool:
    """Share this run when it went further, or reached the same place faster."""
    try:
        n_actions = int(tape.get("n_actions"))
    except (TypeError, ValueError):
        return False
    if not compatible(tape, n_actions, tape.get("objective")):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd, lock_path = _acquire(path)
    except TimeoutError:
        return False
    try:
        current = read_tape(path)
        if compatible(current, n_actions, tape.get("objective")) and not better(tape, current):
            return False
        write_tape(path, tape)
        return True
    finally:
        os.close(fd)
        try:
            lock_path.unlink()
        except OSError:
            pass


def best_saved(
    root: Path,
    n_actions: int,
    objective: str | None,
    exclude: Path | None = None,
) -> dict | None:
    """The furthest compatible run already saved under the runs root."""
    best: dict | None = None
    if not root.is_dir():
        return None
    paths = list(root.glob("*/" + TAPE_NAME))
    paths.extend(root.glob("*/seats/*/" + TAPE_NAME))
    exclude = exclude.resolve() if exclude is not None else None
    for path in paths:
        if exclude is not None:
            resolved = path.resolve()
            if resolved == exclude or exclude in resolved.parents:
                continue
        tape = read_tape(path)
        if not compatible(tape, n_actions, objective):
            continue
        if best is None or better(tape, best):
            best = tape
    return best


def parent_floor(run_dir: Path) -> int:
    """The score this generation started from. A shared run has to reach it."""
    path = Path(run_dir) / "manifest.json"
    if not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(data, dict) or data.get("parent_score") is None:
        return 0
    try:
        return max(int(data["parent_score"]), 0)
    except (TypeError, ValueError):
        return 0


def seed_run(
    run_dir: Path,
    root: Path,
    n_actions: int,
    objective: str | None,
    min_score: int = 0,
) -> bool:
    """Copy the best saved run when it reaches the score this generation started from.

    A shorter run stays out, and the seats play the weights they loaded.
    A run at that score is practiced. A higher saved run replaces the file.
    The same score replaces it when the saved run got there faster.
    """
    dest = run_dir / TAPE_NAME
    current = read_tape(dest)
    tape = best_saved(root, n_actions, objective, exclude=run_dir)
    if tape is None or comparable(tape) <= 0 or comparable(tape) < floor_value(min_score):
        return False
    if compatible(current, n_actions, objective) and not better(tape, current):
        return False
    write_tape(dest, tape)
    return True
