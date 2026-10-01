"""Benchmark an Ollama /v1/systemone model on Pac-Man-sized decisions.

Measures cold-load time, steady latency (median / p95), input tokens per call and GPU memory,
then checks the answers: do the probabilities sum to ~1, and how often does the model agree with
the rule decider on real junction states from tests/fixtures/pacman_play_ram.bin and on hand-made
threat scenarios where the right answer is obvious?

    python tools/benchmark_systemone.py --model nimble --calls 40
"""
import argparse
import copy
import json
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import _bootstrap  # noqa: F401
from games.arcade.pacman.deciders import RuleDecider, describe_option
from games.arcade.pacman.features import GOALS, junction_facts, render_text
from games.arcade.pacman.state import decode
from systemone import DEFAULT_HOST

ROOT = Path(__file__).resolve().parent.parent


def vram_used_mib():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10).stdout
        return int(out.strip().splitlines()[0])
    except Exception:
        return None


def ask(host, model, facts, goal, extra_questions=False, timeout=60):
    questions = {"direction": {
        "type": "choice",
        "instructions": f"Pac-Man is at a junction. Goal: {goal} - {GOALS[goal]} "
                        "Which direction should Pac-Man take?",
        "criteria": {d: describe_option(o) for d, o in facts["options"].items()},
    }}
    if extra_questions:
        questions["in_danger"] = {"type": "noul", "instructions": "Is a normal ghost close enough to catch Pac-Man soon?"}
    body = json.dumps({"model": model, "state": render_text(facts, goal), "questions": questions,
                       "keep_alive": "30m"}).encode()
    request = urllib.request.Request(host + "/v1/systemone", data=body,
                                     headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read())
    return data, (time.time() - t0) * 1000


def scenarios(base):
    """Hand-made cases with an obvious best answer, built from the real junction facts."""
    cases = []
    facts = copy.deepcopy(base)
    for d, o in facts["options"].items():
        o.update(food_steps=2, threat_steps=None, edible_steps=None, room=15)
    if "UP" in facts["options"] and "DOWN" in facts["options"]:
        a = copy.deepcopy(facts)
        a["options"]["UP"].update(threat_steps=2, room=4)       # ghost two steps up, cramped
        a["options"]["DOWN"].update(food_steps=1)
        cases.append(("ghost close up, food down -> expect not UP", "clear_dots", a, lambda c: c != "UP"))
        b = copy.deepcopy(facts)
        b["options"]["UP"].update(food_steps=1)
        b["options"]["DOWN"].update(food_steps=9)
        cases.append(("food near up, far down -> expect UP", "clear_dots", b, lambda c: c == "UP"))
        c = copy.deepcopy(facts)
        c["options"]["DOWN"].update(edible_steps=2)
        cases.append(("blue ghost down while hunting -> expect DOWN", "hunt_ghosts", c, lambda c_: c_ == "DOWN"))
    return cases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="nimble")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--calls", type=int, default=40)
    args = parser.parse_args()

    image = (ROOT / "tests" / "fixtures" / "pacman_play_ram.bin").read_bytes()
    state = decode(image)
    facts = junction_facts(state, image)
    print(f"model {args.model} on {args.host}\nstate text ({len(render_text(facts, 'clear_dots'))} chars):\n"
          f"{render_text(facts, 'clear_dots')}\n")

    before = vram_used_mib()
    data, cold_ms = ask(args.host, args.model, facts, "clear_dots")
    after = vram_used_mib()
    print(f"cold first call: {cold_ms:.0f} ms; usage {data.get('usage')}")
    if before is not None and after is not None:
        print(f"GPU memory: {before} -> {after} MiB (+{after - before})")
    print("answer:", json.dumps(data["answers"]["direction"]))

    latencies = []
    for goal in list(GOALS) * (args.calls // len(GOALS) + 1):
        if len(latencies) >= args.calls:
            break
        _, ms = ask(args.host, args.model, facts, goal)
        latencies.append(ms)
    latencies.sort()
    print(f"\nsteady latency over {len(latencies)} calls (1 question): median {statistics.median(latencies):.0f} ms, "
          f"p95 {latencies[int(len(latencies) * 0.95) - 1]:.0f} ms, min {latencies[0]:.0f}, max {latencies[-1]:.0f}")
    two = [ask(args.host, args.model, facts, "clear_dots", extra_questions=True)[1] for _ in range(10)]
    print(f"with a second yes/no question: median {statistics.median(two):.0f} ms")

    rule = RuleDecider()
    print("\nobvious scenarios:")
    passed = 0
    for name, goal, case, check in scenarios(facts):
        data, _ = ask(args.host, args.model, case, goal)
        answer = data["answers"]["direction"]
        ok = check(answer["choice"])
        passed += ok
        probs = {k: round(v, 2) for k, v in answer["probabilities"].items()}
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: chose {answer['choice']} {probs} "
              f"(rule would choose {rule.decide(case, goal).direction})")
    print(f"  {passed}/{len(scenarios(facts))} passed")

    probs_total = sum(data["answers"]["direction"]["probabilities"].values())
    print(f"\nprobabilities sum to {probs_total:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
