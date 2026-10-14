"""The model menu. Adding a model is a module plus one line in MODULES."""
from __future__ import annotations

from games.lab.models import dqn_cnn, ppo_cnn, ppo_cnn_explore, ppo_cnn_steady, ppo_lstm, ppo_ram

MODULES = (ppo_cnn, ppo_cnn_explore, ppo_cnn_steady, ppo_lstm, dqn_cnn, ppo_ram)
BY_ID = {module.ID: module for module in MODULES}


def ids() -> list[str]:
    return [module.ID for module in MODULES]


def describe() -> list[dict]:
    from games.lab.models.networks import network_for
    return [
        {
            "id": module.ID,
            "label": module.LABEL,
            "detail": module.DETAIL,
            "needs_ram": module.NEEDS_RAM,
            "network": network_for(module.ID),
        }
        for module in MODULES
    ]


def get(model_id: str):
    try:
        return BY_ID[model_id]
    except KeyError:
        raise KeyError(f"unknown model {model_id}") from None


def check(model_id: str, integration) -> None:
    module = get(model_id)
    from games.lab.contract import capabilities_of
    has_ram = integration is not None and capabilities_of(integration).get("ram") and hasattr(integration, "ram_vector")
    if module.NEEDS_RAM and not has_ram:
        raise ValueError(f"{module.LABEL} needs an adapter with a RAM observation")


def build(model_id: str, env, seed: int):
    return get(model_id).build(env, seed)


def load(model_id: str, path, env):
    return get(model_id).load(path, env)
