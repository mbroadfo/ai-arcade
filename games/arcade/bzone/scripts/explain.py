"""Read a lab run back: for each tick, the state it saw, what the policy held and why, and what the next observation
showed (heading change in degrees, distance moved, outcome changes).

    python games/arcade/bzone/scripts/explain.py runs/<label>.jsonl [--from 10 --to 15] [--changes-only]
"""
import argparse
import json
import math
import sys


def degrees(angle_units):
    return angle_units * 360 / 256


def lines(records, start=0.0, end=math.inf, changes_only=False):
    ticks = [r for r in records if r.get("event") == "tick"]
    out = []
    for r, nxt in zip(ticks, ticks[1:] + [None]):
        if not start <= r["t"] <= end:
            continue
        s = r["state"]
        acted = r["pressed"] or r["released"]
        if changes_only and not acted and not r["changes"]:
            continue
        text = (f"{r['t']:8.3f} s  tick {r['tick']}  frame {r['frame']}{'' if r['new_frame'] else ' (same)'}  "
                f"obs age {r['obs_age_ms']:.0f} ms  heading {s['angle']} ({degrees(s['angle']):.0f} deg)  "
                f"pos ({s['x']}, {s['y']})  lives {s['lives']}")
        f = r.get("facts")
        if f:
            text += (f"\n          facts: enemy {f['enemy_side']}"
                     + (f" {f['enemy_bearing_deg']:+.0f} deg" if f["enemy_bearing_deg"] is not None else "")
                     + (f", on radar at {f['enemy_distance']}" if f["enemy_on_radar"] else ", off radar")
                     + (f", shot would pass {f['miss_by']:+d} of radius {f['hit_radius']}" if f.get("miss_by") is not None else "")
                     + (", ON TARGET" if f.get("on_target") else ""))
        text += f"\n          -> {r['why']}: hold {r['action_words']}"
        if acted:
            text += f"  (pressed {r['pressed']}, released {r['released']}; broker {r['broker_ms']:.0f} ms)"
        if nxt:
            n = nxt["state"]
            turn = (n["angle"] - s["angle"] + 128) % 256 - 128
            moved = math.hypot(n["x"] - s["x"], n["y"] - s["y"])
            text += (f"\n          next obs +{nxt['t'] - r['t']:.3f} s: heading {turn:+d} ({degrees(turn):+.1f} deg), "
                     f"moved {moved:.0f}")
        if r["changes"]:
            text += f"\n          ! {', '.join(r['changes'])}"
        out.append(text)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("log")
    parser.add_argument("--from", dest="start", type=float, default=0.0)
    parser.add_argument("--to", dest="end", type=float, default=math.inf)
    parser.add_argument("--changes-only", action="store_true", help="only ticks that pressed or released something "
                        "or saw an outcome change")
    args = parser.parse_args(argv)
    records = [json.loads(line) for line in open(args.log)]
    for text in lines(records, args.start, args.end, args.changes_only):
        print(text)
    summary = [r for r in records if r.get("event") == "summary"]
    if summary:
        print("\nclock:", json.dumps(summary[-1]["clock"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
