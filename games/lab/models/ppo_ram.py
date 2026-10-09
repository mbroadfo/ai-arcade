"""PPO on the integration's RAM vector. Refuses a game that has no vector."""
from __future__ import annotations

ID = "ppo_ram"
LABEL = "PPO / RAM"
DETAIL = "The integration's RAM vector, not the picture. Scored games only."
NEEDS_RAM = True


def build(env, seed: int):
    from stable_baselines3 import PPO
    from games.lab.models.common import ram_view, torch_one_thread
    torch_one_thread()
    return PPO(
        "MlpPolicy",
        ram_view(env),
        n_steps=512,
        batch_size=64,
        n_epochs=4,
        learning_rate=2.5e-4,
        ent_coef=0.01,
        seed=seed,
        # Seven floats. The GPU path is slower than one CPU thread.
        device="cpu",
        verbose=0,
    )


def load(path, env):
    from stable_baselines3 import PPO
    from games.lab.models.common import ram_view, torch_one_thread
    torch_one_thread()
    return PPO.load(path, env=ram_view(env), device="cpu")
