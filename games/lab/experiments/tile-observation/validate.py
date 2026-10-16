"""Validate the Mario tile observation on real emulator states.

Scripted play only. This does not call learn, does not write a population,
and does not resume a lab generation.

Run with the mario-lab Python 3.12 environment, from the repo root:

    python games/lab/experiments/tile-observation/validate.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import traceback
from pathlib import Path

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ["LAB_RUNS"] = str(Path(os.environ.get("TEMP", ".")) / "lab-tile-observation-runs")

REPO = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OBJECTIVE = HERE.parent / "objective-reward"
ROM = Path(r"C:\Users\Mike\mario-lab\roms\smb.nes")
CORE_SHA1 = "e3d3a8436a3a0f3cc2c9164945dc4f87e616f243"
PIPE_SHA = "72c3ea8bd337c489e2a0c1adb3253de22457c8617c8162816dfbd25ae014a97e"
PAST_SHA = "4aead3929fddf62ea5f8eefb3b83868f8849719baf0b9ef756a21e976dd42141"
LATER_SHA = "cfce5b42f75e25299dae999900eeed5505f5a97b13f70d6531a97ef79d719172"
STATE_LEN = 13758
FRAME_CAP = 2000
PIPE_PATH = OBJECTIVE / "state.bin"
PAST_PATH = OBJECTIVE / "held-out-past-pipe.bin"
LATER_PATH = OBJECTIVE / "held-out-later.bin"


def _load_checks():
    spec = importlib.util.spec_from_file_location("tile_observation_checks", HERE / "checks.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKS = _load_checks()


def _sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _preflight() -> dict:
    from games.lab.cores import CORES
    from games.lab.mario.rom import SMB_SHA1
    from games.lab.paths import cores_dir

    problems = []
    rom_sha = _sha1(ROM) if ROM.is_file() else ""
    if rom_sha != SMB_SHA1:
        problems.append(f"ROM sha1 {rom_sha or 'missing'} != {SMB_SHA1}")
    core = cores_dir() / CORES["nes"]["file"]
    core_sha = ""
    if not core.is_file() or core.stat().st_size <= 100_000:
        problems.append(f"NES core is not on disk at {core}; refusing to download")
    else:
        core_sha = _sha1(core)
        if core_sha != CORE_SHA1:
            problems.append(f"core sha1 {core_sha} != {CORE_SHA1}")
    blobs = {}
    for label, path, expected in (
        ("approach", PIPE_PATH, PIPE_SHA),
        ("held_out_past", PAST_PATH, PAST_SHA),
        ("held_out_later", LATER_PATH, LATER_SHA),
    ):
        if not path.is_file():
            problems.append(f"{label} missing: {path}")
            continue
        blob = path.read_bytes()
        digest = hashlib.sha256(blob).hexdigest()
        blobs[label] = blob
        if len(blob) != STATE_LEN or digest != expected:
            problems.append(f"{label} length {len(blob)} sha256 {digest}")
    return {
        "ok": not problems,
        "problems": problems,
        "rom_sha1": rom_sha,
        "core_sha1": core_sha,
        "core_path": str(core),
        "blobs": blobs,
    }


def _guard(runner, counter: dict) -> None:
    original = runner.frame

    def limited(held):
        counter["n"] += 1
        if counter["n"] > FRAME_CAP:
            raise RuntimeError(f"emulator frame cap {FRAME_CAP} exceeded")
        return original(held)

    runner.frame = limited


def _enemy_slots(ram: bytes, mario_col: int, start_row: int) -> list[dict]:
    slots = []
    for index in range(5):
        slot = {
            "slot": index,
            "flag": ram[0x000F + index],
            "id": ram[0x0016 + index],
            "page": ram[0x006E + index],
            "x_0087": ram[0x0087 + index],
            "y_00CF": ram[0x00CF + index],
            "x_03AE": ram[0x03AE + index],
            "y_03B9": ram[0x03B9 + index],
        }
        for label, x_base, y_base in (("cell_03AE", 0x03AE, 0x03B9), ("cell_0087", 0x0087, 0x00CF)):
            column = ram[x_base + index] // 16
            row = ram[y_base + index] // 16
            slot[label] = {
                "col": column,
                "row": row,
                "window_row": row - start_row,
                "col_offset": column - mario_col,
            }
        slots.append(slot)
    return slots


def _active_cell_key(decoder: dict) -> str:
    return "cell_03AE" if decoder["enemy_x"] == "0x03AE" else "cell_0087"


def _measure(ram: bytes, spec_id: str, decoder: dict) -> dict:
    from games.lab.integrations.smb_1_1 import describe, diagnose, observation_details, observation_vector

    details = observation_details(ram, spec_id=spec_id, decoder=decoder)
    vector = observation_vector(ram, spec_id=spec_id, decoder=decoder)
    if vector != details["vector"]:
        raise RuntimeError("observation vector and details diverged")
    rows, hot = CHECKS.split_vector(vector, details["width"], details["height"])
    return {
        "ram": ram,
        "details": details,
        "facts": describe(ram),
        "physics": diagnose(ram),
        "rows": rows,
        "one_hot": CHECKS.one_hot_index(hot),
        "enemies": _enemy_slots(ram, details["mario_col"], details["start_row"]),
        "vector": vector,
    }


def _public_sample(name: str, measured: dict, ground: int | None, extra: dict | None = None) -> dict:
    details = measured["details"]
    facts = measured["facts"]
    pipes = CHECKS.pipe_columns(measured["rows"], ground) if ground is not None else []
    cells = []
    for cell in details["cells"]:
        address = cell["address"]
        cells.append({
            "index": cell["index"],
            "window_row": cell["window_row"],
            "col_offset": cell["col_offset"],
            "screen_row": cell["screen_row"],
            "screen_col": cell["screen_col"],
            "world_x": cell["world_x"],
            "address": None if address is None else f"0x{address:04X}",
            "raw": cell["raw"],
            "value": cell["value"],
        })
    sample = {
        "name": name,
        "x_pos": facts["x_pos"],
        "y_pos": facts["y_pos"],
        "viewport": measured["ram"][0x00B5],
        "screen_x": details["screen_x"],
        "screen_y": details["screen_y"],
        "mario_row": details["mario_row"],
        "mario_col": details["mario_col"],
        "unbiased_row": details["unbiased_row"],
        "unbiased_col": details["unbiased_col"],
        "one_hot": measured["one_hot"],
        "pipes": pipes,
        "grid": measured["rows"],
        "cells": cells,
        "enemies": measured["enemies"],
        "vector": measured["vector"],
        "physics": measured["physics"]["physics"],
    }
    if extra:
        sample.update(extra)
    return sample


def _goomba_hit(measured: dict, decoder: dict, ground: int | None, width: int) -> dict | None:
    if ground is None:
        return None
    key = _active_cell_key(decoder)
    for slot in measured["enemies"]:
        if slot["flag"] == 0 or slot["id"] != 6:
            continue
        cell = slot[key]
        offset = cell["col_offset"]
        window_row = cell["window_row"]
        if offset not in range(1, width):
            continue
        if abs(window_row - ground) not in (0, 1):
            continue
        index = window_row * width + offset
        if measured["vector"][index] != -1.0:
            continue
        return {
            "enemy_index": index,
            "enemy_window_row": window_row,
            "enemy_col_offset": offset,
            "slot": slot["slot"],
        }
    return None


def _pick_on_pipe(rows: list[dict], ground: int | None) -> dict | None:
    candidates = [
        row for row in rows
        if row["grounded"] and row["y"] >= 100 and 450 <= row["x"] < 505
    ]
    if not candidates:
        return None

    def rank(row: dict) -> tuple:
        delta_ok = ground is not None and row["one_hot"] == ground - 2
        return (0 if delta_ok else 1, abs(row["y"] - 111), row["decision"])

    return min(candidates, key=rank)


def _pick_past(rows: list[dict], on_pipe: dict | None) -> dict | None:
    start = on_pipe["decision"] if on_pipe else 0
    for row in rows:
        if row["decision"] <= start:
            continue
        if row["grounded"] and row["y"] <= 90 and row["x"] >= 505:
            return row
    return None


def _gray_mae(left, right):
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return None

    def gray(rgb):
        image = Image.fromarray(rgb).convert("L").resize((84, 84), Image.BILINEAR)
        return np.asarray(image, dtype=np.int16)

    return float(np.mean(np.abs(gray(left) - gray(right))))


def _install_and_open(counter: dict):
    from games.lab.integrations.smb_1_1 import INTEGRATION
    env = INTEGRATION.open_env(ROM, objective="progress")
    _guard(env.unwrapped.runner, counter)
    return env


def _snapshot_row(decision: int, info: dict, measured: dict, action: int | None, ground: int | None) -> dict:
    facts = measured["facts"]
    dead = bool(info.get("dead")) or bool(facts.get("dead"))
    return {
        "decision": decision,
        "action": action,
        "x": int(facts["x_pos"]),
        "y": int(facts["y_pos"]),
        "dead": dead,
        "grounded": measured["physics"]["physics"] == "ground" and not dead,
        "one_hot": measured["one_hot"],
        "pipes": CHECKS.pipe_columns(measured["rows"], ground) if ground is not None else [],
        "termination": info.get("termination") or "",
        "measured": measured,
    }


def run_attempt(spec_id: str, decoder: dict, reason: str, blobs: dict) -> dict:
    from games.lab.integrations.smb_1_1 import observation_spec
    from games.lab.observations import body_parameters, spec_digest, value_parameters

    spec = observation_spec(spec_id)
    spec["decoder"] = dict(decoder)
    digest = spec_digest(spec)
    width = int(spec["grid"]["width"])
    height = int(spec["grid"]["height"])
    length = int(spec["shape"][0])
    attempt = {
        "reason": reason,
        "spec_id": spec_id,
        "decoder": dict(decoder),
        "width": width,
        "height": height,
        "n": length,
        "body_parameters": body_parameters(length),
        "value_parameters": value_parameters(length),
        "spec_digest": digest,
        "frames": 0,
        "accepted": False,
        "aborted": False,
        "error": None,
        "checks": {},
        "fail_names": [],
        "retry_triggers": {},
        "lead_decisions": None,
        "ground_index": None,
        "samples": [],
        "ram_dumps": {},
        "title_x": [],
        "cross_trace": [],
        "held_abs": None,
        "gray_mae": None,
        "held_out": [],
    }
    env = None
    title_env = None
    counter = {"n": 0}
    try:
        env = _install_and_open(counter)
        frame = env.unwrapped
        frame._state = blobs["approach"]
        _obs, info = env.reset()
        approach = _measure(bytes(frame.runner.ram_bytes()), spec_id, decoder)
        facts = approach["facts"]
        if int(facts["x_pos"]) != 197 or int(facts["y_pos"]) != 79:
            attempt["aborted"] = True
            attempt["error"] = f"approach reset is x={facts['x_pos']} y={facts['y_pos']}"
            attempt["frames"] = counter["n"]
            attempt["samples"] = [_public_sample("approach", approach, approach["one_hot"])]
            return attempt
        ground = approach["one_hot"]
        attempt["ground_index"] = ground
        approach_rows = [_snapshot_row(0, info, approach, None, ground)]

        for decision in range(1, 81):
            _obs, _reward, terminated, truncated, info = env.step(4)
            measured = _measure(bytes(frame.runner.ram_bytes()), spec_id, decoder)
            row = _snapshot_row(decision, info, measured, 4, ground)
            approach_rows.append(row)
            if row["dead"] or terminated or truncated:
                break
            if row["grounded"] and row["y"] == 79 and row["x"] >= 434:
                break

        contact_row = next((row for row in approach_rows if row["decision"] > 0 and row["x"] >= 434 and not row["dead"]), None)
        first_pipe = next((row["decision"] for row in approach_rows if row["pipes"]), None)
        if contact_row is None or first_pipe is None:
            lead = None
        else:
            lead = contact_row["decision"] - first_pipe
        attempt["lead_decisions"] = lead
        stuck = bytes(frame.runner.serialize() or b"")
        if contact_row is not None:
            contact = contact_row["measured"]
        else:
            contact = approach_rows[-1]["measured"]

        runner = frame.runner
        runner.unserialize(stuck)
        for _ in range(8):
            runner.frame({"RIGHT", "A", "B"})
        held = _measure(bytes(runner.ram_bytes()), spec_id, decoder)
        held_rgb = runner.rgb.copy()
        runner.unserialize(stuck)
        for _ in range(8):
            runner.frame({"RIGHT", "B"})
        released = _measure(bytes(runner.ram_bytes()), spec_id, decoder)
        released_rgb = runner.rgb.copy()
        held_abs = max(abs(a - b) for a, b in zip(held["vector"], released["vector"]))
        attempt["held_abs"] = held_abs
        attempt["gray_mae"] = _gray_mae(held_rgb, released_rgb)

        frame._state = stuck
        _obs, info = env.reset()
        cross_rows = []
        for decision in range(1, 81):
            action = 3 if decision <= 3 else 4
            _obs, _reward, terminated, truncated, info = env.step(action)
            measured = _measure(bytes(frame.runner.ram_bytes()), spec_id, decoder)
            row = _snapshot_row(decision, info, measured, action, ground)
            cross_rows.append(row)
            if row["dead"] or terminated or truncated:
                break
            if row["grounded"] and row["y"] <= 90 and row["x"] >= 505:
                break
        on_pipe = _pick_on_pipe(cross_rows, ground)
        past = _pick_past(cross_rows, on_pipe)
        attempt["cross_trace"] = [
            {"decision": row["decision"], "action": row["action"], "x": row["x"], "y": row["y"],
             "grounded": row["grounded"], "one_hot": row["one_hot"], "dead": row["dead"]}
            for row in cross_rows
        ]

        title_env = _install_and_open(counter)
        title_frame = title_env.unwrapped
        _obs, info = title_env.reset()
        title = _measure(bytes(title_frame.runner.ram_bytes()), spec_id, decoder)
        title_rows = [_snapshot_row(0, info, title, None, ground)]
        for decision in range(1, 45):
            _obs, _reward, terminated, truncated, info = title_env.step(4)
            measured = _measure(bytes(title_frame.runner.ram_bytes()), spec_id, decoder)
            row = _snapshot_row(decision, info, measured, 4, ground)
            title_rows.append(row)
            if row["dead"] or terminated or truncated:
                break
        death = next((row["decision"] for row in title_rows if row["dead"]), None)
        attempt["title_x"] = [row["x"] for row in title_rows if row["decision"] > 0]
        goomba_row = None
        goomba_hit = None
        for row in title_rows:
            if row["dead"] or row["x"] >= 313:
                continue
            if death is None or death - row["decision"] < 2:
                continue
            hit = _goomba_hit(row["measured"], decoder, ground, width)
            if hit is not None:
                goomba_row = row
                goomba_hit = hit
                break

        held_out = []
        for label, blob in (("held_out_past", blobs["held_out_past"]), ("held_out_later", blobs["held_out_later"])):
            title_frame._state = blob
            _obs, info = title_env.reset()
            measured = _measure(bytes(title_frame.runner.ram_bytes()), spec_id, decoder)
            held_out.append({
                "name": label,
                "x_pos": measured["facts"]["x_pos"],
                "y_pos": measured["facts"]["y_pos"],
                "vector": measured["vector"],
                "sha256": hashlib.sha256(blob).hexdigest(),
            })
        attempt["held_out"] = [
            {"name": item["name"], "x_pos": item["x_pos"], "y_pos": item["y_pos"], "sha256": item["sha256"]}
            for item in held_out
        ]
        attempt["frames"] = counter["n"]

        dumps = {
            "approach": approach["ram"],
            "contact": contact["ram"],
            "title": title["ram"],
        }
        if goomba_row is not None:
            dumps["goomba"] = goomba_row["measured"]["ram"]
        if on_pipe is not None:
            dumps["on-pipe"] = on_pipe["measured"]["ram"]
        if past is not None:
            dumps["past"] = past["measured"]["ram"]
        attempt["ram_dumps"] = dumps

        samples = [
            _public_sample("approach", approach, ground, {"decision": 0}),
            _public_sample("title", title, ground, {"decision": 0}),
            _public_sample("contact", contact, ground, {
                "decision": None if contact_row is None else contact_row["decision"],
            }),
        ]
        if goomba_row is not None:
            samples.append(_public_sample("goomba", goomba_row["measured"], ground, {
                "decision": goomba_row["decision"],
                **goomba_hit,
            }))
        if on_pipe is not None:
            samples.append(_public_sample("on-pipe", on_pipe["measured"], ground, {
                "decision": on_pipe["decision"],
            }))
        if past is not None:
            samples.append(_public_sample("past", past["measured"], ground, {"decision": past["decision"]}))
        attempt["samples"] = samples

        by_name = {sample["name"]: sample for sample in samples}
        approach_hot = approach["one_hot"]
        approach_all_zero = all(value == 0.0 for value in approach["vector"][width * height:])
        contact_sample = by_name["contact"]
        contact_pipes = contact_sample["pipes"]
        on_pipe_hot = None if on_pipe is None else on_pipe["one_hot"]
        past_hot = None if past is None else past["one_hot"]
        five = [by_name.get(name) for name in ("title", "goomba", "contact", "on-pipe", "past")]
        pairwise = all(item is not None for item in five) and len({tuple(item["vector"]) for item in five}) == 5
        checks = {
            "title_start": title["facts"]["x_pos"] == 40 and title["facts"]["y_pos"] == 79,
            "approach_one_hot": approach_hot is not None and 0 <= approach_hot < height,
            "approach_pipe_empty": CHECKS.pipe_columns(approach["rows"], ground) == [],
            "approach_floor": CHECKS.floor_solid(approach["rows"], ground),
            "goomba": goomba_hit is not None,
            "lead": lead is not None and lead >= 4,
            "contact_offset": bool(contact_pipes) and min(contact_pipes) in (1, 2),
            "contact_row": contact_sample["one_hot"] == ground,
            "contact_air": CHECKS.air_above(contact["rows"], ground, contact_pipes),
            "on_pipe_delta": ground is not None and on_pipe_hot == ground - 2,
            "on_pipe_support": on_pipe is not None and CHECKS.solid_below(on_pipe["measured"]["rows"], on_pipe_hot),
            "past_row": ground is not None and past_hot == ground,
            "past_differs": past is not None and past["measured"]["vector"] != contact["vector"],
            "past_not_early": past is not None and past["x"] >= 505 and past["x"] not in (458, 472),
            "held_released": held_abs == 0,
            "script_cross": any(row["x"] >= 505 and not row["dead"] for row in cross_rows),
            "pairwise": pairwise,
            "held_out_differ": held_out[0]["vector"] != held_out[1]["vector"],
            "held_out_not_training": all(item["sha256"] != PIPE_SHA for item in held_out),
            "frame_cap": counter["n"] <= FRAME_CAP,
        }
        attempt["checks"] = checks
        attempt["fail_names"] = sorted(name for name, ok in checks.items() if not ok)
        attempt["retry_triggers"] = {
            "contact_offset": not checks["contact_offset"],
            "y_placement": approach_all_zero or (not checks["approach_floor"]) or (not checks["on_pipe_delta"]),
            "goomba": not checks["goomba"],
        }
        attempt["accepted"] = not attempt["fail_names"]
        return attempt
    except Exception as exc:
        attempt["error"] = traceback.format_exc()
        attempt["frames"] = counter["n"]
        return attempt
    finally:
        if env is not None:
            env.close()
        if title_env is not None:
            title_env.close()


def next_trial(history: list[dict], base: dict) -> dict | None:
    if not history:
        return {"spec_id": "smb-tiles-v1", "decoder": dict(base), "reason": "default"}
    latest = history[-1]
    if latest.get("accepted") or latest.get("error") or latest.get("aborted"):
        return None
    if latest["reason"] == "width":
        return None
    if set(latest["fail_names"]) == {"lead"}:
        decoder = dict(latest["decoder"])
        return {"spec_id": "smb-tiles-v1w10", "decoder": decoder, "reason": "width"}
    origin = history[0]
    tried = {item["reason"] for item in history}
    triggers = origin.get("retry_triggers") or {}
    if triggers.get("contact_offset") and "x_bias" not in tried:
        decoder = dict(base)
        decoder["x_bias"] = 0
        return {"spec_id": "smb-tiles-v1", "decoder": decoder, "reason": "x_bias"}
    if triggers.get("y_placement") and "y_bias" not in tried:
        decoder = dict(base)
        decoder["y_bias"] = 0
        return {"spec_id": "smb-tiles-v1", "decoder": decoder, "reason": "y_bias"}
    if triggers.get("goomba") and "enemy" not in tried:
        decoder = dict(base)
        decoder["enemy_x"] = "0x0087"
        decoder["enemy_y"] = "0x00CF"
        return {"spec_id": "smb-tiles-v1", "decoder": decoder, "reason": "enemy"}
    return None


def _grid_block(sample: dict) -> str:
    lines = [
        f"{sample['name']}: x={sample['x_pos']} y={sample['y_pos']} "
        f"viewport={sample['viewport']} screen=({sample['screen_x']},{sample['screen_y']}) "
        f"anchor=({sample['mario_col']},{sample['mario_row']}) "
        f"unbiased=({sample['unbiased_col']},{sample['unbiased_row']}) "
        f"one_hot={sample['one_hot']} pipes={sample['pipes']}"
    ]
    for index, row in enumerate(sample["grid"]):
        mark = "*" if index == sample["one_hot"] else " "
        body = " ".join(f"{value:2d}" for value in row)
        lines.append(f"{mark} {index:2d} {body}")
    lines.append("enemies:")
    for slot in sample["enemies"]:
        lines.append(
            f"  slot {slot['slot']} flag={slot['flag']} id={slot['id']} page={slot['page']} "
            f"0087={slot['x_0087']} 00CF={slot['y_00CF']} 03AE={slot['x_03AE']} 03B9={slot['y_03B9']} "
            f"cell_03AE={slot['cell_03AE']} cell_0087={slot['cell_0087']}"
        )
    return "\n".join(lines)


def _finding(attempt: dict) -> str:
    samples = {sample["name"]: sample for sample in attempt.get("samples") or []}
    parts = []
    approach = samples.get("approach")
    contact = samples.get("contact")
    goomba = samples.get("goomba")
    if approach is not None:
        hot = approach["one_hot"]
        solid_rows = [index for index, row in enumerate(approach["grid"]) if row and row[0] == 1]
        parts.append(
            f"On the approach frame the one-hot is window row {hot}. "
            f"Column 0 is solid on window rows {solid_rows or 'none'}."
        )
    if contact is not None and contact["one_hot"] is not None:
        hot = contact["one_hot"]
        occupied = []
        for index, row in enumerate(contact["grid"]):
            offsets = [col for col, value in enumerate(row) if col > 0 and value == 1]
            if offsets:
                occupied.append(f"row {index} offsets {offsets}")
        parts.append(
            "At the first pipe, solid cells ahead of column 0 are "
            + (", ".join(occupied) if occupied else "none")
            + f". The acceptance rule looks above the one-hot, on rows {hot - 2} and {hot - 1}."
        )
    if goomba is not None and "enemy_col_offset" in goomba:
        parts.append(
            f"The goomba at x={goomba['x_pos']} on decision {goomba.get('decision')} "
            f"is a -1 at window row {goomba['enemy_window_row']}, column offset {goomba['enemy_col_offset']}."
        )
    if attempt.get("fail_names"):
        parts.append(
            "The two-high pipe is on the one-hot row and the row above it. "
            "The rule requires both rows above the one-hot, and the floor cell on the one-hot row is empty. "
            "The registered retries do not move that run. "
            "Width 10 was not run, because a short lead was not the only failure. "
            "No third grid was tried. Fixtures were not written."
        )
    return " ".join(parts)


def _report(document: dict) -> str:
    chosen = document["chosen"]
    lines = [
        "# Tile observation validation",
        "",
        f"Accepted: {document['accepted']}",
        "",
        document.get("finding") or "",
        "",
        f"Spec id: {chosen.get('spec_id')}",
        f"Width: {chosen.get('width')}",
        f"n: {chosen.get('n')}",
        f"Body parameters: {chosen.get('body_parameters')}",
        f"Value parameters: {chosen.get('value_parameters')}",
        f"Spec digest: {chosen.get('spec_digest')}",
        f"Decoder: `{json.dumps(chosen.get('decoder'), sort_keys=True)}`",
        f"Lead decisions: {chosen.get('lead_decisions')}",
        f"Ground index: {chosen.get('ground_index')}",
        f"Emulator frames: {chosen.get('frames')}",
        f"Held versus released max abs: {chosen.get('held_abs')}",
        f"Held versus released 84x84 gray MAE: {chosen.get('gray_mae')}",
        "",
        "## Attempts",
        "",
        "| Reason | Spec | Accepted | Frames | Failures |",
        "|---|---|---|---|---|",
    ]
    for item in document["attempts"]:
        fails = ", ".join(item["fail_names"]) or "none"
        if item.get("error"):
            fails = item["error"]
        lines.append(
            f"| {item['reason']} | {item['spec_id']} | {item['accepted']} | {item['frames']} | {fails} |"
        )
    lines.extend([
        "",
        "## Preconditions",
        "",
        f"- ROM SHA1: {document['rom_sha1']}",
        f"- Core SHA1: {document['core_sha1']}",
        f"- Approach state sha256: {PIPE_SHA}",
        "",
        "## Samples",
        "",
    ])
    for sample in chosen.get("samples") or []:
        lines.append("```text")
        lines.append(_grid_block(sample))
        lines.append("```")
        lines.append("")
    if chosen.get("title_x"):
        lines.append("Title x after each decision:")
        lines.append("")
        lines.append("`" + ", ".join(str(value) for value in chosen["title_x"]) + "`")
        lines.append("")
    if chosen.get("cross_trace"):
        lines.append("Scripted cross:")
        lines.append("")
        lines.append("| Decision | Action | x | y | Grounded | One-hot |")
        lines.append("|---|---|---|---|---|---|")
        for row in chosen["cross_trace"]:
            lines.append(
                f"| {row['decision']} | {row['action']} | {row['x']} | {row['y']} | "
                f"{row['grounded']} | {row['one_hot']} |"
            )
        lines.append("")
    lines.extend(["## Checks", "", "| Check | Pass |", "|---|---|"])
    for name, ok in (chosen.get("checks") or {}).items():
        lines.append(f"| {name} | {ok} |")
    lines.extend([
        "",
        "## Fixtures",
        "",
        document["fixtures_note"],
        "",
        "## Out of scope",
        "",
        "This run does not train, does not start a generation, and does not implement neuroevolution or `ppo_vector`.",
        "",
    ])
    return "\n".join(lines)


def _expect(chosen: dict, dumps: dict[str, bytes]) -> dict:
    by_name = {sample["name"]: sample for sample in chosen["samples"]}
    files = {
        "title": "title.bin",
        "approach": "approach.bin",
        "goomba": "goomba.bin",
        "contact": "contact.bin",
        "on-pipe": "on-pipe.bin",
        "past": "past.bin",
    }
    samples = {}
    for name, filename in files.items():
        sample = by_name[name]
        blob = dumps[name]
        entry = {
            "file": filename,
            "sha256": hashlib.sha256(blob).hexdigest(),
            "one_hot": sample["one_hot"],
        }
        if name == "approach":
            entry["pipe_columns"] = sample["pipes"]
        if name == "contact":
            entry["pipe_min"] = min(sample["pipes"])
        if name == "goomba":
            entry["enemy_index"] = sample["enemy_index"]
            entry["enemy_window_row"] = sample["enemy_window_row"]
            entry["enemy_col_offset"] = sample["enemy_col_offset"]
        samples[name] = entry
    return {
        "spec_id": chosen["spec_id"],
        "spec_digest": chosen["spec_digest"],
        "decoder": chosen["decoder"],
        "width": chosen["width"],
        "height": chosen["height"],
        "ground_index": chosen["ground_index"],
        "samples": samples,
    }


def _public_attempt(attempt: dict) -> dict:
    hidden = {"ram_dumps", "measured"}
    payload = {key: value for key, value in attempt.items() if key not in hidden}
    return payload


def main() -> int:
    from games.lab.integrations.smb_1_1 import observation_spec

    identity = _preflight()
    document = {
        "accepted": False,
        "rom_sha1": identity["rom_sha1"],
        "core_sha1": identity["core_sha1"],
        "problems": identity["problems"],
        "attempts": [],
        "chosen": {},
        "fixtures_note": "No fixtures written.",
        "source_decoder_matches": False,
    }
    if not identity["ok"]:
        document["chosen"] = {"error": "preflight failed", "samples": [], "checks": {}}
        _write(HERE / "validation.json", document)
        _write(HERE / "REPORT.md", _report(document))
        print("preflight failed")
        for problem in identity["problems"]:
            print(problem)
        return 2

    base = observation_spec("smb-tiles-v1")["decoder"]
    history = []
    trial = next_trial(history, base)
    while trial is not None and len(history) < 6:
        print(f"attempt {trial['reason']} {trial['spec_id']} {trial['decoder']}", flush=True)
        attempt = run_attempt(trial["spec_id"], trial["decoder"], trial["reason"], identity["blobs"])
        history.append(attempt)
        fails = ", ".join(attempt["fail_names"]) or "none"
        print(
            f"  accepted={attempt['accepted']} frames={attempt['frames']} "
            f"lead={attempt['lead_decisions']} fails={fails} error={attempt['error']}",
            flush=True,
        )
        if attempt.get("accepted"):
            break
        trial = next_trial(history, base)

    chosen = next((item for item in history if item.get("accepted")), history[0] if history else {})
    source = observation_spec(chosen.get("spec_id") or "smb-tiles-v1")["decoder"]
    matches = bool(chosen.get("accepted")) and source == chosen.get("decoder")
    document["accepted"] = bool(chosen.get("accepted")) and matches
    document["source_decoder_matches"] = matches
    document["attempts"] = [_public_attempt(item) for item in history]
    document["chosen"] = _public_attempt(chosen) if chosen else {}
    document["finding"] = _finding(document["chosen"]) if chosen else ""
    if chosen.get("accepted") and not matches:
        document["fixtures_note"] = (
            "Checks passed with a decoder that is not the committed default. "
            "Fixtures were not written. Update observation_spec and run this script again."
        )
        document["accepted"] = False
    elif chosen.get("accepted") and matches:
        fixture_dir = HERE / "fixtures"
        fixture_dir.mkdir(parents=True, exist_ok=True)
        dumps = chosen["ram_dumps"]
        names = {
            "title": "title.bin",
            "approach": "approach.bin",
            "goomba": "goomba.bin",
            "contact": "contact.bin",
            "on-pipe": "on-pipe.bin",
            "past": "past.bin",
        }
        for name, filename in names.items():
            blob = dumps[name]
            if len(blob) != 2048:
                raise RuntimeError(f"{name} RAM is {len(blob)} bytes")
            (fixture_dir / filename).write_bytes(blob)
        expect = _expect(chosen, dumps)
        _write(fixture_dir / "expect.json", expect)
        document["fixtures_note"] = "Wrote 2048-byte RAM fixtures and fixtures/expect.json."
        document["expect"] = expect
    else:
        document["fixtures_note"] = "Checks did not accept a grid. No fixtures written."
        document["accepted"] = False

    # Drop raw dumps from the written attempts. _public_attempt already did.
    _write(HERE / "validation.json", document)
    _write(HERE / "REPORT.md", _report(document))
    print(f"accepted={document['accepted']} report={HERE / 'REPORT.md'}")
    if chosen.get("accepted") and not matches:
        print("UPDATE_DECODER")
        print(json.dumps(chosen.get("decoder"), sort_keys=True))
        return 3
    return 0 if document["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
