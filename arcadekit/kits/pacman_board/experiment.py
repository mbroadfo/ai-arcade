"""What an experiment on Pac-Man can switch and what it measures (arcadekit.options; docs/GAME_WORKSHOP.md).

OPTIONS     the switches tools/play.py offers for this game, each with its kind; passed to Player as keywords
METRICS     the game's own result keys, printed per game in the run summary
player_kwargs(vals, new_worker)   turns option values into Player keywords (a model name into a worker)
report_lines(player, results)     extra summary lines only this game knows how to read
"""
from arcadekit.options import Option

OPTIONS = (
    Option("lookahead", "timing", "start asking about a junction this many tiles ahead (player default 8)",
           default=None, parse=int),
    Option("park", "skill", "ambush: wait against a wall near the energizer instead of pacing back and forth", tag="park"),
    Option("refuge", "skill", "hide at the game's safe spot when ghosts are close and he can get there first",
           tag="refuge"),
    Option("danger_query", "timing", "in a corridor with a ghost close, ask the model carry on or turn back (urgent) "
           "and execute its answer", tag="danger"),
    Option("danger_model", "timing", "a separate (fast) model for the danger query, e.g. tev1:0.8b; default: the "
           "decider's own", default=None, parse=str, model=True),
    Option("revise", "override", "code re-checks stored answers against fresh facts and replaces clearly worse ones",
           tag="revise"),
    Option("reflex", "override", "turn the survival instinct off", default=True, flag="--no-reflex", tag="noreflex"),
    Option("late", "override", "no answer on arrival at a junction: the rule decides (code-late), or keep: nothing "
           "changes and he waits for the model's answer (with --no-reflex, the model alone)",
           default="rule", parse=str, choices=("rule", "keep"), tag="late-{}"),
    Option("strategy_timing", "timing", "with a model setting the goal and stance (--strategist ollama): events = the "
           "goal on game events, and every 5 s the goal with one stance setting in turn when no junction question waits; always = goal "
           "and stance as often as answers come (the slow layer then keeps the model server busy)",
           default="events", parse=str, choices=("events", "always"), tag="strat-{}"),
    Option("ask_order", "timing", "the model's queue: nearest = the junction he is heading to first, chained "
           "junctions only in spare time, questions off his way withdrawn; fifo = in the order they come up",
           default="nearest", parse=str, choices=("nearest", "fifo"), tag="order-{}"),
    Option("turn_guess", "timing", "in spare time, also ask about the junction behind him (ready if he turns "
           "around); measured 2 October 2026 without a gain, so off by default", tag="turnguess"),
    Option("chain_depth", "timing", "look-ahead chain depth, 0 = off (player default 2)", default=None, flag="--chain",
           parse=int, tag="chain{}"),
)

METRICS = (
    ("dots_total", "dots eaten over the game"),
    ("ghosts_eaten", "ghosts eaten"),
    ("fruit_eaten", "bonus fruit eaten"),
    ("fruit_shown", "bonus fruit shown"),
    ("energizers", "energizers eaten"),
    ("reflexes", "survival reflex firings"),
    ("parks", "parks (waits near an energizer)"),
    ("parked_seconds", "seconds parked"),
    ("park_deaths", "lives lost while parked"),
    ("refuges", "refuge entries"),
    ("refuge_seconds", "seconds in the refuge"),
    ("refuge_deaths", "lives lost in or on the way to the refuge"),
)


def player_kwargs(vals, new_worker):
    """Player keywords from option values. new_worker(model): a worker answering with that model (from tools/play.py).
    Options left at None use the player's own default."""
    kwargs = {k: v for k, v in vals.items() if v is not None and k != "danger_model"}
    if vals.get("danger_query") and vals.get("danger_model"):
        kwargs["danger_worker"] = new_worker(vals["danger_model"])
    return kwargs


def report_lines(player, results):
    lines = []
    if player.danger_query:
        lines.append(f"danger queries: {player.stats.get('danger')}")
    if results and "feasts" in results[0]:
        sizes = [n for r in results for n in r["feasts"]]
        lines.append("ghosts eaten per energizer: " + "  ".join(f"{k}x: {sizes.count(k)}" for k in range(5))
                     + f"   (of {len(sizes)} energizers)")
    return lines
