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
from .events import GameStats
from .features import GOALS, junction_facts, score_option
from .knowledge import build_state_text
from .maze import LOWER_TO_UPPER, OPPOSITE, Maze, step
from .survival import reflex

THREAT_NEAR = 10  # only run the survival check when a normal ghost is this close (tiles, straight line)
LOOKAHEAD_STEPS = 8  # default: query a junction this many tiles ahead (~0.8 s of travel)
CHAIN_DEPTH = 2  # when an answer arrives, also ask about the junction it leads to, this many junctions deep
CHAIN_DEPTH_PAUSE = 4  # ... deeper while the game is frozen after a ghost is eaten (nothing moves for ~1.2 s)
CHAIN_MAX_STEPS = 14  # do not chain to a junction further than this
PLAN_TTL = 4.0  # seconds before a stored answer is considered stale
REVISE_REGRET = 2.5  # with revise on, a stored answer is replaced if another exit scores this much better
GHOST_SCORES = (200, 400, 800, 1600)
PAUSE_FRAMES = 60  # the game freezes for about this many frames when a ghost is eaten


class Player:
    def __init__(self, stream, broker, worker, strategy, decisions_log, strategy_interval=0.5,
                 lookahead=LOOKAHEAD_STEPS, knowledge=None, revise=False, reflex=True,
                 chain_depth=CHAIN_DEPTH):
        # Ablation switches. revise: code re-checks each stored answer against fresh facts (code overruling the
        # decider, so off by default). reflex: the survival instinct. chain_depth: look-ahead chain, 0 = off.
        self.revise, self.reflex, self.chain_depth = revise, reflex, chain_depth
        self.lookahead = lookahead
        self.knowledge = knowledge  # rung L0..L3b, or None for the original compact fact text
        self.stream, self.broker, self.strategy = stream, broker, strategy
        self.worker = worker
        self.rule = RuleDecider()
        self.decisions_log = decisions_log
        self.strategy_interval = strategy_interval
        self.goal, self.goal_at = "clear_dots", 0.0
        self.plan = {}  # (junction tile, arriving direction) -> (Decision, goal, finished_at)
        self.depth = {}  # plan key -> how many answers deep the chain was when it was asked
        self.pause_until, self.prev_score = -1, None
        self.revised_keys = set()  # situations already counted as revised
        self.consumed = set()  # plan keys already applied: single-use, retired once Pac-Man has moved on
        self.applied = set()  # junctions already counted, so stats are per junction, not per tick
        self.last_frame, self.last_start_attempt = -1, 0.0
        self.was_playing, self.game_started, self.last_state = False, 0.0, None
        self.finished = 0
        self.game = GameStats()  # what happened in the current game
        self.last_reflex = (None, 0.0)
        self.stats = {"on_time": 0, "late_rule": 0, "queries": 0, "chained": 0, "revised": 0,
                      "late_why": {}}
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

    def _near_threat(self, state):
        me = state.pacman.tile
        return any(not state.frightened[n] and not state.eyes[n]
                   and abs(g.tile[0] - me[0]) + abs(g.tile[1] - me[1]) <= THREAT_NEAR
                   for n, g in state.ghosts.items())

    def _revise(self, facts, chosen):
        """A stored answer was made some tiles ago; the world has moved. Keep it unless it is now clearly worse."""
        options = facts["options"]
        if chosen not in options:
            return None
        best = max(options, key=lambda d: score_option(self.goal, options[d]))
        regret = score_option(self.goal, options[best]) - score_option(self.goal, options[chosen])
        return best if best != chosen and regret > REVISE_REGRET else None

    def _survive(self, state, image, tile, arriving, chosen, where, facts=None):
        """The survival instinct: veto `chosen` if it runs into a ghost and a clearly safer way exists."""
        if not self.reflex or not self._near_threat(state):
            return chosen
        facts = facts or junction_facts(state, image, tile=tile, arriving=arriving)
        better = reflex(facts, chosen)
        if better is None:
            return chosen
        key, at = self.last_reflex
        if key != (chosen, better) or time.time() - at > 1.0:  # count an emergency once, not per tick
            self.game.reflexes += 1
            self.log(event="reflex", where=where, tile=list(tile), chosen=chosen, override=better,
                     threat=facts["options"][chosen]["threat_steps"])
        self.last_reflex = ((chosen, better), time.time())
        return better

    def _go(self, state, image, tile, arriving, chosen, where, source):
        """Steer to `chosen` unless survival vetoes it. A turn-back is logged with why and what was around."""
        facts = None
        if self.revise and source not in ("late-rule", "corridor"):  # check a stored answer against the world now
            facts = junction_facts(state, image, tile=tile, arriving=arriving)
            better = self._revise(facts, chosen)
            if better:
                if (tile, arriving) not in self.revised_keys:  # count a situation once, not once per control tick
                    self.revised_keys.add((tile, arriving))
                    self.stats["revised"] += 1
                    self.log(event="revise", tile=list(tile), was=chosen, now=better, goal=self.goal, source=source)
                chosen, source = better, "revised"
        final = self._survive(state, image, tile, arriving, chosen, where, facts)
        heading = LOWER_TO_UPPER.get(state.pacman.direction)
        if final == OPPOSITE.get(heading) and self.broker.held != final:
            here = Maze(image).bfs(tuple(state.pacman.tile))
            blue = sorted(here[g.tile] for n, g in state.ghosts.items()
                          if state.frightened[n] and not state.eyes[n] and g.tile in here)
            normal = sorted(here[g.tile] for n, g in state.ghosts.items()
                            if not state.frightened[n] and not state.eyes[n] and g.tile in here)
            self.log(event="reverse", why="reflex" if final != chosen else source, where=where, goal=self.goal,
                     heading=heading, to=final, blue_steps=blue, normal_steps=normal,
                     fruit=bool(state.fruit_tile))
        self.broker.steer(final)

    def _watch_for_pause(self, state, frame):
        """A ghost-sized score jump means a ghost was just eaten: the game freezes for about a second."""
        jump = None if self.prev_score is None else state.score - self.prev_score
        if jump in GHOST_SCORES + tuple(x + 10 for x in GHOST_SCORES):  # +10: a dot eaten in the same step
            self.pause_until = frame + PAUSE_FRAMES
            self.log(event="pause", frame=frame, score=jump)
        self.prev_score = state.score

    def _late_reason(self, key, asked_now=False):
        """Why there was no stored answer on arrival. asked_now: this very tick was the first chance to ask, i.e.
        the junction only came into view 0-1 tiles ahead (too close together to ask in time)."""
        if asked_now:
            return "seen_too_late"
        if self.worker.pending(key):
            return "in_flight"
        if any(k[0] == key[0] for k in self.plan):
            return "other_arrival"
        return "not_asked"

    def _collect(self, state, image, frame):
        """Store finished answers and, for each, ask about the junction it leads to (the chain)."""
        paused = frame < self.pause_until
        limit = 0 if self.chain_depth == 0 else (self.chain_depth + 2 if paused else self.chain_depth)
        for key, goal, facts, decision, finished_at in self.worker.take_all():
            self.plan[key] = (decision, goal, finished_at)
            self.latencies.append(decision.latency_ms)
            self.sources[decision.source] = self.sources.get(decision.source, 0) + 1
            depth = self.depth.get(key, 0)
            self.log(event="decision", tile=list(key[0]), arriving=key[1], goal=goal,
                     direction=decision.direction, source=decision.source,
                     confidence=round(decision.confidence, 3), latency_ms=round(decision.latency_ms),
                     probabilities=decision.probabilities, note=decision.note, chain=depth)
            if depth >= limit:
                continue
            nxt = step(key[0], decision.direction)
            junction, steps, path = Maze(image).walk_to_decision(nxt, decision.direction)
            if junction is None or steps > CHAIN_MAX_STEPS:
                continue
            key2 = (junction, path[-1] if path else decision.direction)
            if key2 not in self.plan and not self.worker.pending(key2):
                if self.worker.submit(key2, self.goal, self._facts(state, image, junction, key2[1])):
                    self.depth[key2] = depth + 1
                    self.stats["queries"] += 1
                    self.stats["chained"] += 1

    def _pregame(self, state):
        """Attract/coin screens: put in a coin, press start. Returns True if it handled the frame."""
        if state.mode not in ("attract", "coin"):
            return False
        self.broker.steer(None)
        if time.time() - self.last_start_attempt > 4:
            self.last_start_attempt = time.time()
            self.broker.tap("COIN" if state.credits == 0 else "START")
        return True

    def partial_result(self):
        """The game in progress as a result record (for when a run is stopped mid-game), or None."""
        last = self.last_state
        if not self.was_playing or last is None:
            return None
        return {"game": self.finished + 1, "score": last.score, "level": last.level, "dots": last.dots_eaten,
                "seconds": round(time.time() - self.game_started), "partial": True,
                "goal": getattr(self.strategy, "mission", None), **self.game.summary()}

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
                        "dots": last.dots_eaten, "seconds": round(time.time() - self.game_started),
                        "goal": getattr(self.strategy, "mission", None), **self.game.summary()}
            self._pregame(state)
            return None
        if state.mode != "playing":
            return None
        if not self.was_playing:
            self.game_started, self.plan, self.game = time.time(), {}, GameStats()
            self.worker.clear_queued()
        self.was_playing, self.last_state = True, state
        self.game.update(state, image, self.goal, time.time())

        if image[0x4E04 - 0x4000] != 3:  # READY screen, death animation, level transition
            self.broker.steer(None)
            self.plan = {}
            return None

        if time.time() - self.goal_at > self.strategy_interval:
            goal = self.strategy.choose(state, image, frame)
            if goal != self.goal:
                self.log(event="goal", goal=goal)
            self.goal, self.goal_at = goal, time.time()

        self._watch_for_pause(state, frame)
        self._collect(state, image, frame)
        now = time.time()
        self.plan = {k: p for k, p in self.plan.items() if now - p[2] < PLAN_TTL}  # drop stale answers
        maze = Maze(image)
        me = state.pacman.tile
        heading = LOWER_TO_UPPER.get(state.pacman.direction)
        junction, steps, path = maze.walk_to_decision(me, heading)
        arriving = path[-1] if path and junction is not None else heading
        key = (junction, arriving)
        for done in [k for k in self.consumed if k != key]:  # an answer is used once, at its junction
            self.plan.pop(done, None)
            self.consumed.discard(done)
            self.revised_keys.discard(done)

        asked_now = False
        if junction is not None:
            self.applied = {k for k in self.applied if k == key}
            if key not in self.plan and steps <= self.lookahead:
                facts = self._facts(state, image, junction, arriving)
                if self.worker.submit(key, self.goal, facts):
                    self.depth[key] = 0
                    self.stats["queries"] += 1
                    asked_now = True

        if junction is not None and steps <= 1 and key in self.plan:
            decision = self.plan[key][0]
            self.consumed.add(key)
            if key not in self.applied:
                self.applied.add(key)
                self.stats["on_time"] += 1
            self._go(state, image, junction, arriving, decision.direction, "junction", decision.source)
        elif junction is not None and steps == 0:
            # At the junction with no answer yet: a rule decides, and we count it as late.
            facts = junction_facts(state, image, tile=junction, arriving=heading)
            decision = self.rule.decide(facts, self.goal)
            self.plan[key] = (decision, self.goal, time.time())
            self.applied.add(key)
            self.consumed.add(key)
            self.stats["late_rule"] += 1
            why = self._late_reason(key, asked_now)
            self.stats["late_why"][why] = self.stats["late_why"].get(why, 0) + 1
            self.log(event="late", tile=list(junction), direction=decision.direction, why=why, steps_seen=steps)
            self._go(state, image, junction, heading, decision.direction, "junction", "late-rule")
        elif path:
            self._go(state, image, me, heading, path[0], "corridor", "corridor")  # corridor / forced corner
        return None
