"""Every enemy shot in lab runs, scored: where it came from (off the nose or near it), what the policy did about it,
how close the shell finally passed (its true path, logged as shell_true) and whether it killed.

    python games/arcade/bzone/scripts/dodges.py runs/*abc-g*.jsonl
"""
import collections
import json
import re
import sys


def shots(path):
    ticks = [json.loads(line) for line in open(path) if '"event": "tick"' in line]
    for i, tick in enumerate(ticks):
        if "enemy fired" not in tick["changes"]:
            continue
        flight = []
        for later in ticks[i:i + 25]:
            if not 0 < later["state"]["enemy_fire"] < 0x80 and later is not tick:
                break
            flight.append(later)
        passes = [abs(t["state"]["shell_true"][0]) for t in flight if t["state"].get("shell_true", [None])[0] is not None]
        bearing = tick["facts"].get("enemy_bearing")
        killed = any("life lost" in t["changes"] for t in ticks[i:i + 25])
        did = re.sub(r"[-+]?\d+(\.\d+)?", "#", (flight[1] if len(flight) > 1 else tick)["why"]).split(" (")[0]
        yield {"from": "unknown" if bearing is None else "near the nose" if abs(bearing) < 0x10 else "off the nose",
               "did": did[:60], "closest": min(passes) if passes else None, "killed": killed}


def main(paths):
    rows = collections.defaultdict(list)
    for path in paths:
        policy = json.loads(open(path).readline()).get("policy")
        for shot in shots(path):
            rows[(policy, shot["from"])].append(shot)
    for (policy, where), group in sorted(rows.items()):
        killed = sum(s["killed"] for s in group)
        print(f"{policy:22s} {where:14s} {len(group):3d} shots, {len(group) - killed:3d} survived")
        for did, n in collections.Counter(s["did"] for s in group).most_common(3):
            print(f"{'':38s}{n:3d} x {did}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
