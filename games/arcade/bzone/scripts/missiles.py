"""Every missile in lab runs: how it ended (shot down, or it got the tank), how long it lasted, the shots fired at it,
and the height and distance at each shot.

    python games/arcade/bzone/scripts/missiles.py runs/*missile*.jsonl
"""
import json
import sys


def missiles(path):
    ticks = [json.loads(line) for line in open(path) if '"event": "tick"' in line]
    out, current = [], None
    for tick in ticks:
        height = tick["state"].get("missile_height")
        if height is not None and current is None:
            current = {"start": tick["t"], "shots": [], "end": None, "how": "still out"}
        if current is None:
            continue
        fired = ["1", "BUTTON_1"] in [list(map(str, p)) for p in tick["pressed"]]
        if fired:
            current["shots"].append((height, tick["facts"].get("enemy_distance"),
                                     tick["facts"].get("enemy_bearing_deg")))
        if any(c.startswith("score") for c in tick["changes"]):
            current["how"] = "shot down"
        if "life lost" in tick["changes"]:
            current["how"] = "it got the tank"
        if height is None or current["how"] != "still out":
            current["end"] = tick["t"]
            out.append(current)
            current = None
    if current:
        out.append(current)
    return out


def main(paths):
    total = {"shot down": 0, "it got the tank": 0, "still out": 0}
    for path in paths:
        for m in missiles(path):
            total[m["how"]] += 1
            lasted = (m["end"] or m["start"]) - m["start"]
            print(f"{path[-20:-6]} t={m['start']:6.1f} {m['how']:16s} after {lasted:4.1f} s, shots: "
                  + ", ".join(f"h{h} d{d} {b:+.0f}deg" if b is not None else f"h{h} d{d}" for h, d, b in m["shots"]))
    print(total)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
