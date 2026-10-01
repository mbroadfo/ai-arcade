"""What exactly was run: written beside every play.py run, so a result can always be traced to its code and settings.

The manifest says which commit (and whether the working tree had uncommitted changes), which game, which decider and
model (with the model's digest when an Ollama server answers), which knowledge rung, goal and strategist, every switch
that lets code help or overrule the decider, the seed, and how many games were asked for.
"""
import json
import platform
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# switches that let code help or overrule the decider: a result must say which were on
SWITCHES = ("revise", "no_reflex", "chain", "lookahead", "park", "refuge", "danger_query", "danger_model", "min_confidence")


def _git(*args):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def model_digest(host, model, timeout=3.0):
    """The Ollama digest of `model` (so a result names the exact weights), or None if the server does not answer."""
    try:
        with urllib.request.urlopen(host.rstrip("/") + "/api/tags", timeout=timeout) as response:
            for entry in json.loads(response.read()).get("models", []):
                if entry.get("name") in (model, model + ":latest"):
                    return entry.get("digest")
    except (OSError, ValueError):
        pass
    return None


def build_manifest(args, label):
    """args: the argparse namespace of tools/play.py."""
    options = vars(args)
    uses_ollama = options.get("decider") == "ollama" or options.get("strategist") == "ollama"
    models = {}
    if options.get("decider") == "ollama":
        models["decider"] = {"model": options["model"], "digest": model_digest(options["ollama_host"], options["model"])}
    if options.get("strategist") == "ollama":
        name = options["strategist_model"]
        models["strategist"] = {"model": name, "digest": model_digest(options["ollama_host"], name)}
    status = _git("status", "--porcelain")
    return {
        "label": label,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "git": {"sha": _git("rev-parse", "HEAD"), "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
                "dirty": bool(status) if status is not None else None},
        "game": options.get("game"),
        "pi": options.get("host"),
        "decider": options.get("decider"),
        "strategist": options.get("strategist"),
        "knowledge": options.get("knowledge"),
        "goal": options.get("goal"),
        "switches": {name: options.get(name) for name in SWITCHES},
        "seed": options.get("seed"),
        "games_requested": options.get("games"),
        "seconds_cap": options.get("seconds"),
        "tag": options.get("tag"),
        "models": models,
        "ollama_host": options.get("ollama_host") if uses_ollama else None,
        "python": platform.python_version(),
        "args": {k: v for k, v in options.items()},
    }
