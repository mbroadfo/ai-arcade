"""Observation wrappers. Imported by a builder when a model is constructed, not by the registry."""
from __future__ import annotations

from collections import deque

import numpy as np
from gymnasium import spaces
from PIL import Image


def torch_one_thread() -> None:
    import torch
    torch.set_num_threads(1)


def integration_of(env):
    current = env
    while current is not None:
        integration = getattr(current, "integration", None)
        if integration is not None:
            return integration
        current = getattr(current, "env", None)
    return None


def gray_stack(env, frames: int = 4):
    """84x84 grayscale, stacked to (frames, 84, 84). Nature CNN reads that as channels-first."""
    import gymnasium as gym

    class _Gray(gym.ObservationWrapper):
        def __init__(self, inner):
            super().__init__(inner)
            self.observation_space = spaces.Box(0, 255, (84, 84, 1), dtype=np.uint8)

        def observation(self, obs):
            image = Image.fromarray(obs).convert("L").resize((84, 84), Image.BILINEAR)
            array = np.asarray(image, dtype=np.uint8)
            return array[:, :, None]

    class _Stack(gym.Wrapper):
        def __init__(self, inner):
            super().__init__(inner)
            self._frames: deque = deque(maxlen=frames)
            self.observation_space = spaces.Box(0, 255, (frames, 84, 84), dtype=np.uint8)

        def _stack(self):
            return np.stack(list(self._frames), axis=0)

        def reset(self, **kwargs):
            obs, info = self.env.reset(**kwargs)
            plane = obs[:, :, 0]
            for _ in range(frames):
                self._frames.append(plane)
            return self._stack(), info

        def step(self, action):
            obs, reward, terminated, truncated, info = self.env.step(action)
            self._frames.append(obs[:, :, 0])
            return self._stack(), reward, terminated, truncated, info

    return _Stack(_Gray(env))


def ram_view(env):
    import gymnasium as gym

    integration = integration_of(env)
    if integration is None or not hasattr(integration, "ram_vector"):
        raise ValueError("PPO / RAM needs a scored game with a RAM vector")
    width = len(integration.ram_vector(bytes(2048)))

    class _Ram(gym.ObservationWrapper):
        def __init__(self, inner):
            super().__init__(inner)
            self.observation_space = spaces.Box(-np.inf, np.inf, (width,), dtype=np.float32)

        def observation(self, _obs):
            ram = self.env.unwrapped.ram_bytes()
            return np.asarray(integration.ram_vector(ram), dtype=np.float32)

    return _Ram(env)
