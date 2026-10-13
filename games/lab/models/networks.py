"""The shape of each learner. The page draws this. It does not build the network.

Counts follow the Stable-Baselines3 networks these seats actually construct:
Nature CNN with an empty extra MLP, two LSTMs of 128 for the recurrent seat,
and the default 64-64 MLP for the RAM seat. Twelve buttons.
"""
from __future__ import annotations

ACTIONS = 12
RAM = 9
# 84x84, kernel 8 stride 4, kernel 4 stride 2, kernel 3 stride 1 → 7x7x64.
_FLAT = 7 * 7 * 64


def layer_params(layer: dict) -> int:
    kind = layer["kind"]
    if kind == "conv":
        return int(layer["out"]) * (int(layer["in"]) * int(layer["k"]) ** 2 + 1)
    if kind == "linear":
        return int(layer["out"]) * (int(layer["in"]) + 1)
    if kind == "lstm":
        hidden = int(layer["hidden"])
        # PyTorch keeps a bias on the input and a bias on the hidden state.
        return 4 * hidden * (int(layer["in"]) + hidden + 2)
    raise ValueError(f"unknown layer {kind}")


def _conv(label: str, incoming: int, outgoing: int, kernel: int) -> dict:
    return {"label": label, "kind": "conv", "in": incoming, "out": outgoing, "k": kernel}


def _linear(label: str, incoming: int, outgoing: int) -> dict:
    return {"label": label, "kind": "linear", "in": incoming, "out": outgoing}


def _lstm(label: str, incoming: int, hidden: int) -> dict:
    return {"label": label, "kind": "lstm", "in": incoming, "hidden": hidden}


def _finish(note: str, seen: str, layers: list[dict]) -> dict:
    drawn = []
    for layer in layers:
        item = dict(layer)
        item["params"] = layer_params(layer)
        drawn.append(item)
    return {
        "note": note,
        "input": seen,
        "layers": drawn,
        "parameters": sum(item["params"] for item in drawn),
    }


def _nature() -> list[dict]:
    return [
        _conv("Conv 8×8, 32", 4, 32, 8),
        _conv("Conv 4×4, 64", 32, 64, 4),
        _conv("Conv 3×3, 64", 64, 64, 3),
        _linear("Dense 512", _FLAT, 512),
    ]


def _cnn(note: str) -> dict:
    return _finish(
        note,
        "4 grayscale frames, 84×84",
        _nature() + [_linear("12 buttons", 512, ACTIONS), _linear("Value", 512, 1)],
    )


def network_for(model_id: str) -> dict:
    if model_id == "ppo_cnn":
        return _cnn("Entropy 0.01. Same shape as Explore and Steady.")
    if model_id == "ppo_cnn_explore":
        return _cnn("Entropy 0.05. Same shape as the standard CNN, more willing to try a new button.")
    if model_id == "ppo_cnn_steady":
        return _cnn("Entropy 0.001. Same shape as the standard CNN, more willing to repeat a button.")
    if model_id == "ppo_lstm":
        return _finish(
            "The same picture front, then two memories of 128. The memory lasts one life.",
            "4 grayscale frames, 84×84",
            _nature()
            + [
                _lstm("LSTM 128, policy", 512, 128),
                _lstm("LSTM 128, value", 512, 128),
                _linear("12 buttons", 128, ACTIONS),
                _linear("Value", 128, 1),
            ],
        )
    if model_id == "dqn_cnn":
        return _finish(
            "The same picture front. One head scores all 12 buttons.",
            "4 grayscale frames, 84×84",
            _nature() + [_linear("12 button values", 512, ACTIONS)],
        )
    if model_id == "ppo_ram":
        return _finish(
            "Nine numbers from the game, then two small layers. No picture.",
            "9 RAM numbers",
            [
                _linear("Dense 64, policy", RAM, 64),
                _linear("Dense 64, policy", 64, 64),
                _linear("12 buttons", 64, ACTIONS),
                _linear("Dense 64, value", RAM, 64),
                _linear("Dense 64, value", 64, 64),
                _linear("Value", 64, 1),
            ],
        )
    return _finish("Unknown model.", "", [])
