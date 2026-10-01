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
from .features import GOALS, LURE_RADIUS, junction_facts, ready_to_eat, score_option
from .goals import stance_text
from .knowledge import build_state_text
from .maze import LOWER_TO_UPPER, OPPOSITE, Maze, step
from .park import (HOVER_MAX, HOVER_MIN, HOVER_SECONDS, REFUGE_CLEAR, REFUGE_SECONDS, SAFE_SPOT, all_out, gathered,
                   is_stop, nearest_energizer, nearest_normal, refuge_move)
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
                 chain_depth=CHAIN_DEPTH, park=False, refuge=False):
        # Ablation switches. revise: code re-checks each stored answer against fresh facts (code overruling the
        # decider, so off by default). reflex: the survival instinct. chain_depth: look-ahead chain, 0 = off.
        self.revise, self.reflex, self.chain_depth = revise, reflex, chain_depth
        # park: ambush waits against a wall near the energizer instead of pacing. refuge: hide at the safe spot when a
        # ghost is close and he can get there first. Both off by default (park.py); neither lets the reflex steer while held.
        self.park, self.refuge = park, refuge
        self.hold = None  # {"kind": "park"|"refuge", "tile", "push", "since", "noted", "exit", "booked"} while parked
        self.refuge_ran_at, self.refuge_cooldown = 0.0, 0.0
        self.lookahead = lookahead
        self.knowledge = knowledge  # rung L0..L3b, or None for the original compact fact text
        self.stream, self.broker, self.strategy = stream, broker, strategy
        self.worker = worker
        self.rule = RuleDecider()
        self.decisions_log = decisions_log
        self.strategy_interval = strategy_interval
        self.goal, self.goal_at = "clear_dots", 0.0
        self.mods = {}  # the stance a slow layer has set (goals.STANCE levels); empty = all normal
        self.plan = {}  # (junction tile, arriving direction) -> (Decision, goal, finished_at)
        self.depth = {}  # plan key -> how many answers deep the chain was when it was asked
        self.pause_until, self.prev_score = -1, None
        self.revised_keys = set()  # situations already counted as revised
        self.commit = None  # (junction tile, direction): the decision made on this visit to a junction tile
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
        facts = junction_facts(state, image, tile=tile, arriving=arriving, park=self.park)
        facts["mods"], facts["stance"] = dict(self.mods), stance_text(self.mods)
        if self.knowledge:
            goal_text = f"GOAL: {self.goal} - {GOALS[self.goal]} {facts['stance']}".rstrip()
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
        best = max(options, key=lambda d: score_option(self.goal, options[d], self.mods))
        regret = score_option(self.goal, options[best], self.mods) - score_option(self.goal, options[chosen], self.mods)
        return best if best != chosen and regret > REVISE_REGRET else None

    def _survive(self, state, image, tile, arriving, chosen, where, facts=None):
        """The survival instinct: veto `chosen` if it runs into a ghost and a clearly safer way exists.

        Two views, because they see different things. From the junction `chosen` is for: is the exit itself safe?
        From Pac-Man's own tile: is the very next step safe? (A ghost reaching the junction as he does is invisible
        from the junction: its exit looks clear. From his tile it is a ghost 3 steps ahead.)"""
        if not self.reflex or not self._near_threat(state):
            return chosen
        me, heading = tuple(state.pacman.tile), LOWER_TO_UPPER.get(state.pacman.direction)
        if me != tuple(tile) and heading:
            own = reflex(junction_facts(state, image), heading)  # his next step is along the corridor, `heading`
            if own is not None:
                return self._noted_reflex(where, me, heading, own, state, image)
        facts = facts or junction_facts(state, image, tile=tile, arriving=arriving)
        better = reflex(facts, chosen)
        if better is None:
            return chosen
        return self._noted_reflex(where, tile, chosen, better, state, image, facts)

    def _noted_reflex(self, where, tile, chosen, better, state, image, facts=None):
        facts = facts or junction_facts(state, image)
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
        return final

    def _book(self, hold):
        """Add the time spent holding to the game's totals, once."""
        if not hold["booked"]:
            hold["booked"] = True
            seconds = time.time() - hold["since"]
            if hold["kind"] == "park":
                self.game.parked_seconds += seconds
            else:
                self.game.refuge_seconds += seconds

    def _holding(self, state, image, me):
        """Parked against a wall: keep pushing into it while the reason holds, then leave. True if it steered."""
        hold = self.hold
        if hold is None:
            return False
        me = tuple(me)
        if me != hold["tile"]:  # off the tile: by his own exit, or something moved him
            self._book(hold)
            self.hold = None
            return False
        if hold["exit"]:  # leaving: keep to the chosen exit until he is off the tile (the corridor logic would turn him)
            self._go(state, image, me, hold["push"], hold["exit"], "junction", "hold-exit")
            return True
        here = Maze(image).bfs(me)
        near, now = nearest_normal(state, here), time.time()
        if hold["kind"] == "park":
            gathered_close = ready_to_eat({"ghosts_close": gathered(state, here, LURE_RADIUS), "pressure": near})
            reason = ("goal changed" if self.goal != "ambush" else "gathered" if gathered_close
                      else "timeout" if now - hold["since"] > HOVER_SECONDS else None)
        else:
            reason = ("clear" if near is None or near > REFUGE_CLEAR
                      else "timeout" if now - hold["since"] > REFUGE_SECONDS else None)
        steps = self._ghost_steps(state, here)
        if reason is None:
            self.broker.steer(hold["push"])  # stay put. The reflex does not steer while parked, on purpose
            if now - hold["noted"] > 2.0:
                hold["noted"] = now
                self.log(event=hold["kind"], phase="waiting", steps=steps)
            return True
        self._book(hold)
        if hold["kind"] == "refuge":
            self.refuge_cooldown = now + 8.0  # do not run straight back
        hold["exit"] = self.rule.decide(self._facts(state, image, me, hold["push"]), self.goal).direction
        self.log(event=hold["kind"], phase="leave", why=reason, exit=hold["exit"], steps=steps)
        self._go(state, image, me, hold["push"], hold["exit"], "junction", "hold-exit")
        return True

    def _begin_hold(self, state, image, me, heading):
        """He is against a wall (his heading runs into it): is this a place to wait?"""
        maze, tile = Maze(image), tuple(me)
        if heading is None or maze.passable(step(tile, heading)):
            return False
        here, kind = maze.bfs(tile), None
        near = nearest_normal(state, here)
        if self.refuge and tile == SAFE_SPOT and all_out(state, here) and self.goal != "hunt_ghosts":
            if near is not None and near <= REFUGE_CLEAR:
                kind = "refuge"
        if kind is None and self.park and self.goal == "ambush" and is_stop(maze, tile, heading):
            pellet = nearest_energizer(maze, here)
            if pellet and HOVER_MIN <= maze.bfs(pellet).get(tile, 99) <= HOVER_MAX and not ready_to_eat(
                    {"ghosts_close": gathered(state, here, LURE_RADIUS), "pressure": near}):
                kind = "park"
        if kind is None:
            return False
        now = time.time()
        self.hold = {"kind": kind, "tile": tile, "push": heading, "since": now, "noted": now, "exit": None, "booked": False}
        if kind == "park":
            self.game.parks += 1
        else:
            self.game.refuges += 1
        self.log(event=kind, phase="start", tile=list(tile), steps=self._ghost_steps(state, here))
        return True

    def _refuge_run(self, state, image, me):
        """A ghost is close and the safe spot can be reached first: go there. True if it steered."""
        if not self.refuge or self.goal == "hunt_ghosts" or time.time() < self.refuge_cooldown:
            return False
        direction = refuge_move(state, Maze(image), me)
        if direction is None:
            return False
        if time.time() - self.refuge_ran_at > 2.0:
            self.log(event="refuge", phase="run", tile=list(me), direction=direction)
        self.refuge_ran_at = time.time()
        self.broker.steer(direction)
        return True

    @staticmethod
    def _ghost_steps(state, here):
        return sorted(here[g.tile] for n, g in state.ghosts.items()
                      if not state.frightened[n] and not state.eyes[n] and g.tile in here)

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
            self.game_started, self.plan, self.game, self.commit = time.time(), {}, GameStats(), None
            self.worker.clear_queued()
        self.was_playing, self.last_state = True, state
        self.game.update(state, image, self.goal, time.time())

        if image[0x4E04 - 0x4000] != 3:  # READY screen, death animation, level transition
            self.broker.steer(None)
            self.plan, self.commit = {}, None
            if self.hold is not None:  # the READY screen after a life lost while waiting
                self.game.park_deaths += self.hold["kind"] == "park"
                self.game.refuge_deaths += self.hold["kind"] == "refuge"
                self.log(event=self.hold["kind"], phase="died")
            elif time.time() - self.refuge_ran_at < 1.5:
                self.game.refuge_deaths += 1
                self.log(event="refuge", phase="died on the way")
            self.hold = None
            return None

        if time.time() - self.goal_at > self.strategy_interval:
            goal = self.strategy.choose(state, image, frame)
            mods = dict(getattr(self.strategy, "mods", {}))
            if goal != self.goal:
                self.log(event="goal", goal=goal)
            if mods != self.mods:
                self.log(event="stance", mods=mods)
            for record in getattr(self.strategy, "drain", lambda: [])():  # the slow layer's own notes
                self.log(**record)
            self.goal, self.mods, self.goal_at = goal, mods, time.time()

        self._watch_for_pause(state, frame)
        self._collect(state, image, frame)
        if self._holding(state, image, state.pacman.tile):
            return None
        heading_now = LOWER_TO_UPPER.get(state.pacman.direction)
        if (self.park or self.refuge) and self._begin_hold(state, image, state.pacman.tile, heading_now) \
                and self._holding(state, image, state.pacman.tile):
            return None
        if self._refuge_run(state, image, state.pacman.tile):
            return None
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

        # A junction is decided once per visit. Pac-Man spends several frames on its tile, and each change of his
        # heading would otherwise look like arriving at a new junction and decide again: two answers that disagree
        # flip him back and forth on the spot while a ghost closes in. Survival can still override the commitment.
        here = tuple(me)
        if self.commit and here != self.commit[0] and (junction is None or tuple(junction) != self.commit[0]):
            self.commit = None  # he has left it
        if self.commit and here == self.commit[0]:
            self.commit = (here, self._go(state, image, me, heading, self.commit[1], "junction", "commit"))
            return None

        if junction is not None and steps <= 1 and key in self.plan:
            decision = self.plan[key][0]
            self.consumed.add(key)
            if key not in self.applied:
                self.applied.add(key)
                self.stats["on_time"] += 1
            self.commit = (tuple(junction), self._go(state, image, junction, arriving, decision.direction, "junction",
                                                     decision.source))
        elif junction is not None and steps == 0:
            # At the junction with no answer yet: a rule decides, and we count it as late.
            facts = junction_facts(state, image, tile=junction, arriving=heading, park=self.park)
            facts["mods"] = dict(self.mods)
            decision = self.rule.decide(facts, self.goal)
            self.plan[key] = (decision, self.goal, time.time())
            self.applied.add(key)
            self.consumed.add(key)
            self.stats["late_rule"] += 1
            why = self._late_reason(key, asked_now)
            self.stats["late_why"][why] = self.stats["late_why"].get(why, 0) + 1
            self.log(event="late", tile=list(junction), direction=decision.direction, why=why, steps_seen=steps)
            self.commit = (tuple(junction), self._go(state, image, junction, heading, decision.direction, "junction",
                                                     "late-rule"))
        elif path:
            self._go(state, image, me, heading, path[0], "corridor", "corridor")  # corridor / forced corner
        return None
