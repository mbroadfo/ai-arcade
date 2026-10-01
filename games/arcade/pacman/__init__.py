"""Pac-Man (Midway, MAME romset "pacman"). The adapter that general tools load via tools/gamelib.py.

What a game package provides:
  AGENT_REGIONS   RAM regions the Pi streams (start, end, refresh-every-N-frames)
  decode(image)   RAM image -> game state
  score_option    heuristic option score (drives the mock model and the rule decider)
  deciders        RuleDecider, SystemOneDecider
  knowledge       LEVELS and build_state_text(): the L0..L3b help rungs
  goals           GOALS, MISSIONS, GoalManager: what to try to achieve (survival.py can override)
  player          Player: the play loop (goal manager, deciders, survival reflex, per-game stats)
Layout: profile.json (ROM, controls), discovered.json (auto-found RAM), RAM_MAP.md, scripts/, tests/.
"""
from . import deciders, goals, knowledge, player  # noqa: F401
from .features import score_option  # noqa: F401
from .state import AGENT_REGIONS, REGIONS, decode  # noqa: F401
