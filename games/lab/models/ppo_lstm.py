"""Recurrent PPO. The comparison for whether memory beats a stack of frames."""
from __future__ import annotations

ID = "ppo_lstm"
LABEL = "PPO / LSTM"
DETAIL = "Pixels, a frame stack, and an LSTM."
NEEDS_RAM = False


def build(env, seed: int):
    from sb3_contrib import RecurrentPPO
    from games.lab.models.common import gray_stack, torch_one_thread
    torch_one_thread()
    return RecurrentPPO(
        "CnnLstmPolicy",
        gray_stack(env),
        n_steps=128,
        batch_size=128,
        learning_rate=2.5e-4,
        ent_coef=0.01,
        policy_kwargs={"lstm_hidden_size": 128},
        seed=seed,
        device="auto",
        verbose=0,
    )


def load(path, env):
    from sb3_contrib import RecurrentPPO
    from games.lab.models.common import gray_stack, torch_one_thread
    torch_one_thread()
    return RecurrentPPO.load(path, env=gray_stack(env), device="auto")
