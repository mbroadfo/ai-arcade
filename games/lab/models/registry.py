"""The model menu. Adding a model is a module plus one line in MODULES."""
from __future__ import annotations

from games.lab.models import dqn_cnn, ppo_cnn, ppo_lstm, ppo_ram

MODULES = (ppo_cnn, ppo_lstm, dqn_cnn, ppo_ram)
BY_ID = {module.ID: module for module in MODULES}


def ids() -> list[str]:
    return [module.ID for module in MODULES]


def describe() -> list[dict]:
    return [
        {"id": module.ID, "label": module.LABEL, "detail": module.DETAIL, "needs_ram": module.NEEDS_RAM}
        for module in MODULES
    ]


def get(model_id: str):
    try:
        return BY_ID[model_id]
    except KeyError:
        raise KeyError(f"unknown model {model_id}") from None


def check(model_id: str, integration) -> None:
    module = get(model_id)
    if module.NEEDS_RAM and (integration is None or not hasattr(integration, "ram_vector")):
        raise ValueError(f"{module.LABEL} needs a scored game with a RAM vector")


def build(model_id: str, env, seed: int):
    return get(model_id).build(env, seed)


def load(model_id: str, path, env):
    return get(model_id).load(path, env)
