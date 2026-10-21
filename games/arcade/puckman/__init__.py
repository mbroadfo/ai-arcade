"""Puck Man (bootleg set 1) (MAME set "puckmanb"), put on the AI by tools/new_game.py from arcade/pacman: the same hardware
(pacman/pacman.cpp), so it plays with the same kit, bound to its own spec.py."""
from arcadekit.kits.pacman_board.bind import bind

from .spec import SPEC

_game = bind(SPEC)
AGENT_REGIONS, IMAGE, REGIONS, decode = _game.AGENT_REGIONS, _game.IMAGE, _game.REGIONS, _game.decode
score_option = _game.score_option
danger, deciders, events, experiment, features = _game.danger, _game.deciders, _game.events, _game.experiment, _game.features
ghosts, goals, knowledge, park, player = _game.ghosts, _game.goals, _game.knowledge, _game.park, _game.player
strategy, survival = _game.strategy, _game.survival
ORDERS_EXAMPLE = _game.ORDERS_EXAMPLE  # an order an operator might give, the Observatory's example
