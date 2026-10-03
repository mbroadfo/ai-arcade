"""What an AI run of a game can be set to, read from the game package, for the Observatory's AI setup panel.

The panel is built from the package (games/README.md): its knowledge levels, goals, slow layer and its own switches
(experiment.OPTIONS, each with a kind), so no game's names live here. The answers come back as the command line of
tools/play.py, which checks them again.

    schema("<system>/<name>")                 -> the fields and switches, with help text and defaults
    command_line("<system>/<name>", answers)  -> ["--game", "<system>/<name>", "--decider", "ollama", ...]
"""
import json

from gamelib import ROOT, load_game, load_profile

GAMES_DIR = ROOT / "games"
KIND_HELP = {
    "facts": "Changes what the model is told.",
    "timing": "Changes when or how often the model is asked. Never chooses a move.",
    "override": "Code changes or replaces a move the model proposed. Its moves are booked to code.",
    "skill": "Code steers several moves on its own. Its moves are booked to code.",
}
DECIDERS = [
    {"value": "ollama", "label": "A model", "help": "A System One model on this PC's Ollama chooses at each decision point."},
    {"value": "rule", "label": "The rule (control)", "help": "Code decides every move: the baseline to compare models with."},
    {"value": "mock", "label": "Mock model", "help": "Code's choice delivered after a model-like delay: tests timing, not judgement."},
]
STRATEGISTS = [
    {"value": "code", "label": "Code", "help": "The game's own code picks the goal and stance."},
    {"value": "ollama", "label": "A model", "help": "A model picks the goal and stance every second or so."},
    {"value": "mock", "label": "Mock model", "help": "Code's choice after a delay (timing test)."},
]


def ai_games():
    """{"<system>/<name>": {"romset", "title", "kind"}} for every game package with an AI player ("model") or, while
    no model plays it yet, a real-time lab of code policies ("lab"). A game with neither (a profile and a RAM map only)
    is left out: it can be played by a human only."""
    out = {}
    for profile in sorted(GAMES_DIR.glob("*/*/profile.json")):
        system, name = profile.parent.parent.name, profile.parent.name
        kind = lab_or_model(load_game(f"{system}/{name}"))
        if kind is None:
            continue
        data = json.loads(profile.read_text())
        out[f"{system}/{name}"] = {"romset": data.get("romset", name), "title": data.get("description", name),
                                   "kind": kind,  # the cabinet's file for it, when its name is not the ROM set's
                                   "file": data.get("cabinet_file", data.get("romset", name))}
    return out


def lab_or_model(game):
    if getattr(game, "player", None) is not None:
        return "model"
    if hasattr(game, "lab_main") and hasattr(game, "LAB"):
        return "lab"
    return None


def lab_schema(spec, game):
    lab = game.LAB
    lo, hi = lab["hz_range"]
    return {
        "game": spec, "kind": "lab", "title": load_profile(spec).get("description", spec),
        "run_types": [
            {"value": "manual", "label": "Manual", "help": "A person plays on the cabinet."},
            {"value": "lab", "label": "Lab policy", "help": "Code plays: a fixed policy on a fixed-rate clock, every "
                                                         "tick logged. Never reported as AI play."},
            {"value": "ai", "label": "AI player", "help": lab.get("ai_help", "Not available yet: no model plays this "
                                                                  "game."), "disabled": not lab.get("ai_player")}],
        "policies": list(game.lab_policies()),
        "groups": list(getattr(game, "LAB_GROUPS", ())) or None,  # in this order (the baselines first)
        "default_policy": lab["default_policy"],
        "measures": list(getattr(game, "LAB_MEASURES", [])),
        "ai_modes": list(lab.get("ai_modes", [])),
        "hz": {"default": lab["default_hz"], "min": lo, "max": hi,
               "help": "How often the policy reads the game and sets the controls."},
        "seconds": {"default": 300, "min": 10, "max": 3600, "help": "The run also ends when the game ends."},
        "speed": {"default": 1.0, "min": 0.3, "max": 1.0, "help": "How fast the game runs. Timing work runs at 100 %."},
    }


def _option_field(o):
    field = {"name": o.name, "kind": o.kind, "help": o.help, "flag": o.cli, "default": o.default}
    if isinstance(o.default, bool):
        field["type"] = "switch"
    elif o.choices:
        field["type"], field["choices"] = "choice", list(o.choices)
    elif o.model:
        field["type"] = "model"
    elif o.parse in (int, float):
        field["type"] = "number"
    else:
        field["type"] = "text"
    return field


