"""One line per lab run: rate, timing, outcome and how the aiming went. For comparing runs at different rates.

    python games/arcade/bzone/scripts/summarize.py runs/*arcade_bzone-lab*.jsonl
"""
import json
import math
import statistics
import sys


def wrap16(v):
    return (v + 0x8000) % 0x10000 - 0x8000


def summarize(path):
    records = [json.loads(line) for line in open(path)]
    run = records[0]
    ticks = [r for r in records if r.get("event") == "tick"]
    summary = next((r for r in records if r.get("event") == "summary"), {})
    if not ticks:
        return None
    alive = [r for r in ticks if r["state"]["playing"] and not r["facts"]["dying"]]
    radar = [r for r in alive if r["facts"]["enemy_on_radar"]]
    # A kill raises the score (HITS, thousands in BCD); older logs have no score changes, only "hits a->b"
    kills = sum(any(c.startswith(("score", "hits ")) for c in r["changes"]) for r in ticks)
    deaths = sum("life lost" in r["changes"] for r in ticks)
    shots = sum(1 for r in ticks if ["1", "BUTTON_1"] in [list(map(str, p)) for p in r["pressed"]])
    misses = [abs(r["facts"]["miss_by"]) for r in radar if r["facts"].get("miss_by") is not None]
    clock = summary.get("clock", {})
    # Movement: distance driven while alive (a respawn's jump is not driving), and time standing still while an enemy
    # that may fire is there (the exposure the doctrine says to avoid)
    moved, still = 0.0, 0
    for a, b in zip(ticks, ticks[1:]):
        if b not in alive or a not in alive:
            continue
        step = math.hypot(wrap16(b["state"]["x"] - a["state"]["x"]), wrap16(b["state"]["y"] - a["state"]["y"]))
        if step < 5000:
            moved += step
        f = b["facts"]
        if step == 0 and f.get("enemy_side") not in (None, "none") and f.get("enemy_holds_fire") is False:
            still += 1
    fired = [r["t"] for r in ticks if "enemy fired" in r["changes"]]
    lost = [r["t"] for r in ticks if "life lost" in r["changes"]]
    survived = sum(not any(0 <= d - f <= 3 for d in lost) for f in fired)  # no life lost within 3 s of the shot
    return {"run": run["label"], "policy": run["policy"], "hz": run["hz"], "seconds": ticks[-1]["t"],
            "score": ticks[-1]["state"].get("score"), "kills": kills, "deaths": deaths, "shots": shots,
            "distance": round(moved), "still_threatened_s": round(still / run["hz"], 1) if any(
                "enemy_holds_fire" in r["facts"] for r in ticks) else None,
            "enemy_shots": len(fired), "enemy_shots_survived": survived,
            "blocked_s": round(sum(1 for r in alive if r["state"].get("blocked")) / run["hz"], 1)
            if any("blocked" in r["state"] for r in ticks) else None,
            "on_target_share": round(sum(bool(r["facts"].get("on_target")) for r in radar) / len(radar), 2) if radar else None,
            "miss_median": round(statistics.median(misses)) if misses else None,
            "radar_share": round(len(radar) / len(alive), 2) if alive else None,
            "interval_ms_p90": round(clock["interval_ms_p90"], 1) if clock.get("interval_ms_p90") else None,
            "obs_age_ms_p50": round(statistics.median(r["obs_age_ms"] for r in ticks), 1)}


def main(paths):
    for path in paths:
        row = summarize(path)
        if row:
            print(json.dumps(row))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
