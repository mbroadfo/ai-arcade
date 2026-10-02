"""Ms. Pac-Man (Midway, MAME romset "mspacman").

It runs Pac-Man's program with its own additions on an auxiliary board, so it uses the player, decoder and maze reader
shared by games on Pac-Man's board (arcadekit.kits.pacman_board), bound to Ms. Pac-Man's own facts in spec.py: her name
in the texts, the ghost knowledge, the tunnels. There is no refuge spot, so --refuge is not offered. README.md says what
is checked and what comes next.
"""
from arcadekit.kits.pacman_board.bind import bind

from .spec import SPEC

_game = bind(SPEC)
AGENT_REGIONS, IMAGE, REGIONS, decode = _game.AGENT_REGIONS, _game.IMAGE, _game.REGIONS, _game.decode
score_option = _game.score_option
danger, deciders, events, experiment, features = _game.danger, _game.deciders, _game.events, _game.experiment, _game.features
ghosts, goals, knowledge, park, player = _game.ghosts, _game.goals, _game.knowledge, _game.park, _game.player
strategy, survival = _game.strategy, _game.survival
