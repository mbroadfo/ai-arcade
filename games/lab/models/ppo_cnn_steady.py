"""The standard pixel PPO with a narrow button spread. Its own weights."""
from __future__ import annotations

ID = "ppo_cnn_steady"
LABEL = "PPO / Steady"
DETAIL = "Pixels. Entropy 0.001, so it repeats the button it already prefers."
NEEDS_RAM = False
ENT_COEF = 0.001


def build(env, seed: int):
    from games.lab.models.ppo_cnn import build as build_cnn
    return build_cnn(env, seed, ent_coef=ENT_COEF)


def load(path, env):
    from games.lab.models.ppo_cnn import load
    return load(path, env)
