"""Gymnasium wrapper around one libretro core.

FrameEnv is pixels and buttons. ScoredEnv adds an integration's objective.
SurvivalEnv is the bootable grade: the only score is how long the episode lasted,
and the page is expected to say so.
"""
from __future__ import annotations

from typing import Callable

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from games.lab.actions import BUTTON_ID, for_system
from games.lab.contract import sense_of
from games.lab.cores import ensure_core
from games.lab.libretro import LibretroRunner


class FrameEnv(gym.Env):
    metadata = {"render_modes": ["rgb_array"]}

    def __init__(self, runner: LibretroRunner, actions: list[tuple[str, ...]], frame_skip: int = 4,
                 prepare: Callable | None = None):
        self.runner = runner
        self.actions = list(actions)
        self.frame_skip = frame_skip
        self.prepare = prepare
        self._state: bytes | None = None
        self.record_sink = None
        self.action_space = spaces.Discrete(len(self.actions))
        shape = (runner.height, runner.width, 3)
        self.observation_space = spaces.Box(0, 255, shape, dtype=np.uint8)

    def ram_bytes(self) -> bytes:
        return self.runner.ram_bytes()

    def _write_record(self) -> None:
        if self.record_sink is not None and self.runner.rgb is not None:
            self.record_sink.write(self.runner.rgb.tobytes())

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if self._state is None:
            if self.prepare is not None:
                self.prepare(self.runner)
            self._state = self.runner.serialize()
        if self._state is not None:
            self.runner.unserialize(self._state)
        else:
            self.runner.reset_core()
            if self.prepare is not None:
                self.prepare(self.runner)
        self.runner.frame(set())
        self._write_record()
        return self.runner.rgb.copy(), {}

    def step(self, action):
        buttons = set(self.actions[int(action)])
        for _ in range(self.frame_skip):
            self.runner.frame(buttons)
            self._write_record()
            if self.runner.shutdown:
                break
        terminated = bool(self.runner.shutdown)
        return self.runner.rgb.copy(), 0.0, terminated, False, {}

    def render(self):
        return None if self.runner.rgb is None else self.runner.rgb.copy()

    def close(self):
        self.runner.close()


class ScoredEnv(gym.Wrapper):
    """Reward and facts come from the adapter. A life ends when the adapter says so.

    The step limit still ends a stuck episode. The adapter measures the
    objective, says when its clock is running, and may present a cleared
    stage in its own facts.
    """

    def __init__(self, env: FrameEnv, integration, step_limit: int = 20000):
        super().__init__(env)
        self.integration = integration
        self.step_limit = step_limit
        self._progress = 0
        self._steps = 0
        self._seen_time = False
        self._clear = {"cleared": False, "at": None}

    def _facts(self) -> dict:
        describe = getattr(self.integration, "describe", None)
        if not callable(describe):
            return {}
        facts = describe(self.env.unwrapped.ram_bytes())
        return facts if isinstance(facts, dict) else {}

    def _measure(self, facts: dict) -> int:
        measure = getattr(self.integration, "measure", None)
        if not callable(measure):
            return 0
        return int(measure(facts))

    def _running(self, facts: dict) -> bool:
        clock = getattr(self.integration, "clock_running", None)
        if not callable(clock):
            return False
        return bool(clock(facts))

    def _show(self, info: dict, facts: dict) -> None:
        present = getattr(self.integration, "present", None)
        if callable(present):
            shown = present(facts, self._clear)
            if isinstance(shown, dict):
                info.update(shown)
                return
        info.update(facts)

    def reset(self, *, seed=None, options=None):
        _obs, info = self.env.reset(seed=seed, options=options)
        facts = self._facts()
        self._progress = self._measure(facts)
        self._steps = 0
        self._seen_time = self._running(facts)
        self._clear = {"cleared": False, "at": None}
        self._show(info, facts)
        info["score"] = self._progress
        info["objective"] = self.integration.objective
        info["dead"] = False
        return self.env.unwrapped.runner.rgb.copy(), info

    def step(self, action):
        _obs, _reward, _terminated, _truncated, info = self.env.step(action)
        facts = self._facts()
        self._steps += 1
        if self._running(facts):
            self._seen_time = True
        reward_of = getattr(self.integration, "step_reward", None)
        note_clear = getattr(self.integration, "note_clear", None)
        if callable(note_clear):
            self._clear = note_clear(self._clear, facts)
        if not callable(reward_of):
            measured = self._measure(facts)
            dead = bool(facts.get("dead"))
            if sense_of(self.integration) == "minimize":
                self._progress = measured
                reward = -float(measured)
            else:
                gained = max(0, measured - self._progress)
                self._progress += gained
                reward = float(gained)
        elif callable(note_clear):
            place = self._clear.get("at") if self._clear.get("cleared") else None
            reward, self._progress, dead = reward_of(
                self._progress, facts, self._seen_time, bool(self._clear.get("cleared")), place
            )
        else:
            reward, self._progress, dead = reward_of(self._progress, facts, self._seen_time)
        if dead or self._steps >= self.step_limit:
            terminated = dead
            truncated = not dead
        else:
            terminated = False
            truncated = False
        self._show(info, facts)
        info["score"] = self._progress
        info["objective"] = self.integration.objective
        info["dead"] = dead
        return self.env.unwrapped.runner.rgb.copy(), reward, terminated, truncated, info


