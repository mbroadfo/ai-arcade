"""Capture the World 1-1 opening and, when a saved run reaches it, World 1-2.

This writes challenge files under games/lab/challenges. It does not start
training and it does not write into the runs folder.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from games.lab.challenge import challenges_root, reached_warp, same_start, save_challenge
from games.lab.integrations.smb_1_1 import CLEAR_X, SMB_ACTIONS, describe, diagnose
from games.lab.probe import EmulatorProbe
from games.lab.search import beam_search


def _sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _boot():
    from games.lab.actions import BUTTON_ID
    from games.lab.cores import ensure_core
    from games.lab.integrations.smb_1_1 import skip_title
    from games.lab.libretro import LibretroRunner
    from games.lab.roms import SMB_SHA1, pinned_smb
    rom = pinned_smb()
    if rom is None:
        raise SystemExit("pinned Super Mario Bros. ROM is missing")
    core = ensure_core("nes")
    runner = LibretroRunner(core, rom, BUTTON_ID)
    skip_title(runner)
    return runner, rom, core, SMB_SHA1


def _sample(runner, buttons: set[str], frames: int) -> list[dict]:
    rows = []
    for index in range(frames):
        runner.frame(buttons)
        ram = runner.ram_bytes()
        facts = describe(ram)
        diag = diagnose(ram)
        rows.append({
            "frame": index + 1,
            "x_pos": facts["x_pos"],
            "y_pos": facts["y_pos"],
            "physics": diag["physics"],
            "physics_code": diag["physics_code"],
            "x_speed": diag["x_speed"],
            "y_speed": diag["y_speed"],
            "area": diag["area"],
            "power": diag["power"],
            "enemies": len(diag["enemies"]),
            "dead": facts["dead"],
            "dying": facts["dying"],
            "world": facts["world"],
            "stage": facts["stage"],
            "time": facts["time"],
            "player_state": facts["player_state"],
        })
    return rows


def _restore_mode(runner) -> tuple[bytes, bool, dict]:
    """How to put the core back on the bytes we just saved."""
    state = runner.serialize()
    if not state:
        raise RuntimeError("the core returned an empty savestate")
    before = describe(runner.ram_bytes())
    for _ in range(8):
        runner.frame({"RIGHT"})
    runner.unserialize(state)
    immediate = describe(runner.ram_bytes())
    if same_start(before, immediate):
        return state, False, {"mode": "unserialize", "before": before, "after": immediate}
    runner.frame(set())
    after = describe(runner.ram_bytes())
    return state, True, {"mode": "unserialize+empty-frame", "before": before, "immediate": immediate, "after": after}


def _opening(runner, rom_sha1: str, core_sha1: str) -> dict:
    state, empty_frame, restore_report = _restore_mode(runner)
    probe = EmulatorProbe(runner, state, empty_frame=empty_frame)
    start = probe.restore()
    jump_rows = _sample(runner, {"A"}, 24)
    probe.restore()
    run_rows = _sample(runner, {"RIGHT"}, 60)
    probe.restore()
    both_rows = _sample(runner, {"RIGHT", "A"}, 60)
    start_x = int(start["x_pos"])
    run_delta = int(run_rows[-1]["x_pos"]) - start_x if run_rows else 0
    both_delta = int(both_rows[-1]["x_pos"]) - start_x if both_rows else 0
    moved = max(run_delta, both_delta, 0)
    per_frame = moved / 60.0 if moved else 0.0
    goal_delta = 8 if per_frame <= 0 else max(4, min(16, int(per_frame * 20)))
    goal = start_x + goal_delta
    needed = 60 if per_frame <= 0 else min(48, max(8, int(goal_delta / per_frame) + 4))
    y_speeds = [row["y_speed"] for row in jump_rows]
    physics = sorted({row["physics"] for row in jump_rows})
    saw_negative = any(speed < 0 for speed in y_speeds)
    saw_enemy = any(row["enemies"] for row in run_rows + both_rows)

    def success(facts: dict) -> bool:
        return (
            bool(facts.get("saw_jump"))
            and int(facts.get("x_pos") or 0) >= goal
            and not facts.get("dead")
            and not facts.get("dying")
        )

    def rank(facts: dict) -> int:
        if facts.get("dead") or facts.get("dying"):
            return -10_000
        jump = 1000 if facts.get("saw_jump") else 0
        return jump + int(facts.get("x_pos") or 0)

    actions = [("RIGHT",), ("RIGHT", "A"), ("A",)]
    found = beam_search(
        probe,
        actions,
        success,
        rank,
        width=4,
        depth=needed,
        hold=1,
        max_attempts=max(80, needed * 12),
        max_frames=20000,
    )
    document = {
        "id": "smb-1-1-opening-jump",
        "objective": (
            "From the start of World 1-1, jump and move right. "
            "Success is a higher x, an upward motion, and Mario still alive."
        ),
        "game": "Super Mario Bros.",
        "rom_sha1": rom_sha1,
        "core_sha1": core_sha1,
        "core_name": "fceumm",
        "success": "jump-and-run",
        "x_goal": goal,
        "max_frames": 20000,
        "restore": "unserialize+empty-frame" if empty_frame else "unserialize",
        "start": {
            "world": start["world"],
            "stage": start["stage"],
            "x_pos": start["x_pos"],
            "y_pos": start["y_pos"],
            "time": start["time"],
            "player_state": start["player_state"],
        },
        "note": "Frame-accurate search. Each button stores its own frame count. This is not a warp.",
    }
    folder = save_challenge(challenges_root(), document, state)
    from games.lab.worker import atomic_json
    atomic_json(folder / "search.json", found)
    atomic_json(folder / "measurement.json", {
        "restore": restore_report["mode"],
        "start": document["start"],
        "goal_x": goal,
        "right_delta_60": run_delta,
        "right_a_delta_60": both_delta,
        "jump_physics": physics,
        "jump_y_speed_min": min(y_speeds) if y_speeds else None,
        "jump_y_speed_negative": saw_negative,
        "enemy_seen": saw_enemy,
        "jump_sample": jump_rows[:8],
        "solved": found["solved"],
        "attempts": found["attempts"],
        "frames": found["frames"],
        "trajectory_frames": found["trajectory_frames"],
        "budget_exhausted": found["budget_exhausted"],
    })
    if found["solved"]:
        from games.lab.skill import curriculum_plan, new_skill, verify_demonstration
        end_a = probe.replay(found["trajectory"])
        end_b = probe.replay(found["trajectory"])
        skill = new_skill(
            "opening jump",
            document["objective"],
            document["id"],
            found["trajectory"],
            world=1,
            stage=1,
            start=document["start"],
        )
        skill = verify_demonstration(skill, [success(end_a), success(end_b)])
        atomic_json(folder / "skill.json", skill)
    from games.lab.skill import curriculum_plan
    atomic_json(folder / "curriculum.json", {"stages": curriculum_plan(document["id"])})
    return {
        "id": document["id"],
        "solved": found["solved"],
        "attempts": found["attempts"],
        "frames": found["frames"],
        "trajectory_frames": found["trajectory_frames"],
        "goal_x": goal,
        "start_x": start_x,
        "y_speed_negative": saw_negative,
        "physics": physics,
        "enemy_seen": saw_enemy,
        "restore": document["restore"],
    }


def _tape_candidates() -> list[tuple[int, Path]]:
    from games.lab.paths import runs_root
    from games.lab.tape import comparable, read_tape
    root = runs_root()
    found = []
    if not root.is_dir():
        return found
    paths = list(root.glob("*/best.tape.json"))
    paths.extend(root.glob("*/seats/*/best.tape.json"))
    for path in paths:
        tape = read_tape(path)
        if not tape or tape.get("objective") != "progress":
            continue
        world = int(tape.get("world") or 1)
        stage = int(tape.get("stage") or 1)
        if world == 1 and stage < 2:
            continue
        found.append((comparable(tape), path))
    found.sort(key=lambda item: item[0], reverse=True)
    return found[:8]


def _replay_to_1_2(runner, actions: list[int]) -> dict | None:
    """Play a saved run at the training frame skip until 1-2 is actually on screen."""
    for index, action in enumerate(actions[:30000]):
        try:
            buttons = set(SMB_ACTIONS[int(action)])
        except (IndexError, TypeError, ValueError):
            continue
        for _ in range(4):
            runner.frame(buttons)
        facts = describe(runner.ram_bytes())
        # Past the 1-1 castle: the clock is running and x has left the castle walk.
        if (
            facts["world"] == 1
            and facts["stage"] == 2
            and int(facts["time"] or 0) > 100
            and int(facts["x_pos"] or 0) < 1000
            and not facts["dead"]
            and not facts["dying"]
        ):
            return facts
    return None


def _warp(runner, rom_sha1: str, core_sha1: str, empty_frame: bool) -> dict:
    from games.lab.tape import read_tape
    report = {"candidates": [], "reached": False}
    opening = challenges_root() / "smb-1-1-opening-jump" / "state.bin"
    candidates = _tape_candidates()
    if not candidates:
        report["reason"] = "no saved run claims a later stage"
        return report
    if not opening.is_file():
        report["reason"] = "opening state is missing, so the tape was not replayed"
        return report
    blob = opening.read_bytes()
    reached = None
    chosen = None
    for score, path in candidates[:4]:
        tape = read_tape(path)
        actions = list(tape.get("actions") or [])
        entry = {
            "path": str(path),
            "score": score,
            "world": tape.get("world"),
            "stage": tape.get("stage"),
            "presses": len(actions),
        }
        report["candidates"].append(entry)
        runner.unserialize(blob)
        if empty_frame:
            runner.frame(set())
        reached = _replay_to_1_2(runner, actions)
        if reached is not None:
            chosen = entry
            break
    report["first"] = chosen or (report["candidates"][0] if report["candidates"] else None)
    if reached is None:
        end = describe(runner.ram_bytes())
        report["reason"] = "replay did not show world 1-2 with the clock running"
        report["ended"] = {
            "world": end["world"],
            "stage": end["stage"],
            "x_pos": end["x_pos"],
            "time": end["time"],
            "dead": end["dead"],
        }
        return report
    state = runner.serialize()
    probe = EmulatorProbe(runner, state, empty_frame=False)
    start = probe.restore()
    if not same_start(reached, start):
        # The serialize included the current frame. Keep the bytes that restore to `start`.
        reached = {
            "world": start["world"],
            "stage": start["stage"],
            "x_pos": start["x_pos"],
            "y_pos": start["y_pos"],
            "time": start["time"],
            "player_state": start["player_state"],
            "dead": start["dead"],
            "dying": start["dying"],
        }
    if reached.get("world") != 1 or reached.get("stage") != 2:
        report["reason"] = "restored state is not world 1-2"
        report["ended"] = reached
        return report
    document = {
        "id": "smb-1-2-ceiling-warp",
        "objective": (
            "In World 1-2, take the ceiling route and reach the warp to World 4. "
            "Success is the emulator changing the world to 4. A score is not success."
        ),
        "game": "Super Mario Bros.",
        "rom_sha1": rom_sha1,
        "core_sha1": core_sha1,
        "core_name": "fceumm",
        "success": "world-4-from-1-2",
        "max_frames": 4000,
        "restore": "unserialize",
        "start": {
            "world": int(reached["world"]),
            "stage": int(reached["stage"]),
            "x_pos": int(reached["x_pos"]),
            "y_pos": int(reached["y_pos"]),
            "time": int(reached["time"]),
            "player_state": int(reached["player_state"]),
        },
        "note": (
            "The normal ceiling warp. The frame-perfect pipe clip is out of scope. "
            f"The castle walk at x {CLEAR_X} is not this state."
        ),
    }
    # Confirm the blob round-trips before saving.
    check = probe.restore()
    if not same_start(document["start"], check):
        report["reason"] = "savestate did not round-trip"
        report["ended"] = check
        return report

    def success(facts: dict) -> bool:
        return reached_warp(document["start"], facts)

    def rank(facts: dict) -> int:
        if facts.get("dead") or facts.get("dying"):
            return -10_000
        return int(facts.get("world") or 1) * 100000 + int(facts.get("x_pos") or 0)

    actions = [(), ("RIGHT",), ("RIGHT", "A"), ("RIGHT", "B"), ("RIGHT", "A", "B"), ("A",), ("LEFT",), ("DOWN",)]
    found = beam_search(
        probe, actions, success, rank,
        width=2, depth=3, hold=1, max_attempts=30, max_frames=500,
    )
    folder = save_challenge(challenges_root(), document, state)
    from games.lab.skill import curriculum_plan
    from games.lab.worker import atomic_json
    atomic_json(folder / "search.json", found)
    atomic_json(folder / "curriculum.json", {"stages": curriculum_plan(document["id"])})
    report["reached"] = True
    report["solved"] = found["solved"]
    report["attempts"] = found["attempts"]
    report["frames"] = found["frames"]
    report["start"] = document["start"]
    return report


def refine() -> dict:
    """Settle the 1-2 state and search the opening jump within the measured movement."""
    from games.lab.actions import BUTTON_ID
    from games.lab.cores import ensure_core
    from games.lab.libretro import LibretroRunner
    from games.lab.roms import SMB_SHA1, pinned_smb
    from games.lab.skill import curriculum_plan, new_skill, verify_demonstration
    from games.lab.worker import atomic_json
    rom = pinned_smb()
    core = ensure_core("nes")
    runner = LibretroRunner(core, rom, BUTTON_ID)
    root = challenges_root()
    try:
        from games.lab.challenge import load_challenge
        opening_dir = root / "smb-1-1-opening-jump"
        _document, opening_state = load_challenge(opening_dir, rom_sha1=SMB_SHA1, core_sha1=_sha1(core))
        probe = EmulatorProbe(runner, opening_state, empty_frame=False)
        start = probe.restore()
        goal = int(start["x_pos"]) + 8

        def success(facts: dict) -> bool:
            return (
                bool(facts.get("saw_jump"))
                and int(facts.get("x_pos") or 0) >= goal
                and not facts.get("dead")
                and not facts.get("dying")
            )

        def rank(facts: dict) -> int:
            if facts.get("dead") or facts.get("dying"):
                return -10_000
            return (1000 if facts.get("saw_jump") else 0) + int(facts.get("x_pos") or 0)

        found = beam_search(
            probe,
            [("RIGHT", "A"), ("RIGHT",)],
            success,
            rank,
            width=3,
            depth=36,
            hold=1,
            max_attempts=400,
            max_frames=8000,
        )
        atomic_json(opening_dir / "search.json", {
            key: found[key] for key in (
                "solved", "trajectory", "attempts", "frames", "trajectory_frames",
                "best_facts", "best_rank", "cancelled", "budget_exhausted",
            )
        })
        skill = None
        if found["solved"]:
            skill = verify_demonstration(
                new_skill(
                    "opening jump",
                    _document["objective"],
                    _document["id"],
                    found["trajectory"],
                    world=1,
                    stage=1,
                    start=_document["start"],
                ),
                [success(probe.replay(found["trajectory"])), success(probe.replay(found["trajectory"]))],
            )
            atomic_json(opening_dir / "skill.json", skill)
        # Walk far enough to see whether an enemy slot becomes active.
        probe.restore()
        enemy_frame = None
        for frame in range(240):
            runner.frame({"RIGHT"})
            diag = diagnose(runner.ram_bytes())
            if diag["enemies"]:
                enemy_frame = {"frame": frame + 1, "enemies": diag["enemies"], "x_pos": describe(runner.ram_bytes())["x_pos"]}
                break
        # Settle world 1-2 past the entry frame.
        warp_dir = root / "smb-1-2-ceiling-warp"
        warp_doc, warp_state = load_challenge(warp_dir, rom_sha1=SMB_SHA1, core_sha1=_sha1(core))
        runner.unserialize(warp_state)
        settled = None
        trace = []
        for frame in range(180):
            facts = describe(runner.ram_bytes())
            trace.append({
                "frame": frame,
                "player_state": facts["player_state"],
                "time": facts["time"],
                "x_pos": facts["x_pos"],
                "y_pos": facts["y_pos"],
                "world": facts["world"],
                "stage": facts["stage"],
            })
            if (
                facts["world"] == 1
                and facts["stage"] == 2
                and facts["player_state"] == 8
                and 100 < int(facts["time"] or 0) <= 400
                and not facts["dead"]
                and not facts["dying"]
            ):
                settled = runner.serialize()
                break
            runner.frame(set())
        warp_report = {"settled": settled is not None, "trace_head": trace[:6], "trace_tail": trace[-3:]}
        if settled is not None:
            probe = EmulatorProbe(runner, settled, empty_frame=False)
            start = probe.restore()
            document = dict(warp_doc)
            document["start"] = {
                "world": start["world"],
                "stage": start["stage"],
                "x_pos": start["x_pos"],
                "y_pos": start["y_pos"],
                "time": start["time"],
                "player_state": start["player_state"],
            }
            document["restore"] = "unserialize"

            def warp_success(facts: dict) -> bool:
                return reached_warp(document["start"], facts)

            def warp_rank(facts: dict) -> int:
                if facts.get("dead") or facts.get("dying"):
                    return -10_000
                return int(facts.get("world") or 1) * 100000 + int(facts.get("x_pos") or 0)

            actions = [(), ("RIGHT",), ("RIGHT", "A"), ("RIGHT", "B"), ("RIGHT", "A", "B"), ("A",), ("LEFT",), ("DOWN",)]
            warp_found = beam_search(
                probe, actions, warp_success, warp_rank,
                width=2, depth=3, hold=1, max_attempts=30, max_frames=500,
            )
            save_challenge(root, document, settled)
            atomic_json(warp_dir / "search.json", {
                key: warp_found[key] for key in (
                    "solved", "trajectory", "attempts", "frames", "trajectory_frames",
                    "best_facts", "best_rank", "cancelled", "budget_exhausted",
                )
            })
            atomic_json(warp_dir / "curriculum.json", {"stages": curriculum_plan(document["id"])})
            warp_report["solved"] = warp_found["solved"]
            warp_report["attempts"] = warp_found["attempts"]
            warp_report["start"] = document["start"]
        summary = {
            "opening_solved": found["solved"],
            "opening_attempts": found["attempts"],
            "opening_frames": found["frames"],
            "opening_trajectory_frames": found["trajectory_frames"],
            "goal_x": goal,
            "best_x": (found.get("best_facts") or {}).get("x_pos"),
            "saw_jump": (found.get("best_facts") or {}).get("saw_jump"),
            "skill_stage": None if skill is None else skill.get("stage"),
            "enemy_frame": enemy_frame,
            "warp": warp_report,
        }
        atomic_json(opening_dir / "measurement.json", summary)
        print(json.dumps(summary, indent=2))
        return summary
    finally:
        runner.close()


def main() -> int:
    runner, rom, core, rom_sha1 = _boot()
    try:
        core_sha1 = _sha1(core)
        file_sha1 = _sha1(rom)
        if file_sha1 != rom_sha1:
            raise SystemExit("ROM hash does not match the pin")
        opening = _opening(runner, rom_sha1, core_sha1)
        empty = opening["restore"] != "unserialize"
        warp = _warp(runner, rom_sha1, core_sha1, empty)
        summary = {"rom_sha1": rom_sha1, "core_sha1": core_sha1, "opening": opening, "warp": warp}
        dest = challenges_root() / "measurement.json"
        from games.lab.worker import atomic_json
        atomic_json(dest, summary)
        print(json.dumps(summary, indent=2))
        return 0
    finally:
        runner.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "refine":
        refine()
        raise SystemExit(0)
    raise SystemExit(main())
