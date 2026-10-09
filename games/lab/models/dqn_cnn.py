"""DQN with the Nature CNN. The value-based comparison."""
from __future__ import annotations

ID = "dqn_cnn"
LABEL = "DQN / Nature CNN"
DETAIL = "Pixels. Learns a value for each button, not a policy gradient."
NEEDS_RAM = False


def build(env, seed: int):
    from stable_baselines3 import DQN
    from games.lab.models.common import gray_stack, torch_one_thread
    torch_one_thread()
    return DQN(
        "CnnPolicy",
        gray_stack(env),
        buffer_size=10_000,
        learning_starts=256,
        target_update_interval=1000,
        train_freq=4,
        exploration_fraction=0.2,
        exploration_final_eps=0.05,
        seed=seed,
        device="auto",
        verbose=0,
    )


def load(path, env):
    from stable_baselines3 import DQN
    from games.lab.models.common import gray_stack, torch_one_thread
    torch_one_thread()
    return DQN.load(path, env=gray_stack(env), device="auto")
