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


# Wording variants for the weak questions: (fire options + extra state text) and (duration option text). "F0"/"D0" are
# the driver's wording now (pilot.py); a winner is copied into pilot.py.
def fire_f0(f, b, verdict):  # the driver's own (pilot.py), now the F2 wording
    return P.fire_question(f, b)


def fire_old(f, b, verdict):  # the driver's wording before 3 October's benchmark: the verdict in the options
    return {"now": f"fire now: the shot {verdict}", "hold": "hold fire: keep the shell for a shot that hits"}, ""


def fire_f1(f, b, verdict):
    hit = verdict == "HITS"
    return ({"now": "fire now: the shot HITS and destroys the enemy" if hit else
             f"fire now: WASTED, the shot {verdict} units and the gun reloads for 1.4 s",
             "hold": "hold fire: the enemy gets away" if hit else "hold fire: keep the shell for a shot that hits"}, "")


def fire_f2(f, b, verdict):
    return {"now": "fire now", "hold": "hold fire"}, (" A shot fired now HITS." if verdict == "HITS" else
                                                       f" A shot fired now {verdict}: it would be wasted.")


FIRE_VARIANTS = {"F0": fire_f0, "Fold": fire_old, "F1": fire_f1, "F2": fire_f2}


def duration_d0(f, b, cmd, d):  # the driver's own (pilot.py), now the D1 wording
    return P.duration_text(f, b, cmd, d)


def duration_old(f, b, cmd, d):  # before 3 October's benchmark: where the enemy ends up, closer or farther
    return f"{cmd} for {d:g} s: {P.effect(f, b, cmd, d, f.obstacle_ahead, f.obstacle_behind)}"


def duration_d1(f, b, cmd, d):
    after = b - P.TREADS[cmd][2] * d
    if abs(after) < 1.5:
        words = "the enemy ends IN YOUR SIGHTS"
    elif (after > 0) == (b > 0):
        words = f"{abs(after):.0f} deg still to turn"
    else:
        words = f"turns PAST it by {abs(after):.0f} deg"
    return f"{cmd} for {d:g} s: {words}"


DURATION_VARIANTS = {"D0": duration_d0, "Dold": duration_old, "D1": duration_d1}


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
    def __init__(self, model, fire="F0", duration="D0", only=None):
        self.client = OllamaSystemOne(model=model, timeout=60)
        self.latency = []
        self.fire, self.duration = FIRE_VARIANTS[fire], DURATION_VARIANTS[duration]
        self.only = set(only) if only else None

    def wants(self, q):
        return self.only is None or q in self.only

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
            if len(goals) > 1 and self.wants("goal"):
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
                pick = None if not self.wants("turn") else self.ask(text, attack + " First, which tread command?",
                                {n: f"{w}; in 0.5 s: {P.effect(f, b, n, 0.5, f.obstacle_ahead, f.obstacle_behind)}"
                                 for n, (_, w, _, _) in P.TREADS.items()})
                if pick:
                    swing = P.TREADS[pick][2]
                    ok = swing != 0 and (swing > 0) == (b > 0)
                    results["turn"].append({"ok": ok, "kind": kind, "answer": pick, "bearing": b, "text": text})
                # duration, given a pivot toward it
                cmd = "pivot_left" if b > 0 else "pivot_right"
                rate = P.TREADS[cmd][2]
                durations = {f"{d:g}s": self.duration(f, b, cmd, d) for d in P.DURATIONS}
                pick = self.ask(text, attack + f" You chose {cmd}. For how long?", durations) \
                    if self.wants("duration") else None
                if pick:
                    order = sorted(P.DURATIONS, key=lambda d: abs(b - rate * d))
                    chosen = float(pick[:-1])
                    ideal = order[0]
                    near = abs(P.DURATIONS.index(chosen) - P.DURATIONS.index(ideal)) <= 1
                    results["duration"].append({"ok": chosen == ideal, "near": near, "kind": kind, "answer": chosen,
                                                "ideal": ideal, "bearing": b, "text": text})
            # fire (the enemy in range and in front)
            if f.enemy_distance is not None and b is not None and abs(b) < 90 and f.enemy_kind == "tank" \
                    and self.wants("fire"):
                verdict = P.shot(f, b)
                options, extra = self.fire(f, b, verdict)
                pick = self.ask(text + extra, "Fire only if the shot HITS. When?", options)
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
    parser.add_argument("--fire", action="append", default=[], choices=sorted(FIRE_VARIANTS),
                        help="fire wording variants to compare (default F0, the driver's)")
    parser.add_argument("--duration", action="append", default=[], choices=sorted(DURATION_VARIANTS),
                        help="duration wording variants to compare (default D0, the driver's)")
    parser.add_argument("--only", help="comma-separated questions to ask (goal,turn,duration,fire)")
    args = parser.parse_args(argv)
    situations = build() if args.build or not SITUATIONS.exists() else json.loads(SITUATIONS.read_text())["situations"]
    report = {"situations": len(situations), "kinds": dict(collections.Counter(s["kind"] for s in situations)),
              "models": {}}
    combos = [(m, fv, dv) for m in (args.model or ["nimble"]) for fv in (args.fire or ["F0"])
              for dv in (args.duration or ["D0"])]
    only = args.only.split(",") if args.only else None
    for model, fv, dv in combos:
        name = model if len(combos) == len(args.model or ["nimble"]) else f"{model} {fv} {dv}"
        random.seed(args.seed)
        bench = Bench(model, fv, dv, only)
        bench.ask("warm-up", "Pick.", {"a": "a", "b": "b"})
        bench.latency.clear()
        t0 = time.time()
        results = bench.run(situations)
        report["models"][name] = {"summary": summary(results), "latency_ms_median": round(statistics.median(
            bench.latency)), "seconds": round(time.time() - t0), "results": results}
        s = report["models"][name]["summary"]
        print(f"{name}: " + " | ".join(f"{q} {v['right']}/{v['n']}" + (f" (within one step {v['within_one']})"
                                                                        if q == "duration" else "") +
                                        (f" (fired at {v['hits_fired']}/{v['hits']} hits, held {v['misses_held']}/"
                                         f"{v['misses']} misses)" if q == "fire" else "")
                                        for q, v in s.items())
              + f" | {report['models'][name]['latency_ms_median']} ms a question")
    Path(args.out).write_text(json.dumps(report, indent=1))
    print(f"report: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
