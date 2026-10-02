"""Pac-Man (Midway, MAME romset "pacman"). The adapter that general tools load via tools/gamelib.py.

Pac-Man plays with the player shared by games on Pac-Man's board (arcadekit.kits.pacman_board), bound to Pac-Man's own
facts in spec.py: its name in the texts, the ghost knowledge, the corner targets, the tunnel and the refuge tile.

What a game package provides (games/README.md):
  AGENT_REGIONS   RAM regions the Pi streams (start, end, refresh-every-N-frames [, cpu, space])
  IMAGE           (base, size): the RAM window decode() reads
  decode(image)   RAM image -> game state
  score_option    heuristic option score (drives the mock model and the rule decider)
  deciders        RuleDecider, SystemOneDecider
  knowledge       LEVELS and build_state_text(): the L0..L3b help rungs
  goals           GOALS, MISSIONS, GoalManager: what to try to achieve (survival.py can override)
  strategy        SCHEMA, ModelGoalManager: a slow model layer picking the goal and stance (optional)
  player          Player: the play loop (goal manager, deciders, survival reflex, per-game stats)
  experiment      OPTIONS (the switches an experiment can set, with kinds), METRICS, player_kwargs, report_lines
Layout: spec.py, profile.json (ROM, controls), discovered.json (auto-found RAM), RAM_MAP.md, scripts/, tests/.
"""
from arcadekit.kits.pacman_board.bind import bind

from .spec import SPEC

_game = bind(SPEC)
AGENT_REGIONS, IMAGE, REGIONS, decode = _game.AGENT_REGIONS, _game.IMAGE, _game.REGIONS, _game.decode
score_option = _game.score_option
danger, deciders, events, experiment, features = _game.danger, _game.deciders, _game.events, _game.experiment, _game.features
ghosts, goals, knowledge, park, player = _game.ghosts, _game.goals, _game.knowledge, _game.park, _game.player
strategy, survival = _game.strategy, _game.survival
ORDERS_EXAMPLE = _game.ORDERS_EXAMPLE  # an order an operator might give, the Observatory's example
