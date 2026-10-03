"""Benchmark the S1M driver's questions offline: 100 fixed situations from lab games, each question scored.

    python games/arcade/bzone/scripts/benchmark.py --model tev1:latest [--model nimble] [--out runs/bench.json]
    python games/arcade/bzone/scripts/benchmark.py --build   (re-sample the situations from runs/: rarely)

The situations (tests/fixtures/bench_situations.json) are moments from lab games, balanced by kind: enemy ahead,
behind or out of sight, a shot just heard, a shot lined up, a missile. Each of the driver's questions (pilot.py) is
asked on its own, worded exactly as the driver words it, and scored against the game's facts:

  goal      a sensible goal: missile -> missile; shot heard -> evade; behind or out of sight -> search; lined up ->
            attack; ahead -> attack (or approach, while it can fire back)
  turn      under ATTACK, the first tread command turns the enemy toward the sights (enemy 4-90 degrees off)
  duration  given a pivot toward it, the duration that leaves it closest to the sights (or the next one)
  fire      fire now exactly when the shot would hit, else hold

The scoring is the benchmark's, not the player's: it measures the model, it never plays.
"""
import argparse
import collections
import json
import random
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from arcadekit.systemone import OllamaSystemOne  # noqa: E402
from games.arcade.bzone import pilot as P  # noqa: E402
from games.arcade.bzone.facts import Facts  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
SITUATIONS = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "bench_situations.json"
QUOTA = {"ahead": 40, "behind": 20, "shot heard": 15, "lined up": 15, "missile": 10}


def kind_of(x):
    b = x["enemy_bearing_deg"]
    if x["enemy_kind"] == "missile":
        return "missile"
    if x["enemy_shell"] == "flying":
        return "shot heard"
    if b is None or abs(b) >= 90:
        return "behind"
    return "lined up" if x["on_target"] else "ahead"


def build(seed=7):
    fields = set(Facts.__dataclass_fields__)
    pool = collections.defaultdict(list)
    for path in sorted((ROOT / "runs").glob("*bzone-lab*.jsonl")):
        for line in open(path):
            if '"event": "tick"' not in line:
                continue
            r = json.loads(line)
            x = r.get("facts")
            if not x or not fields <= set(x) or not r["state"]["playing"] or x["dying"] or x["enemy_side"] == "none":
                continue
            pool[kind_of(x)].append({"run": path.stem, "t": r["t"], "facts": x})
    rng = random.Random(seed)
    chosen = []
    for kind, n in QUOTA.items():
        for s in rng.sample(pool[kind], min(n, len(pool[kind]))):
            chosen.append({**s, "kind": kind})
    SITUATIONS.write_text(json.dumps({"note": "Moments from Battlezone lab games (3 October 2026), sampled by kind "
                                              "for scripts/benchmark.py", "situations": chosen}, indent=0))
    return chosen


def facts_of(s):
    x = dict(s["facts"])
    x["obstacles_in_view"] = tuple(tuple(o) for o in x.get("obstacles_in_view") or ())
    return Facts(**x)


READY = SimpleNamespace(tank=SimpleNamespace(fire=0))  # the gun is taken as ready: the logs do not keep it


def sensible_goals(f, kind):
    if kind == "missile":
        return {"missile"}
    if kind == "shot heard":
        return {"evade"}
    if kind == "behind":
        return {"search"}
    if kind == "lined up":
        return {"attack"}
    safe = f.enemy_holds_fire or f.enemy_shell != "none" or (f.enemy_aim is not None and abs(f.enemy_aim) > 20)
    return {"attack"} if safe else {"attack", "approach"}