class SurvivalEnv(gym.Wrapper):
    """Bootable games have no death address. The score is steps until the time limit."""

    def __init__(self, env: FrameEnv, horizon: int = 2000):
        super().__init__(env)
        self.integration = None
        self.horizon = horizon
        self._steps = 0

    def reset(self, *, seed=None, options=None):
        obs, info = self.env.reset(seed=seed, options=options)
        self._steps = 0
        info["score"] = 0
        info["objective"] = "steps"
        return obs, info

    def step(self, action):
        obs, _reward, terminated, truncated, info = self.env.step(action)
        self._steps += 1
        if self._steps >= self.horizon:
            truncated = True
        info["score"] = self._steps
        info["objective"] = "steps"
        return obs, 1.0, bool(terminated), bool(truncated), info


def leave_nes_title(runner) -> None:
    """One START tap so a bootable NES game leaves the title demo.

    Wrecking Crew spends several seconds on "MARIO START!" before the phase.
    The savestate is taken after that, so a later reset does not return to the menu.
    START is not an action the seat can press. Holding it would pause the game.
    """
    for _ in range(30):
        runner.frame(set())
    runner.frame({"START"})
    runner.frame(set())
    for _ in range(480):
        runner.frame(set())


def _demonstration_row(button: int, info: dict) -> dict:
    """One practiced button. Missing place fields stay off the row."""
    row = {"action": int(button)}
    try:
        row["score"] = int(info.get("score") or 0)
    except (TypeError, ValueError):
        row["score"] = 0
    try:
        row["time"] = max(int(info.get("time") or 0), 0)
    except (TypeError, ValueError):
        row["time"] = 0
    for key in ("world", "stage"):
        if not isinstance(info, dict) or key not in info or info.get(key) is None:
            continue
        try:
            row[key] = int(info[key])
        except (TypeError, ValueError):
            continue
    context = info.get("context") if isinstance(info, dict) else None
    if isinstance(context, dict):
        row["context"] = dict(context)
    return row


class RouteEnv(gym.Wrapper):
    """Practice the shared run, then let the policy play.

    The run and a hint that applies after it are stepped inside reset. PPO and
    DQN only call step for buttons the policy chose, so a demonstration never
    enters either buffer. Every eighth life skips the run. A higher score
    replaces it, and so does a faster pass of the same ground.
    """

    def __init__(self, env: gym.Env, tape_path, n_actions: int, objective: str | None,
                 min_score: int = 0, hints_path=None):
        super().__init__(env)
        from games.lab.tape import Route
        self.route = Route(tape_path, n_actions, objective, min_score, hints_path)
        self._lives = 0
        self.demonstration_log: list[dict] = []

    def reset(self, *, seed=None, options=None):
        from games.lab.tape import search_life, take_demonstration
        obs, info = self.env.reset(seed=seed, options=options)
        self._lives += 1
        self.route.on_reset(search=search_life(self._lives))
        log: list[dict] = []
        ended = False

        def act(button: int) -> bool:
            nonlocal obs, info, ended
            obs, _reward, terminated, truncated, info = self.env.step(button)
            log.append(_demonstration_row(int(button), info))
            ended = bool(terminated or truncated)
            return not ended

        take_demonstration(self.route, self._place, act)
        if ended:
            # The demonstration itself ended the life. That death is not a policy
            # transition, so this life starts over with no scripted buttons.
            obs, info = self.env.reset(seed=seed, options=options)
            self.route.on_reset(search=True)
            log = []
        self.demonstration_log = log
        info = dict(info)
        info["forced"] = False
        info["assisted"] = False
        info["applied_action"] = None
        info["demonstration_steps"] = len(log)
        info["demonstration_log"] = log
        info["assisted_reset"] = bool(log)
        info["learn"] = True
        return obs, info

    def _place(self):
        env = self.env
        for _ in range(8):
            if env is None:
                return None, None
            integration = getattr(env, "integration", None)
            ram = getattr(getattr(env, "unwrapped", None), "ram_bytes", None)
            describe = getattr(integration, "describe", None)
            if callable(describe) and callable(ram):
                try:
                    facts = describe(ram())
                except Exception:
                    return None, None
                if isinstance(facts, dict):
                    return facts.get("world"), facts.get("stage")
            env = getattr(env, "env", None)
        return None, None

    def step(self, action):
        from games.lab.tape import as_int
        try:
            applied = as_int(action)
        except (TypeError, ValueError, IndexError):
            applied = 0
        obs, reward, terminated, truncated, info = self.env.step(applied)
        info["applied_action"] = applied
        info["forced"] = False
        info["assisted"] = False
        info["agent_action"] = applied
        info["demonstration_steps"] = len(self.demonstration_log)
        info["demonstration_log"] = self.demonstration_log
        info["assisted_reset"] = bool(self.demonstration_log)
        return obs, reward, terminated, truncated, info


def make_env(system: str, rom_path, integration=None, frame_skip: int = 4) -> gym.Env:
    runner = LibretroRunner(ensure_core(system), rom_path, BUTTON_ID)
    actions = integration.actions if integration is not None else for_system(system)
    if integration is not None:
        prepare = integration.skip_title
    elif system == "nes":
        prepare = leave_nes_title
    else:
        prepare = None
    env = FrameEnv(runner, actions, frame_skip=frame_skip, prepare=prepare)
    if integration is not None:
        return ScoredEnv(env, integration)
    return SurvivalEnv(env)
