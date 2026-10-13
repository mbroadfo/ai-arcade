"""The standard pixel PPO with a wider button spread. Its own weights."""
from __future__ import annotations

ID = "ppo_cnn_explore"
LABEL = "PPO / Explore"
DETAIL = "Pixels. Entropy 0.05, so it tries more routes than the standard CNN."
NEEDS_RAM = False
ENT_COEF = 0.05


def build(env, seed: int):
    from games.lab.models.ppo_cnn import build as build_cnn
    return build_cnn(env, seed, ent_coef=ENT_COEF)


def load(path, env):
    from games.lab.models.ppo_cnn import load
    return load(path, env)
