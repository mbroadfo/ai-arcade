"""The player for games on Pac-Man's board: reads the streamed state, asks a decider at each junction, steers.

The game's own facts (its name in the texts, ghost knowledge, the safe spot) come in a spec.Spec; a game binds this
module to its spec (bind.py), so Pac-Man and Ms. Pac-Man share every line of it.

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

from arcadekit.answers import AnswerBook
from arcadekit.ledger import SOURCE_BY, Ledger

from .danger import ASK_EVERY, MAX_AGE, MAX_DRIFT, danger_facts
from .deciders import Decision, RuleDecider
from .events import GameStats
from .features import GOALS, LURE_RADIUS, junction_facts, ready_to_eat, score_option
from .goals import stance_text
from .knowledge import build_state_text
from .maze import LOWER_TO_UPPER, OPPOSITE, Maze, step
from . import observe as observing, screen
from .park import (HOVER_MAX, HOVER_MIN, HOVER_SECONDS, REFUGE_CLEAR, REFUGE_SECONDS, all_out, gathered,
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
LATE_DEFAULTS = ("rule", "keep")  # with no answer on arrival: the rule decides, or nothing changes (see _late_keep)
# ask_order (a timing switch): "nearest" puts the question for the junction he is heading to at the front of the model's
# queue, asks chained junctions only when the model is idle (nothing queued or being answered), and withdraws queued
# questions no longer on his way; "fifo" asks in the order questions come up (before 2 October 2026). Measured that
# day on Ms. Pac-Man: with fifo, 434 of 537 late junctions had their question still waiting behind chained ones, though
# answers took only 258 ms. "Idle" first meant only "nothing queued", which is nearly always true (the model takes a
# question at once), so guesses still held up the next real question: none of 425 chained guesses were skipped.
# With guesses only when idle, 140 of 292 late junctions came under 0.8 s after the previous one (a guess refused
# when its answer arrived was never asked again) and 114 within 1.5 s of a turn-around (the junction behind him had
# not been asked). So in spare time (_spare_guess) the path ahead is filled each tick: short-corridor lates fell to 58
# of 542. Asking about the junction behind him too (turn_guess) did not help turn-arounds (102 of 542), so it is off.
ASK_ORDERS = ("nearest", "fifo")


class Player:
    def __init__(self, stream, broker, worker, strategy, decisions_log, strategy_interval=0.5,
                 lookahead=LOOKAHEAD_STEPS, knowledge=None, revise=False, reflex=True,
                 chain_depth=CHAIN_DEPTH, park=False, refuge=False, danger_query=False,
                 danger_worker=None, clock=time.time, late="rule", strategy_timing="events", ask_order="nearest",
                 turn_guess=False, *, spec):
        # Ablation switches. revise: code re-checks each stored answer against fresh facts (code overruling the
        # decider, so off by default). reflex: the survival instinct. chain_depth: look-ahead chain, 0 = off.
        self.clock = clock  # wall-clock seconds; a replay passes recorded time
        self.spec = spec  # the game's own facts (spec.Spec)
        if refuge and spec.safe_spot is None:
            raise ValueError(f"{spec.name} has no safe spot: --refuge does not apply")
        self.revise, self.reflex, self.chain_depth = revise, reflex, chain_depth
        # park: ambush waits against a wall near the energizer instead of pacing. refuge: hide at the safe spot when a
        # ghost is close and he can get there first. Both off by default (park.py); neither lets the reflex steer while held.
        self.park, self.refuge = park, refuge
        # danger_query: in a corridor with a ghost close, the model is asked "carry on or turn back" (danger.py) and its
        # answer is executed. danger_worker: a separate (fast) model for it; None = the main worker, at the front.
        self.danger_query, self.danger_worker = danger_query, danger_worker
        self.danger_asked_at, self.danger_out, self.danger_answer = 0.0, None, None
        # late: what happens when no answer is there on arrival. "rule" decides (code-late); "keep" changes nothing and
        # waits for the model's answer (_late_keep), so a run can be the model alone. An ablation switch.
        if late not in LATE_DEFAULTS:
            raise ValueError(f"late must be one of {LATE_DEFAULTS}")
        self.late = late
        self.waiting = None  # (key, why, since): at a junction with no answer, late="keep"
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
        # questions asked ahead and their answers, keyed (junction tile, arriving direction); depth = how many answers
        # deep the chain was when it was asked (arcadekit.answers)
        self.book = AnswerBook(worker, self.clock, ttl=PLAN_TTL, urgent_worker=danger_worker)
        self.pause_until, self.prev_score = -1, None
        self.revised_keys = set()  # situations already counted as revised
        self.commit = None  # (junction tile, direction): the decision made on this visit to a junction tile
        self.applied = set()  # junctions already counted, so stats are per junction, not per tick
        self.last_frame, self.last_start_attempt = -1, 0.0
        self.was_playing, self.game_started, self.last_state, self.last_image = False, 0.0, None, None
        self.finished = 0
        self.game = GameStats()  # what happened in the current game
        self.last_reflex = (None, 0.0)
        self.stats = {"on_time": 0, "late_rule": 0, "late_keep": 0, "queries": 0, "chained": 0, "revised": 0,
                      "late_why": {},
                      "danger": {"asked": 0, "answered": 0, "dropped": 0, "turned_back": 0, "carried_on": 0}}  # moves: executed junction decisions by who made them
        self.last_how = None  # how the last _go() changed the proposed direction: None, "revise" or "reflex"
        self.latencies, self.sources = [], {}
        self.ledger = Ledger(self.log)  # who executed each move (arcadekit.ledger)
        if ask_order not in ASK_ORDERS:
            raise ValueError(f"ask_order must be one of {ASK_ORDERS}")
        self.nearest = ask_order == "nearest"
        self.stats["queue"] = self.book.counts  # promoted, withdrawn, spare_skipped
        self.stats["spare"] = {"ahead": 0, "behind": 0, "behind_used": 0}  # guesses asked in spare time (_spare_guess)
        self.behind_asked = set()
        self.turn_guess = turn_guess
        # a model slow layer shares the model server: tell it when no junction question waits (strategy.TIMINGS)
        if hasattr(strategy, "configure"):
            strategy.configure(timing=strategy_timing, quiet=self._quiet)

    def _quiet(self):
        """No junction or danger question is waiting or being answered."""
        workers = [w for w in (self.worker, self.danger_worker) if w is not None]
        return not any(getattr(w, "busy", lambda: False)() for w in workers)

    def log(self, **record):
        record["t"] = round(self.clock(), 3)
        record.setdefault("frame", self.last_frame)  # lines up the log with a recording of the stream
        self.decisions_log.write(json.dumps(record) + "\n")

    def observe(self):
        """What is on screen now, for the Observatory's `status` line: facts read from the stream, nothing decided."""
        state, frame = self.last_state, self.last_frame
        record = {"event": "status", "frame": frame, "title": self.spec.name, "game": self.finished + 1,
                  "playing": self.was_playing, "goal": self.goal, "stance": stance_text(self.mods),
                  "held": self.broker.held, "screen": {"size": screen.SIZE, "tile_to_px": screen.TILE_TO_PX},
                  "moves": {f"{by} ({via})": n for (by, via), n in self.ledger.counts.items()}}
        if state is None or not self.was_playing:
            return record
        here = Maze(self.last_image).bfs(tuple(state.pacman.tile))
        record["marks"] = screen.marks(state, here, self.spec.name, self.spec.ghost_labels)
        lines = [[self.spec.name, f"{tuple(state.pacman.tile)} {LOWER_TO_UPPER.get(state.pacman.direction) or '-'}"]]
        for name, ghost in state.ghosts.items():
            mode = "EYES" if state.eyes[name] else "BLUE" if state.frightened[name] else "normal"
            steps = here.get(ghost.tile)
            lines.append([self.spec.ghost_labels.get(name, name), f"{steps} steps  {mode}" if steps is not None else mode])
        if state.fruit_tile:
            lines.append(["fruit", f"{tuple(state.fruit_tile)} {here.get(state.fruit_tile, '?')} steps"])
        record.update(score=state.score, level=state.level, lives=state.lives, dots=state.dots_eaten, lines=lines,
                      facts=observing.facts(state, self.last_image, here), series=observing.series(state, here))
        return record

    def _ahead(self, maze, key):
        """The junction he is heading to and the ones its stored answers lead to (the chain still on his way)."""
        keys, k = {key}, key
        for _ in range(CHAIN_DEPTH_PAUSE + 1):
            stored = self.book.get(k)
            if stored is None:
                break
            choice = stored[0].choice
            junction, steps, path = maze.walk_to_decision(step(k[0], choice), choice)
            if junction is None or steps > CHAIN_MAX_STEPS:
                break
            k = (junction, path[-1] if path else choice)
            keys.add(k)
        return keys

    def _facts(self, state, image, tile, arriving):
        facts = junction_facts(state, image, tile=tile, arriving=arriving, park=self.park)
        facts["mods"], facts["stance"] = dict(self.mods), stance_text(self.mods)
        if self.knowledge:
            goal_text = f"GOAL: {self.goal} - {GOALS[self.goal]} {facts['stance']}".rstrip()
            facts["state_text"] = build_state_text(self.knowledge, state, image, facts, tile, arriving, goal_text,
                                                   spec=self.spec)
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
        if key != (chosen, better) or self.clock() - at > 1.0:  # count an emergency once, not per tick
            self.game.reflexes += 1
            self.log(event="reflex", where=where, tile=list(tile), chosen=chosen, override=better,
                     threat=facts["options"][chosen]["threat_steps"])
        self.last_reflex = ((chosen, better), self.clock())
        return better

    def _go(self, state, image, tile, arriving, chosen, where, source):
        """Steer to `chosen` unless survival vetoes it. A turn-back is logged with why and what was around."""
        facts, how = None, None
        if self.revise and source not in ("late-rule", "corridor"):  # check a stored answer against the world now
            facts = junction_facts(state, image, tile=tile, arriving=arriving)
            better = self._revise(facts, chosen)
            if better:
                if (tile, arriving) not in self.revised_keys:  # count a situation once, not once per control tick
                    self.revised_keys.add((tile, arriving))
                    self.stats["revised"] += 1
                    self.log(event="revise", tile=list(tile), was=chosen, now=better, goal=self.goal, source=source)
                chosen, source, how = better, "revised", "revise"
        final = self._survive(state, image, tile, arriving, chosen, where, facts)
        if final != chosen:
            how = "reflex"
        self.last_how = how
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
            seconds = self.clock() - hold["since"]
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
        near, now = nearest_normal(state, here), self.clock()
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
        hold["exit"] = self.rule.decide(self._facts(state, image, me, hold["push"]), self.goal).choice
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
        if self.refuge and tile == self.spec.safe_spot and all_out(state, here) and self.goal != "hunt_ghosts":
            if near is not None and near <= REFUGE_CLEAR:
                kind = "refuge"
        if kind is None and self.park and self.goal == "ambush" and is_stop(maze, tile, heading):
            pellet = nearest_energizer(maze, here)
            if pellet and HOVER_MIN <= maze.bfs(pellet).get(tile, 99) <= HOVER_MAX and not ready_to_eat(
                    {"ghosts_close": gathered(state, here, LURE_RADIUS), "pressure": near}):
                kind = "park"
        if kind is None:
            return False
        now = self.clock()
        self.hold = {"kind": kind, "tile": tile, "push": heading, "since": now, "noted": now, "exit": None, "booked": False}
        if kind == "park":
            self.game.parks += 1
        else:
            self.game.refuges += 1
        self.log(event=kind, phase="start", tile=list(tile), steps=self._ghost_steps(state, here))
        self.ledger.count("code-skill", kind)
        return True

    def _refuge_run(self, state, image, me):
        """A ghost is close and the safe spot can be reached first: go there. True if it steered."""
        if not self.refuge or self.goal == "hunt_ghosts" or self.clock() < self.refuge_cooldown:
            return False
        direction = refuge_move(state, Maze(image), me, self.spec.safe_spot)
        if direction is None:
            return False
        if self.clock() - self.refuge_ran_at > 2.0:
            self.log(event="refuge", phase="run", tile=list(me), direction=direction)
            self.ledger.count("code-skill", "refuge")
        self.refuge_ran_at = self.clock()
        self.broker.steer(direction)
        return True

    @staticmethod
    def _ghost_steps(state, here):
        return sorted(here[g.tile] for n, g in state.ghosts.items()
                      if not state.frightened[n] and not state.eyes[n] and g.tile in here)

    def _book_move(self, key, decision, final, late=None, answered_at=None, **extra):
        """One record per junction decision: who proposed the direction, who executed it, how old the answer was
        (arcadekit.ledger has the vocabulary). Forced single-exit corners are mechanical and not booked."""
        if self.last_how:  # the reflex or a revision changed the proposal
            by, via = "code-override", self.last_how
        else:
            by, via = ("code-late" if late else SOURCE_BY[decision.source]), "junction"
        age = None if answered_at is None else round(self.clock() - answered_at, 2)
        self.ledger.book(by, via, tile=list(key[0]), arriving=key[1], goal=self.goal, mods=dict(self.mods),
                         proposed=decision.choice, source=decision.source, confidence=round(decision.confidence, 2),
                         latency_ms=round(decision.latency_ms), age_s=age, executed=final, late=late,
                         **({"orders": decision.orders} if getattr(decision, "orders", None) is not None else {}),
                         **extra)

    def _late_keep(self, state, image, junction, heading, key, why):
        """late="keep": no answer on arrival and nothing changes. He carries on if his way goes on (booked code-late via
        keep when he leaves the tile), or stops against the wall and waits. An answer that arrives while he is still on
        the tile is used and booked as the model's, with how long he waited."""
        if self.waiting is None or self.waiting[0] != key:
            self.waiting = (key, why, self.clock())
            self.stats["late_keep"] += 1
            self.stats["late_why"][why] = self.stats["late_why"].get(why, 0) + 1
            self.log(event="late", tile=list(junction), direction=None, why=why, steps_seen=0, default="keep")
        if heading and Maze(image).passable(step(tuple(junction), heading)):
            final = self._go(state, image, junction, heading, heading, "junction", "late-keep")  # the reflex may veto
            if final != heading:  # it did: that is code's move, booked now
                self._book_move(key, Decision(heading, "keep"), final, late=why)
                self.applied.add(key)
                self.waiting, self.commit = None, (tuple(junction), final)
        else:
            self.broker.steer(heading)  # push on into the wall: stopped, waiting for the answer

    def _left_waiting(self, here):
        """He left the junction he was waiting at without an answer: he carried on, and code's default made that move."""
        key, why, since = self.waiting
        if here == tuple(key[0]):
            return
        self.waiting = None
        if key not in self.applied:
            self.ledger.book("code-late", "keep", tile=list(key[0]), arriving=key[1], goal=self.goal, executed=key[1],
                             late=why, waited_s=round(self.clock() - since, 2))

    def _watch_for_pause(self, state, frame):
        """A ghost-sized score jump means a ghost was just eaten: the game freezes for about a second."""
        jump = None if self.prev_score is None else state.score - self.prev_score
        if jump in GHOST_SCORES + tuple(x + 10 for x in GHOST_SCORES):  # +10: a dot eaten in the same step
            self.pause_until = frame + PAUSE_FRAMES
            self.log(event="pause", frame=frame, score=jump)
        self.prev_score = state.score

    # the book's state, by the names the tests and the log analysis use
    plan = property(lambda self: self.book.plan)
    depth = property(lambda self: self.book.depth)
    consumed = property(lambda self: self.book.consumed)

    def _collect(self, state, image, frame):
        """Store finished answers and, for each, ask about the junction it leads to (the chain)."""
        paused = frame < self.pause_until
        limit = 0 if self.chain_depth == 0 else (self.chain_depth + 2 if paused else self.chain_depth)
        answers, urgent = self.book.collect()
        for key, goal, facts, decision, finished_at in urgent:  # danger answers
            self._danger_answered(key, decision, finished_at)
        for key, goal, facts, decision, finished_at in answers:
            self.latencies.append(decision.latency_ms)
            self.sources[decision.source] = self.sources.get(decision.source, 0) + 1
            depth = self.depth.get(key, 0)
            self.log(event="decision", tile=list(key[0]), arriving=key[1], goal=goal,
                     direction=decision.choice, source=decision.source,
                     confidence=round(decision.confidence, 3), latency_ms=round(decision.latency_ms),
                     probabilities=decision.probabilities, note=decision.note, chain=depth,
                     **({"orders": decision.orders} if decision.orders is not None else {}))
            if depth >= limit:
                continue
            nxt = step(key[0], decision.choice)
            junction, steps, path = Maze(image).walk_to_decision(nxt, decision.choice)
            if junction is None or steps > CHAIN_MAX_STEPS:
                continue
            key2 = (junction, path[-1] if path else decision.choice)
            if not self.book.has(key2) and not self.book.pending(key2):
                if self.book.ask(key2, self.goal, self._facts(state, image, junction, key2[1]), depth=depth + 1,
                                 spare=self.nearest):
                    self.stats["queries"] += 1
                    self.stats["chained"] += 1

    def _model_idle(self):
        return not getattr(self.worker, "busy", lambda: True)()

    def _spare_guess(self, state, image, maze, key, heading):
        """With the model idle, ask one guess: the first junction on his way without an answer (following the
        stored answers, chain_depth deep), else (turn_guess) the junction behind him, which a turn-around (his own
        choice or the reflex) makes the next one. A timing choice: what is asked about, never what is chosen."""
        k = key
        for depth in range(1, self.chain_depth + 1):
            stored = self.book.get(k)
            if stored is None:
                break
            choice = stored[0].choice
            junction, steps, path = maze.walk_to_decision(step(k[0], choice), choice)
            if junction is None or steps > CHAIN_MAX_STEPS:
                break
            k = (junction, path[-1] if path else choice)
            if not self.book.has(k) and not self.book.pending(k):
                if self.book.ask(k, self.goal, self._facts(state, image, junction, k[1]), depth=depth, spare=True):
                    self.stats["queries"] += 1
                    self.stats["chained"] += 1
                    self.stats["spare"]["ahead"] += 1
                return
        back = OPPOSITE.get(heading)
        if back is None or not self.turn_guess:
            return
        junction, steps, path = maze.walk_to_decision(state.pacman.tile, back)
        if junction is None or steps > CHAIN_MAX_STEPS:
            return
        k = (junction, path[-1] if path else back)
        if not self.book.has(k) and not self.book.pending(k):
            if self.book.ask(k, self.goal, self._facts(state, image, junction, k[1]), depth=1, spare=True):
                self.stats["queries"] += 1
                self.stats["spare"]["behind"] += 1
                self.behind_asked.add(k)

    def _danger_answered(self, key, decision, finished_at):
        self.danger_out = None
        self.danger_answer = (key, decision, finished_at)
        self.stats["danger"]["answered"] += 1
        self.latencies.append(decision.latency_ms)
        self.sources[decision.source] = self.sources.get(decision.source, 0) + 1

    def _danger(self, state, image, me, heading):
        """A corridor with a ghost close: apply the model's last answer, and ask again. True if it steered."""
        steered = False
        now = self.clock()
        if self.danger_answer is not None:
            (_, asked_tile, asked_heading), decision, finished_at = self.danger_answer
            self.danger_answer = None
            drift = abs(me[0] - asked_tile[0]) + abs(me[1] - asked_tile[1])
            if now - finished_at > MAX_AGE or heading != asked_heading or drift > MAX_DRIFT:
                self.stats["danger"]["dropped"] += 1  # too late to matter
            elif decision.choice == OPPOSITE[heading]:
                self.stats["danger"]["turned_back"] += 1
                self.ledger.count(SOURCE_BY[decision.source], "danger")
                self.log(event="danger", phase="turn back", tile=list(me), heading=heading, source=decision.source,
                         confidence=round(decision.confidence, 2), latency_ms=round(decision.latency_ms),
                         age_s=round(now - finished_at, 2))
                self.broker.steer(decision.choice)
                steered = True
            else:
                self.stats["danger"]["carried_on"] += 1
        if self.danger_out is not None and now - self.danger_asked_at > 2.0:
            self.danger_out = None  # an answer that never came: ask again
        if self.danger_out is None and now - self.danger_asked_at >= ASK_EVERY and self._near_threat(state):
            asked = None
            if danger_facts(junction_facts(state, image, tile=me, arriving=heading), heading) is not None:  # cheap check
                asked = danger_facts(self._facts(state, image, me, heading), heading)  # then the full prompt text
            if asked is not None:
                key = ("danger", tuple(me), heading)
                if self.book.ask(key, self.goal, asked, urgent=True):
                    self.danger_out, self.danger_asked_at = key, now
                    self.stats["danger"]["asked"] += 1
        return steered

    def _pregame(self, state):
        """Attract/coin screens: put in a coin, press start. Returns True if it handled the frame."""
        if state.mode not in ("attract", "coin"):
            return False
        self.broker.steer(None)
        if self.clock() - self.last_start_attempt > 4:
            self.last_start_attempt = self.clock()
            self.broker.tap("COIN" if state.credits == 0 else "START")
        return True

    def partial_result(self):
        """The game in progress as a result record (for when a run is stopped mid-game), or None."""
        last = self.last_state
        if not self.was_playing or last is None:
            return None
        return {"game": self.finished + 1, "score": last.score, "level": last.level, "dots": last.dots_eaten,
                "seconds": round(self.clock() - self.game_started), "partial": True,
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
                        "dots": last.dots_eaten, "seconds": round(self.clock() - self.game_started),
                        "goal": getattr(self.strategy, "mission", None), **self.game.summary()}
            self._pregame(state)
            return None
        if state.mode != "playing":
            return None
        if not self.was_playing:
            self.game_started, self.game, self.commit, self.waiting = self.clock(), GameStats(), None, None
            self.book.forget()
            self.book.clear_queued()
        self.was_playing, self.last_state, self.last_image = True, state, image
        self.game.update(state, image, self.goal, self.clock())

        if image[0x4E04 - 0x4000] != 3:  # READY screen, death animation, level transition
            self.broker.steer(None)
            self.book.forget()
            self.commit, self.waiting = None, None
            if self.hold is not None:  # the READY screen after a life lost while waiting
                self.game.park_deaths += self.hold["kind"] == "park"
                self.game.refuge_deaths += self.hold["kind"] == "refuge"
                self.log(event=self.hold["kind"], phase="died")
            elif self.clock() - self.refuge_ran_at < 1.5:
                self.game.refuge_deaths += 1
                self.log(event="refuge", phase="died on the way")
            self.hold = None
            return None

        if self.clock() - self.goal_at > self.strategy_interval:
            goal = self.strategy.choose(state, image, frame)
            mods = dict(getattr(self.strategy, "mods", {}))
            if goal != self.goal:
                self.log(event="goal", goal=goal)
            if mods != self.mods:
                self.log(event="stance", mods=mods)
            for record in getattr(self.strategy, "drain", lambda: [])():  # the slow layer's own notes
                self.log(**record)
            self.goal, self.mods, self.goal_at = goal, mods, self.clock()

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
        now = self.clock()
        self.book.drop_stale()
        maze = Maze(image)
        me = state.pacman.tile
        heading = LOWER_TO_UPPER.get(state.pacman.direction)
        junction, steps, path = maze.walk_to_decision(me, heading)
        arriving = path[-1] if path and junction is not None else heading
        key = (junction, arriving)
        for done in self.book.retire_except(key):  # an answer is used once, at its junction
            self.revised_keys.discard(done)
        if self.nearest and junction is not None:  # questions about junctions he is no longer heading for
            ahead = self._ahead(maze, key)
            self.book.withdraw(lambda k: k in ahead or isinstance(k[0], str))  # ("danger", ...) questions stay

        asked_now = False
        if junction is not None:
            self.applied = {k for k in self.applied if k == key}
            if not self.book.has(key) and steps <= self.lookahead:
                facts = self._facts(state, image, junction, arriving)
                if self.book.ask(key, self.goal, facts, next_point=self.nearest):
                    self.stats["queries"] += 1
                    asked_now = True
            if self.nearest and not asked_now and self._model_idle():
                self._spare_guess(state, image, maze, key, heading)

        # A junction is decided once per visit. Pac-Man spends several frames on its tile, and each change of his
        # heading would otherwise look like arriving at a new junction and decide again: two answers that disagree
        # flip him back and forth on the spot while a ghost closes in. Survival can still override the commitment.
        here = tuple(me)
        if self.waiting:
            self._left_waiting(here)
        if self.commit and here != self.commit[0] and (junction is None or tuple(junction) != self.commit[0]):
            self.commit = None  # he has left it
        if self.commit and here == self.commit[0]:
            self.commit = (here, self._go(state, image, me, heading, self.commit[1], "junction", "commit"))
            return None

        if junction is not None and steps <= 1 and self.book.has(key):
            decision, _, answered_at = self.book.get(key)
            self.book.use(key)
            first = key not in self.applied
            if first:
                self.applied.add(key)
                self.stats["on_time"] += 1
                if key in self.behind_asked:  # once per guess: the same junction can be asked again later
                    self.behind_asked.discard(key)
                    self.stats["spare"]["behind_used"] += 1
            final = self._go(state, image, junction, arriving, decision.choice, "junction", decision.source)
            if first:
                extra = {}
                if self.waiting and self.waiting[0] == key:  # it came while he waited at the junction (late="keep")
                    extra = {"waited_s": round(self.clock() - self.waiting[2], 2)}
                    self.waiting = None
                self._book_move(key, decision, final, answered_at=answered_at, **extra)
            self.commit = (tuple(junction), final)
        elif junction is not None and steps == 0 and self.late == "keep":
            self._late_keep(state, image, junction, heading, key, self.book.late_reason(key, asked_now))
        elif junction is not None and steps == 0:
            # At the junction with no answer yet: a rule decides, and we count it as late.
            facts = junction_facts(state, image, tile=junction, arriving=heading, park=self.park)
            facts["mods"] = dict(self.mods)
            decision = self.rule.decide(facts, self.goal)
            self.book.put(key, decision, self.goal)
            self.applied.add(key)
            self.book.use(key)
            self.stats["late_rule"] += 1
            why = self.book.late_reason(key, asked_now)
            self.stats["late_why"][why] = self.stats["late_why"].get(why, 0) + 1
            self.log(event="late", tile=list(junction), direction=decision.choice, why=why, steps_seen=steps)
            final = self._go(state, image, junction, heading, decision.choice, "junction", "late-rule")
            self._book_move(key, decision, final, late=why)
            self.commit = (tuple(junction), final)
        elif path:
            if self.danger_query and self._danger(state, image, me, heading):
                return None  # the model turned him round
            self._go(state, image, me, heading, path[0], "corridor", "corridor")  # corridor / forced corner
        return None
