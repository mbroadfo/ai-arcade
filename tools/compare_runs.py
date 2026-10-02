"""Compare play.py runs side by side, from their manifests, game results and decisions logs. Any game.

    python tools/compare_runs.py v13 v15-L2 v17          # runs whose label contains any of these
    python tools/compare_runs.py --all                   # every run with a manifest

One row per run: model, rung, switches that are not at their default, games, mean score and range, the model's own
share of executed moves (arcadekit.ledger; older labels are mapped), late decisions and why, median model latency,
and emulated frames per second when the manifest has it.
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

from gamelib import ROOT  # first: puts the repository root on sys.path

from arcadekit.ledger import OLD_LABELS


def load(manifest_path):
    m = json.loads(manifest_path.read_text())
    stem = str(manifest_path)[: -len("-manifest.json")]
    games_path, log_path = Path(stem + "-games.jsonl"), Path(stem + "-decisions.jsonl")
    results = [json.loads(line) for line in games_path.read_text().splitlines()] if games_path.exists() else []
    moves, late, latencies = {}, {}, []
    if log_path.exists():
        for line in log_path.read_text().splitlines():
            e = json.loads(line)
            if e["event"] == "move":
                by, via = (e["by"], e["via"]) if "via" in e else OLD_LABELS.get(e["by"], (e["by"], "?"))
                moves[by] = moves.get(by, 0) + 1
            elif e["event"] == "late":
                late[e["why"]] = late.get(e["why"], 0) + 1
            elif e["event"] == "decision" and e.get("source") == "model":
                latencies.append(e["latency_ms"])
    return m, results, moves, late, latencies


def switches_on(m):
    """The switches not at their usual setting, from either manifest format."""
    out = []
    for name, v in (m.get("switches") or {}).items():
        value = v["value"] if isinstance(v, dict) else v  # since phase 2: {"value", "kind"}
        if name in ("reflex", "no_reflex"):  # on by default: shown only when off
            if value is (name == "no_reflex"):
                out.append("noreflex")
        elif name == "late":
            if value not in (None, "rule"):
                out.append(f"late-{value}")
        elif isinstance(value, bool):  # (checked before numbers: True == 1 in Python)
            if value:
                out.append(name)
        elif value is not None and name != "min_confidence":
            out.append(f"{name}={value}")
    if m.get("strategist") not in (None, "code"):
        out.append(f"strategist={m['strategist']}")
    return out


def row(manifest_path):
    m, results, moves, late, latencies = load(manifest_path)
    scores = [r["score"] for r in results if not r.get("partial")]
    total = sum(moves.values())
    model = (m.get("models", {}).get("decider") or {}).get("model") or m.get("decider")
    return {
        "run": m.get("tag") or m["label"],
        "decider": model,
        "rung": m.get("knowledge") or "-",
        "switches": ",".join(switches_on(m)) or "-",
        "games": len(scores),
        "mean": round(statistics.mean(scores)) if scores else "-",
        "range": f"{min(scores)}-{max(scores)}" if scores else "-",
        "model's own": f"{100 * moves.get('model', 0) / total:.0f}%" if total else "-",
        "late": sum(late.values()),
        "late why": ",".join(f"{k} {v}" for k, v in sorted(late.items(), key=lambda kv: -kv[1])) or "-",
        "latency ms": round(statistics.median(latencies)) if latencies else "-",
        "fps": m.get("emulated_fps", "-"),
    }


def table(rows):
    cols = list(rows[0])
    widths = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
    lines = [" | ".join(c.ljust(widths[c]) for c in cols), "-|-".join("-" * widths[c] for c in cols)]
    lines += [" | ".join(str(r[c]).ljust(widths[c]) for c in cols) for r in rows]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("match", nargs="*", help="runs whose label contains any of these")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--runs", default=str(ROOT / "runs"))
    args = parser.parse_args(argv)
    manifests = sorted(Path(args.runs).glob("*-manifest.json"))
    if not args.all:
        manifests = [p for p in manifests if any(s in p.name for s in args.match)]
    if not manifests:
        print("no matching runs")
        return 1
    print(table([row(p) for p in manifests]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
