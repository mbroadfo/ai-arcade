"""Bounded search for a short button sequence from one saved state.

This is a maneuver finder. It does not replace the six learners, and it does
not write their weights. Every candidate is judged by running it.

`frames` is the number of emulator frames actually played. Each candidate is
restored and the whole sequence is run again, so this counts every prefix, not
only the button just appended. `decisions` is how many actions are in the
returned sequence. `trajectory_frames` is the emulator frames in that sequence.
An action that does not fit the remaining frame budget is skipped. A shorter
action later in the alphabet is still tried.
"""
from __future__ import annotations


def frames_of(trajectory: list[dict]) -> int:
    total = 0
    for step in trajectory:
        total += int(step["frames"])
    return total


def action_step(action, hold: int) -> dict:
    """One search action. A dict may set its own frame count.

    Navigation can hold RIGHT for many frames. A precision input can set
    frames to 1. The stored step is what playback runs.
    """
    if isinstance(action, dict):
        buttons = list(action.get("buttons") or [])
        raw = action.get("frames")
        frames = int(hold if raw is None else raw)
    else:
        buttons = list(action)
        frames = int(hold)
    if frames < 1:
        raise ValueError("an action lasts at least one frame")
    return {"buttons": buttons, "frames": frames}


def _note_subgoals(subgoals, facts, attempts: int, used: int, found: dict) -> None:
    if not subgoals:
        return
    for name, predicate in subgoals:
        if name in found:
            continue
        if predicate(facts):
            found[name] = {
                "name": name,
                "reached": True,
                "attempts": int(attempts),
                "frames": int(used),
            }


def _subgoal_rows(subgoals, found: dict) -> list[dict]:
    rows = []
    for name, _predicate in subgoals or []:
        rows.append(found.get(name) or {
            "name": name,
            "reached": False,
            "attempts": None,
            "frames": None,
        })
    return rows


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
    subgoals=None,
) -> dict:
    """Beam search. probe.replay(trajectory) restores the start and plays it.

    hold is the frame count for an action that does not name its own. One means
    a single emulator frame. A dict action {"buttons", "frames"} overrides it.
    max_frames counts emulator frames inside every replayed prefix.
    """
    alphabet = list(actions)
    hold = max(int(hold), 1)
    subgoals = list(subgoals or [])
    if resume:
        beam = [list(item) for item in resume.get("beam") or [[]]]
        attempts = int(resume.get("attempts") or 0)
        used = int(resume.get("frames") or 0)
        best_rank = resume.get("best_rank")
        best_trajectory = list(resume.get("best_trajectory") or [])
        best_facts = resume.get("best_facts")
        found_subgoals = dict(resume.get("subgoals_reached") or {})
    else:
        start = probe.replay([])
        attempts = 1
        used = frames_of([])
        best_facts = start
        best_rank = rank(start)
        best_trajectory = []
        beam = [[]]
        found_subgoals = {}
        _note_subgoals(subgoals, start, attempts, used, found_subgoals)
        if success(start):
            return _result(
                True, [], attempts, used, best_facts, best_rank, False, False, [[]],
                subgoals, found_subgoals,
            )
    solved = False
    solved_trajectory = None
    cancelled = False
    exhausted = False
    for _level in range(int(depth)):
        if cancel is not None and cancel():
            cancelled = True
            break
        pool = []
        progressed = False
        skipped_for_budget = False
        for trajectory in beam:
            for action in alphabet:
                step = action_step(action, hold)
                candidate = list(trajectory) + [step]
                replayed = frames_of(candidate)
                if attempts >= max_attempts:
                    exhausted = True
                    break
                if used + replayed > max_frames:
                    skipped_for_budget = True
                    continue
                facts = probe.replay(candidate)
                progressed = True
                attempts += 1
                used += replayed
                _note_subgoals(subgoals, facts, attempts, used, found_subgoals)
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
        if not progressed:
            if skipped_for_budget:
                exhausted = True
            break
        pool.sort(key=lambda item: item[0], reverse=True)
        beam = [candidate for _value, candidate in pool[: int(width)]]
        if not beam:
            break
    trajectory = solved_trajectory if solved else best_trajectory
    return _result(
        solved, trajectory, attempts, used, best_facts, best_rank, cancelled, exhausted, beam,
        subgoals, found_subgoals,
    )


def _result(solved, trajectory, attempts, used, facts, best_rank, cancelled, exhausted, beam, subgoals, found_subgoals) -> dict:
    return {
        "solved": bool(solved),
        "trajectory": trajectory,
        "attempts": int(attempts),
        "frames": int(used),
        "decisions": len(trajectory),
        "trajectory_frames": frames_of(trajectory),
        "frame_accounting": "full-prefix",
        "best_facts": facts,
        "best_rank": best_rank,
        "cancelled": bool(cancelled),
        "budget_exhausted": bool(exhausted),
        "subgoals": _subgoal_rows(subgoals, found_subgoals),
        "resume": {
            "beam": beam,
            "attempts": int(attempts),
            "frames": int(used),
            "best_rank": best_rank,
            "best_trajectory": trajectory,
            "best_facts": facts,
            "subgoals_reached": found_subgoals,
        },
    }
