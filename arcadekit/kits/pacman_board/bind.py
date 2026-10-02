"""Bind the shared modules to one game's spec: what a game package hands tools/play.py and its own tests.

    game = bind(SPEC)          # in games/<system>/<name>/__init__.py
    game.player.Player(...)    # the shared player, with the game's spec filled in
    game.deciders.SystemOneDecider(client)

Each bound module is a namespace with everything the shared module has, plus the functions that need the game's facts
with the spec filled in. Modules that need no spec are handed over as they are.
"""
from functools import partial
from types import SimpleNamespace

from . import (danger, deciders, events, experiment, features, ghosts, goals, knowledge, park, player, state, strategy,
               survival)


def _module(mod, **overrides):
    names = {k: v for k, v in vars(mod).items() if not k.startswith("__")}
    names.update(overrides)
    return SimpleNamespace(**names)


def bind(spec):
    class Player(player.Player):
        __doc__ = player.Player.__doc__

        def __init__(self, *args, **kwargs):
            kwargs.setdefault("spec", spec)
            super().__init__(*args, **kwargs)

    options = tuple(o for o in experiment.OPTIONS if o.name != "refuge" or spec.safe_spot is not None)
    return SimpleNamespace(
        spec=spec,
        AGENT_REGIONS=state.AGENT_REGIONS, IMAGE=state.IMAGE, REGIONS=state.REGIONS, decode=state.decode,
        score_option=features.score_option,
        player=_module(player, Player=Player),
        deciders=_module(deciders, SystemOneDecider=partial(deciders.SystemOneDecider, spec=spec),
                         question=partial(deciders.question, spec=spec)),
        knowledge=_module(knowledge, build_state_text=partial(knowledge.build_state_text, spec=spec),
                          render_l0=partial(knowledge.render_l0, spec=spec),
                          render_l2=partial(knowledge.render_l2, spec=spec),
                          render_l3b=partial(knowledge.render_l3b, spec=spec),
                          show=partial(knowledge.show, spec=spec)),
        ghosts=_module(ghosts, targets=partial(ghosts.targets, spec=spec),
                       choose_exit=partial(ghosts.choose_exit, spec=spec),
                       forecast=partial(ghosts.forecast, spec=spec)),
        strategy=_module(strategy, SCHEMA=strategy.schema(spec.name),
                         ModelGoalManager=partial(strategy.ModelGoalManager, name=spec.name),
                         describe=partial(strategy.describe, name=spec.name)),
        experiment=_module(experiment, OPTIONS=options),
        danger=danger, events=events, features=features, goals=goals, park=park, survival=survival,
    )
