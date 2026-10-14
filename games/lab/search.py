"""Bounded search for a short button sequence from one saved state.

This is a maneuver finder. It does not replace the six learners, and it does
not write their weights. Every candidate is judged by running it.
"""
from __future__ import annotations


def frames_of(trajectory: list[dict]) -> int:
    total = 0
    for step in trajectory:
        total += int(step["frames"])
    return total


def beam_search(
    probe,
    actions,
    success,
    rank,
    *,
    width: int = 4,
    depth: int = 8,
    hold: int = 1,
    max_attempts: int = 80,
    max_frames: int = 4000,
    cancel=None,
    resume: dict | None = None,
) -> dict:
    """Beam search. probe.replay(trajectory) restores the start and plays it.

    hold is the number of frames each new button is held. One means a single
    emulator frame. The trajectory stores that count on every step, so playback
    does not assume the training frame skip.
    """
    alphabet = [tuple(chord) for chord in actions]
    hold = max(int(hold), 1)
    if resume:
        beam = [list(item) for item in resume.get("beam") or [[]]]
        attempts = int(resume.get("attempts") or 0)
        used = int(resume.get("frames") or 0)
        best_rank = resume.get("best_rank")
        best_trajectory = list(resume.get("best_trajectory") or [])
        best_facts = resume.get("best_facts")
    else:
        start = probe.replay([])
        attempts = 1
        used = 0
        best_facts = start
        best_rank = rank(start)
        best_trajectory = []
        beam = [[]]
        if success(start):
            return _result(True, [], attempts, used, best_facts, best_rank, False, False, [[]])
    solved = False
    solved_trajectory = None
    cancelled = False
    exhausted = False
    for _level in range(int(depth)):
        if cancel is not None and cancel():
            cancelled = True
            break
        pool = []
        for trajectory in beam:
            for chord in alphabet:
                if attempts >= max_attempts or used >= max_frames:
                    exhausted = True
                    break
                step = {"buttons": list(chord), "frames": hold}
                candidate = list(trajectory) + [step]
                facts = probe.replay(candidate)
                attempts += 1
                used += hold
                value = rank(facts)
                if best_rank is None or value > best_rank:
                    best_rank = value
                    best_facts = facts
                    best_trajectory = candidate
                if success(facts):
                    solved = True
                    solved_trajectory = candidate
                    best_facts = facts
                    best_trajectory = candidate
                    best_rank = value
                    break
                if not facts.get("dead") and not facts.get("dying"):
                    pool.append((value, candidate))
            if solved or exhausted:
                break
        if solved or exhausted or cancelled:
            break
        pool.sort(key=lambda item: item[0], reverse=True)
        beam = [candidate for _value, candidate in pool[: int(width)]]
        if not beam:
            break
    trajectory = solved_trajectory if solved else best_trajectory
    return _result(
        solved, trajectory, attempts, used, best_facts, best_rank, cancelled, exhausted, beam
    )


def _result(solved, trajectory, attempts, used, facts, best_rank, cancelled, exhausted, beam) -> dict:
    return {
        "solved": bool(solved),
        "trajectory": trajectory,
        "attempts": int(attempts),
        "frames": int(used),
        "trajectory_frames": frames_of(trajectory),
        "best_facts": facts,
        "best_rank": best_rank,
        "cancelled": bool(cancelled),
        "budget_exhausted": bool(exhausted),
        "resume": {
            "beam": beam,
            "attempts": int(attempts),
            "frames": int(used),
            "best_rank": best_rank,
            "best_trajectory": trajectory,
            "best_facts": facts,
        },
    }
