"""Supervised practice on one demonstrated action sequence.

This is not a training generation. It does not read a shared tape, and it does
not change what the environment does on step. The caller has already played
the demonstration and kept the observations. Torch loads only when practice runs.
"""
from __future__ import annotations

import numpy as np


def practice_actions(
    model,
    observations,
    actions,
    *,
    epochs: int = 80,
    learning_rate: float = 1e-4,
    extra_after_match: int = 5,
) -> dict:
    """Move one policy toward these labeled actions.

    Each distinct action gets the same total weight, so a short jump is not
    drowned by the long wait before it. Training stops once the deterministic
    action matches every label, plus a few extra epochs, or at the epoch cap.
    """
    import torch

    obs = np.asarray(observations)
    labels = np.asarray(list(actions), dtype=np.int64)
    if obs.ndim < 2 or obs.shape[0] != labels.shape[0]:
        raise ValueError("one observation per action")
    if labels.size == 0:
        raise ValueError("empty demonstration")
    counts = {int(action): int((labels == action).sum()) for action in sorted(set(labels.tolist()))}
    weights = np.asarray([1.0 / counts[int(action)] for action in labels], dtype=np.float32)

    policy = model.policy
    policy.set_training_mode(True)
    optimizer = torch.optim.Adam(policy.parameters(), lr=float(learning_rate))
    history = []
    matched_at = None
    for epoch in range(1, int(epochs) + 1):
        obs_tensor, _vectorized = policy.obs_to_tensor(obs)
        action_tensor = torch.as_tensor(labels, device=policy.device)
        weight_tensor = torch.as_tensor(weights, device=policy.device)
        _values, log_prob, _entropy = policy.evaluate_actions(obs_tensor, action_tensor)
        log_prob = log_prob.reshape(-1)
        loss = -(log_prob * weight_tensor).sum() / weight_tensor.sum()
        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(policy.parameters(), 0.5)
        optimizer.step()
        with torch.no_grad():
            predicted = policy.get_distribution(obs_tensor).get_actions(deterministic=True)
        predicted = predicted.detach().cpu().numpy().reshape(-1)
        matched = int((predicted == labels).sum())
        history.append({
            "epoch": epoch,
            "loss": float(loss.detach().cpu()),
            "matched": matched,
            "count": int(labels.size),
        })
        if matched == int(labels.size) and matched_at is None:
            matched_at = epoch
        if matched_at is not None and epoch >= matched_at + int(extra_after_match):
            break
    policy.set_training_mode(False)
    return {
        "epochs_ran": history[-1]["epoch"],
        "matched_at": matched_at,
        "class_counts": counts,
        "final": history[-1],
        "history": history,
    }
