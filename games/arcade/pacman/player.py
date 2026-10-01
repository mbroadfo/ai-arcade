"""Pac-Man player: reads the streamed state, asks a decider for a direction at each junction, steers.

Tiers (after Sean Goedecke's "tiered goals"): a slow strategy loop picks a goal from a fixed set;
a fast decider (rule, mock model, or a System One model) picks a direction at each junction given
that goal. Corridors and forced corners are followed by code, so the model is only asked real
questions. Because answers take 70-500 ms, a junction is queried a few tiles ahead and the
answer is applied when Pac-Man arrives; if it is late, a rule decides instead (and it is counted).

The stream, broker link and decision worker are passed in (they are general tools, see tools/play.py):
    python tools/play.py --game arcade/pacman --decider rule --games 3
"""
import json
import time

from .deciders import RuleDecider
from .features import GOALS, junction_facts, threat_distance
from .knowledge import build_state_text
from .maze import LOWER_TO_UPPER, Maze

LOOKAHEAD_STEPS = 8  # default: query a junction this many tiles ahead (~0.8 s of travel)


class RuleStrategy:
    """Slow-loop goal chooser. Replace with an LLM (e.g. Qwen) that returns one of GOALS."""

    def choose(self, state, image):
        if any(state.frightened[name] and not state.eyes[name] for name in state.ghosts):
            return "hunt_ghosts"
        threat = threat_distance(state, image)
        if threat is not None and threat <= 8:
            return "avoid_ghosts"
        return "clear_dots"


class Player:
    def __init__(self, stream, broker, worker, strategy, decisions_log, strategy_interval=2.0,
                 lookahead=LOOKAHEAD_STEPS, knowledge=None):
        self.lookahead = lookahead
        self.knowledge = knowledge  # rung L0..L3b, or None for the original compact fact text
        self.stream, self.broker, self.strategy = stream, broker, strategy
        self.worker = worker
        self.rule = RuleDecider()
        self.decisions_log = decisions_log
        self.strategy_interval = strategy_interval
        self.goal, self.goal_at = "clear_dots", 0.0
        self.plan = {}  # junction tile -> (Decision, goal, finished_at)
        self.applied = set()  # junctions already counted, so stats are per junction, not per tick
        self.last_frame, self.last_start_attempt = -1, 0.0
        self.was_playing, self.game_started, self.last_state = False, 0.0, None
        self.finished = 0
        self.stats = {"on_time": 0, "late_rule": 0, "queries": 0}
        self.latencies, self.sources = [], {}

    def log(self, **record):
        record["t"] = round(time.time(), 3)
        self.decisions_log.write(json.dumps(record) + "\n")

    def _facts(self, state, image, tile, arriving):
        facts = junction_facts(state, image, tile=tile, arriving=arriving)
        if self.knowledge:
            goal_text = f"GOAL: {self.goal} - {GOALS[self.goal]}"
            facts["state_text"] = build_state_text(self.knowledge, state, image, facts, tile, arriving, goal_text)
        return facts

    def _collect(self):
        got = self.worker.take()
        if not got:
            return
        tile, goal, facts, decision, finished_at = got
        self.plan[tile] = (decision, goal, finished_at)
        self.latencies.append(decision.latency_ms)
        self.sources[decision.source] = self.sources.get(decision.source, 0) + 1
        self.log(event="decision", tile=list(tile), goal=goal, direction=decision.direction,
                 source=decision.source, confidence=round(decision.confidence, 3),
                 latency_ms=round(decision.latency_ms), probabilities=decision.probabilities,
                 note=decision.note)

    def _pregame(self, state):
        """Attract/coin screens: put in a coin, press start. Returns True if it handled the frame."""
        if state.mode not in ("attract", "coin"):
            return False
        self.broker.steer(None)
        if time.time() - self.last_start_attempt > 4:
            self.last_start_attempt = time.time()
            self.broker.tap("COIN" if state.credits == 0 else "START")
        return True

    def tick(self):
        frame, state, image = self.stream.latest(newer_than=self.last_frame)
        self.last_frame = frame

        if state.mode in ("attract", "coin"):
            if self.was_playing:
                self.was_playing = False
                self.finished += 1
                last = self.last_state
                self.log(event="game_over", game=self.finished, score=last.score, level=last.level)
                return {"game": self.finished, "score": last.score, "level": last.level,
                        "dots": last.dots_eaten, "seconds": round(time.time() - self.game_started)}
            self._pregame(state)
            return None
        if state.mode != "playing":
            return None
        if not self.was_playing:
            self.game_started, self.plan = time.time(), {}
        self.was_playing, self.last_state = True, state

        if image[0x4E04 - 0x4000] != 3:  # READY screen, death animation, level transition
            self.broker.steer(None)
            self.plan = {}
            return None

        if time.time() - self.goal_at > self.strategy_interval:
            goal = self.strategy.choose(state, image)
            if goal != self.goal:
                self.log(event="goal", goal=goal)
            self.goal, self.goal_at = goal, time.time()

        self._collect()
        maze = Maze(image)
        me = state.pacman.tile
        heading = LOWER_TO_UPPER.get(state.pacman.direction)
        junction, steps, path = maze.walk_to_decision(me, heading)

        if junction is not None:
            self.plan = {t: p for t, p in self.plan.items() if t == junction}  # drop passed junctions
            self.applied &= {junction}
            if junction not in self.plan and steps <= self.lookahead:
                arriving = path[-1] if path else heading
                facts = self._facts(state, image, junction, arriving)
                if self.worker.submit(junction, self.goal, facts):
                    self.stats["queries"] += 1

        if junction is not None and steps <= 1 and junction in self.plan:
            decision = self.plan[junction][0]
            if junction not in self.applied:
                self.applied.add(junction)
                self.stats["on_time"] += 1
            self.broker.steer(decision.direction)
        elif junction is not None and steps == 0:
            # At the junction with no answer yet: a rule decides, and we count it as late.
            facts = junction_facts(state, image, tile=junction, arriving=heading)
            decision = self.rule.decide(facts, self.goal)
            self.plan[junction] = (decision, self.goal, time.time())
            self.applied.add(junction)
            self.stats["late_rule"] += 1
            self.log(event="late", tile=list(junction), direction=decision.direction)
            self.broker.steer(decision.direction)
        elif path:
            self.broker.steer(path[0])  # follow the corridor / forced corner
        return None
