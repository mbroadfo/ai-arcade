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
    """Reward is how far right Mario moved. The life ends on death, or at the flag because the level stops."""

    def __init__(self, env: FrameEnv, integration, step_limit: int = 10000):
        super().__init__(env)
        self.integration = integration
        self.step_limit = step_limit
        self._x = 0
        self._steps = 0
        self._seen_time = False

    def reset(self, *, seed=None, options=None):
        _obs, info = self.env.reset(seed=seed, options=options)
        facts = self.integration.describe(self.env.unwrapped.ram_bytes())
        self._x = facts["x_pos"]
        self._steps = 0
        self._seen_time = facts["time"] > 0
        info.update(facts)
        info["score"] = facts["x_pos"]
        info["objective"] = self.integration.objective
        return self.env.unwrapped.runner.rgb.copy(), info

    def step(self, action):
        _obs, _reward, terminated, truncated, info = self.env.step(action)
        facts = self.integration.describe(self.env.unwrapped.ram_bytes())
        reward = float(facts["x_pos"] - self._x)
        self._x = facts["x_pos"]
        self._steps += 1
        if facts["time"] > 0:
            self._seen_time = True
        dead = facts["dead"] or facts["dying"] or facts["game_over"] or (self._seen_time and facts["time"] == 0)
        if facts["flag_get"] or dead or self._steps >= self.step_limit:
            terminated = terminated or facts["flag_get"] or dead
            truncated = truncated or self._steps >= self.step_limit
        info.update(facts)
        info["score"] = facts["x_pos"]
        info["objective"] = self.integration.objective
        info["dead"] = dead
        return self.env.unwrapped.runner.rgb.copy(), reward, bool(terminated), bool(truncated), info


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
        info["flag_get"] = False
        info["objective"] = "steps"
        return obs, info

    def step(self, action):
        obs, _reward, terminated, truncated, info = self.env.step(action)
        self._steps += 1
        if self._steps >= self.horizon:
            truncated = True
        info["score"] = self._steps
        info["flag_get"] = False
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