def schema(spec):
    game = load_game(spec)
    if lab_or_model(game) == "lab":
        return lab_schema(spec, game)
    levels = list(getattr(game.knowledge, "LEVELS", ()))
    level_help = getattr(game.knowledge, "LEVEL_HELP", {})
    goals = getattr(game.goals, "GOALS", {})
    missions = list(getattr(game.goals, "MISSIONS", ("auto",)))
    experiment = getattr(game, "experiment", None)
    return {
        "game": spec,
        "title": load_profile(spec).get("description", spec),
        "deciders": DECIDERS,
        "knowledge": [{"value": None, "label": "Compact facts", "help": "the original short fact text"}]
                     + [{"value": lv, "label": lv, "help": level_help.get(lv, "")} for lv in levels],
        "default_knowledge": "L2" if "L2" in levels else (levels[-1] if levels else None),
        "goals": [{"value": m, "label": m.replace("_", " "), "help": goals.get(m, "chosen as the game goes")}
                  for m in missions],
        "strategists": STRATEGISTS if hasattr(game, "strategy") else STRATEGISTS[:1],
        "orders_example": getattr(game, "ORDERS_EXAMPLE", ""),
        "switches": [_option_field(o) for o in (experiment.OPTIONS if experiment else ())],
        "kinds": KIND_HELP,
        "speed": {"default": 0.85, "min": 0.3, "max": 1.0,
                  "help": "How fast the game runs. Slower gives the model more time per decision; 85 % is the Pi 3's "
                          "pace, which the answer times were tuned on. Changeable during the run."},
    }


def command_line(spec, answers):
    """play.py's arguments for these answers (run_lab.py's, for a lab). Raises ValueError on anything not offered."""
    s = schema(spec)
    args = ["--game", spec]
    if s.get("kind") == "lab":
        ai = answers.get("runtype") == "ai"
        if ai and s["run_types"][2].get("disabled"):
            raise ValueError("no AI player for this game")
        modes = {m["value"]: m for m in s.get("ai_modes", [])}
        mode = answers.get("ai_mode") or next(iter(modes), None)
        if ai and mode not in modes:
            raise ValueError(f"ai_mode: {mode!r} is not offered")
        policy = modes[mode]["policy"] if ai else answers.get("policy", s["default_policy"])
        if not ai and policy not in [p["value"] for p in s["policies"]]:
            raise ValueError(f"policy: {policy!r} is not offered")
        hz, seconds = float(answers.get("hz", s["hz"]["default"])), int(answers.get("seconds", s["seconds"]["default"]))
        if not s["hz"]["min"] <= hz <= s["hz"]["max"]:
            raise ValueError(f"hz: {s['hz']['min']} to {s['hz']['max']}")
        if not s["seconds"]["min"] <= seconds <= s["seconds"]["max"]:
            raise ValueError(f"seconds: {s['seconds']['min']} to {s['seconds']['max']}")
        return (args + ["--policy", policy, "--hz", f"{hz:g}", "--seconds", str(seconds)]
                + (["--model", str(answers.get("model") or modes[mode].get("model", "nimble"))] if ai else []))

    def pick(name, options, default):
        value = answers.get(name, default)
        if value not in [o["value"] for o in options]:
            raise ValueError(f"{name}: {value!r} is not offered")
        return value

    decider = pick("decider", s["deciders"], "ollama")
    args += ["--decider", decider]
    if decider == "ollama":
        args += ["--model", str(answers.get("model") or "nimble")]
    knowledge = pick("knowledge", s["knowledge"], s["default_knowledge"])
    if knowledge:
        args += ["--knowledge", knowledge]
    goal = pick("goal", s["goals"], "auto")
    args += ["--goal", goal]
    strategist = pick("strategist", s["strategists"], "code")
    if strategist != "code":
        if goal != "auto":
            raise ValueError("a slow layer needs the goal on auto")
        args += ["--strategist", strategist]
        if strategist == "ollama":
            args += ["--strategist-model", str(answers.get("strategist_model") or "nimble")]
    games = int(answers.get("games", 3))
    if not 1 <= games <= 100:
        raise ValueError("games: 1 to 100")
    args += ["--games", str(games)]
    for order in answers.get("orders") or []:
        if not isinstance(order, str):
            raise ValueError("orders: text only")
        if order.strip():
            args.append(f"--orders={order.strip()}")  # = form: an order may start with a dash
    chosen = answers.get("switches") or {}
    for field in s["switches"]:
        if field["name"] not in chosen:
            continue
        value = chosen[field["name"]]
        if field["type"] == "switch":
            if bool(value) != field["default"]:
                args.append(field["flag"])
        elif value not in (None, "", field["default"]):
            if field["type"] == "choice" and value not in field["choices"]:
                raise ValueError(f"{field['name']}: {value!r} is not offered")
            args.append(f"{field['flag']}={value}")
    return args
