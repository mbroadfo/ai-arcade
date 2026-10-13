"""The six seats. The color is the border on the lab page, not a palette hack in the ROM."""
from __future__ import annotations

SEATS = (
    {"name": "Red", "color": "#d64545"},
    {"name": "Green", "color": "#3c9d5a"},
    {"name": "Blue", "color": "#3a6fd8"},
    {"name": "Gold", "color": "#d4a017"},
    {"name": "Purple", "color": "#8a4fc7"},
    {"name": "White", "color": "#e6e1d6"},
)

# One learner per seat. The two extra pixel seats differ by how widely they sample buttons.
# Each id keeps its own parent weights.
DEFAULT_MODELS = (
    "ppo_cnn",
    "ppo_lstm",
    "dqn_cnn",
    "ppo_ram",
    "ppo_cnn_explore",
    "ppo_cnn_steady",
)


def default_seat_specs() -> list[dict]:
    return [{"model": model, "seed": index + 1} for index, model in enumerate(DEFAULT_MODELS)]
