"""One line per lab run: rate, timing, outcome and how the aiming went. For comparing runs at different rates.

    python games/arcade/bzone/scripts/summarize.py runs/*arcade_bzone-lab*.jsonl
"""
import json
import statistics
import sys


def summarize(path):
    records = [json.loads(line) for line in open(path)]
    run = records[0]
    ticks = [r for r in records if r.get("event") == "tick"]
    summary = next((r for r in records if r.get("event") == "summary"), {})
    if not ticks:
        return None
    alive = [r for r in ticks if r["state"]["playing"] and not r["facts"]["dying"]]
    radar = [r for r in alive if r["facts"]["enemy_on_radar"]]
    kills = ticks[-1]["state"]["hits"] - ticks[0]["state"]["hits"]
    deaths = sum("life lost" in r["changes"] for r in ticks)
    shots = sum(1 for r in ticks if ["1", "BUTTON_1"] in [list(map(str, p)) for p in r["pressed"]])
    misses = [abs(r["facts"]["miss_by"]) for r in radar if r["facts"].get("miss_by") is not None]
    clock = summary.get("clock", {})
    return {"run": run["label"], "policy": run["policy"], "hz": run["hz"], "seconds": ticks[-1]["t"],
            "kills": kills, "deaths": deaths, "shots": shots,
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
