"""PPO with the Nature CNN. The standard pixel seat."""
from __future__ import annotations

ID = "ppo_cnn"
LABEL = "PPO / Nature CNN"
DETAIL = "Pixels and a stack of four frames."
NEEDS_RAM = False
ENT_COEF = 0.01


def _algo(env, seed: int, ent_coef: float = ENT_COEF):
    from stable_baselines3 import PPO
    from games.lab.models.common import gray_stack, torch_one_thread
    torch_one_thread()
    return PPO(
        "CnnPolicy",
        gray_stack(env),
        n_steps=512,
        batch_size=64,
        n_epochs=4,
        learning_rate=2.5e-4,
        gamma=0.99,
        gae_lambda=0.95,
        ent_coef=ent_coef,
        clip_range=0.1,
        seed=seed,
        device="auto",
        verbose=0,
    )


def build(env, seed: int, ent_coef: float = ENT_COEF):
    return _algo(env, seed, ent_coef)


def load(path, env):
    from stable_baselines3 import PPO
    from games.lab.models.common import gray_stack, torch_one_thread
    torch_one_thread()
    return PPO.load(path, env=gray_stack(env), device="auto")