class Bench:
    def __init__(self, model):
        self.client = OllamaSystemOne(model=model, timeout=60)
        self.latency = []

    def ask(self, text, instructions, criteria):
        items = list(criteria.items())
        random.shuffle(items)
        t0 = time.time()
        reply = self.client.ask(text, {"q": {"type": "choice", "instructions": instructions, "criteria": dict(items)}})
        self.latency.append((time.time() - t0) * 1000)
        return reply["answers"]["q"]["choice"]

    def run(self, situations):
        results = collections.defaultdict(list)
        for s in situations:
            f, kind = facts_of(s), s["kind"]
            text = P.situation(READY, f)
            b = f.enemy_bearing_deg
            # goal
            goals = P.goals_now(f)
            if len(goals) > 1:
                pick = self.ask(text, P.INSTRUCTIONS + " Which goal now?",
                                {g: f"{P.GOALS[g]} Now: {why}" for g, why in goals.items()})
                ok = pick in sensible_goals(f, kind)
                results["goal"].append({"ok": ok, "kind": kind, "answer": pick, "offered": list(goals),
                                        "expected": sorted(sensible_goals(f, kind)), "text": text})
            if b is None or not 4 <= abs(b) < 90:
                pass
            else:
                attack = f"{P.INSTRUCTIONS} {P.GOALS['attack']}"
                # turn
                pick = self.ask(text, attack + " First, which tread command?",
                                {n: f"{w}; in 0.5 s: {P.effect(f, b, n, 0.5, f.obstacle_ahead, f.obstacle_behind)}"
                                 for n, (_, w, _, _) in P.TREADS.items()})
                swing = P.TREADS[pick][2]
                ok = swing != 0 and (swing > 0) == (b > 0)
                results["turn"].append({"ok": ok, "kind": kind, "answer": pick, "bearing": b, "text": text})
                # duration, given a pivot toward it
                cmd = "pivot_left" if b > 0 else "pivot_right"
                rate = P.TREADS[cmd][2]
                durations = {f"{d:g}s": f"{cmd} for {d:g} s: {P.effect(f, b, cmd, d, f.obstacle_ahead, f.obstacle_behind)}"
                             for d in P.DURATIONS}
                pick = self.ask(text, attack + f" You chose {cmd}. For how long?", durations)
                order = sorted(P.DURATIONS, key=lambda d: abs(b - rate * d))
                chosen = float(pick[:-1])
                ideal = order[0]
                near = abs(P.DURATIONS.index(chosen) - P.DURATIONS.index(ideal)) <= 1
                results["duration"].append({"ok": chosen == ideal, "near": near, "kind": kind, "answer": chosen,
                                            "ideal": ideal, "bearing": b, "text": text})
            # fire (the enemy in range and in front)
            if f.enemy_distance is not None and b is not None and abs(b) < 90 and f.enemy_kind == "tank":
                verdict = P.shot(f, b)
                pick = self.ask(text, "Fire only if the shot HITS. When?",
                                {"now": f"fire now: the shot {verdict}", "hold": "hold fire: keep the shell for a shot "
                                                                                 "that hits"})
                hits = verdict == "HITS"
                results["fire"].append({"ok": (pick == "now") == hits, "hits": hits, "kind": kind, "answer": pick,
                                        "text": text})
        return results


def summary(results):
    out = {}
    for q, rows in results.items():
        out[q] = {"n": len(rows), "right": sum(r["ok"] for r in rows)}
        if q == "duration":
            out[q]["within_one"] = sum(r["near"] for r in rows)
        if q == "fire":
            out[q]["hits_fired"] = sum(r["ok"] for r in rows if r["hits"])
            out[q]["hits"] = sum(r["hits"] for r in rows)
            out[q]["misses_held"] = sum(r["ok"] for r in rows if not r["hits"])
            out[q]["misses"] = sum(not r["hits"] for r in rows)
        by_kind = collections.defaultdict(lambda: [0, 0])
        for r in rows:
            by_kind[r["kind"]][0] += r["ok"]
            by_kind[r["kind"]][1] += 1
        out[q]["by_kind"] = {k: f"{a}/{b}" for k, (a, b) in by_kind.items()}
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", action="append", default=[])
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--out", default=str(ROOT / "runs" / f"bench-{time.strftime('%Y%m%d-%H%M%S')}.json"))
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args(argv)
    situations = build() if args.build or not SITUATIONS.exists() else json.loads(SITUATIONS.read_text())["situations"]
    report = {"situations": len(situations), "kinds": dict(collections.Counter(s["kind"] for s in situations)),
              "models": {}}
    for model in args.model or ["tev1:latest"]:
        random.seed(args.seed)
        bench = Bench(model)
        bench.ask("warm-up", "Pick.", {"a": "a", "b": "b"})
        bench.latency.clear()
        t0 = time.time()
        results = bench.run(situations)
        report["models"][model] = {"summary": summary(results), "latency_ms_median": round(statistics.median(
            bench.latency)), "seconds": round(time.time() - t0), "results": results}
        s = report["models"][model]["summary"]
        print(f"{model}: " + " | ".join(f"{q} {v['right']}/{v['n']}" + (f" (within one step {v['within_one']})"
                                                                        if q == "duration" else "") +
                                        (f" (fired at {v['hits_fired']}/{v['hits']} hits, held {v['misses_held']}/"
                                         f"{v['misses']} misses)" if q == "fire" else "")
                                        for q, v in s.items())
              + f" | {report['models'][model]['latency_ms_median']} ms a question")
    Path(args.out).write_text(json.dumps(report, indent=1))
    print(f"report: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
