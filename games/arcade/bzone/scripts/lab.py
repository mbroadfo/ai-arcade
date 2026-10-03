"""Battlezone's real-time lab: a fixed-rate loop running a diagnostic policy, logging every tick.

    observe -> decode -> facts -> policy(state, facts) -> hold controls -> wait for the next tick

Each tick's log line says when it ran and how late, which snapshot it saw and how old that was when the command went
out, the decoded state, what the policy chose and why, what was actually pressed and released, how long the decision
and the broker took, and what changed since the last tick (a life, a hit). explain.py reads it back.

Start the Pi side first (MAME, the state stream; full speed for timing work):
    python tools/start_pi_game.py --game arcade/bzone --speed 1.0
    python games/arcade/bzone/scripts/lab.py --policy pattern --hz 10 --seconds 60
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tools"))
from gamelib import DEFAULT_PI_HOST, ROOT, load_game  # noqa: E402  (puts the repository root on sys.path)

from arcadekit.clock import TickClock  # noqa: E402
from arcadekit.observatory import DEFAULT_ADDRESS, LiveSink  # noqa: E402
from broker_link import BrokerLink  # noqa: E402
from games.arcade.bzone.controls import broker_actions, describe  # noqa: E402
from games.arcade.bzone.facts import derive, shell_pass  # noqa: E402
from games.arcade.bzone.observe import status  # noqa: E402
from games.arcade.bzone.policies import POLICIES  # noqa: E402
from games.arcade.bzone.state import LETTERS  # noqa: E402
from state_client import StateStream  # noqa: E402


def digest(state):
    """The decoded state, flat, for the log."""
    return {"playing": state.playing, "lives": state.lives, "hits": state.hits, "score": state.score, "hits_taken": state.hits_taken,
            "dying": state.dying, "angle": state.tank.angle, "x": state.tank.x, "y": state.tank.y,
            "enemy": [state.enemy.x, state.enemy.y, state.enemy.angle], "enemy_distance": state.enemy_distance,
            "enemy_in_range": state.enemy_in_range, "missile": state.missile, "saucer": state.saucer,
            "enemy_fire": state.enemy.fire, "enemy_shell": list(state.enemy.shell), "enemy_timer": state.enemy_timer,
            # where the flying shell's path passes the tank, seen or not: for scoring dodges afterwards, never shown
            "shell_true": list(shell_pass(state, seen_only=False))}


def changes(before, after):
    """Outcome changes between two observations."""
    out = []
    if before is None:
        return out
    if after.lives < before.lives:
        out.append("life lost")
    if after.score > before.score:
        out.append(f"score {before.score}->{after.score}")
    if after.hits_taken != before.hits_taken:
        out.append(f"hit taken ({after.hits_taken})")
    if after.enemy.fire and not before.enemy.fire:
        out.append("enemy fired")
    if after.dying and not before.dying:
        out.append("windshield cracked")
    if after.playing != before.playing:
        out.append("game started" if after.playing else "game ended")
    return out


def enter_initials(stream, broker, name="AI ", seconds=40):
    """On the high-score screen, enter `name` (letters and spaces only: the game has no digits). The game says the right
    hand controller steps the letter and fire takes it; which tread direction steps which way is learned from RAM (a
    press that changes nothing tries the next), so a missed or doubled step is corrected. Returns (done, attempts)."""
    tries = [(2, "UP"), (2, "DOWN"), (1, "UP"), (1, "DOWN")]
    learned = {}  # +1 / -1 -> the control that steps that way
    attempts, deadline, k = [], time.time() + seconds, 0
    while time.time() < deadline:
        (_, state, _), _ = stream.latest_timed()
        if not state.entering_initials:
            return True, attempts
        i = min(state.initial_index, 2)
        want, have = LETTERS[name[i]], state.initials[i]
        if have == want:
            broker.tap("BUTTON_1", ms=150)
            attempts.append({"letter": i, "fire": True})
            time.sleep(0.6)
            continue
        way = 1 if ((want - have) // 2) % 27 <= 13 else -1
        control = learned.get(way) or tries[k % len(tries)]
        broker.hold({control})
        time.sleep(0.3)  # the game steps after 4 frames held, then every 4 more
        broker.hold(set())
        time.sleep(0.25)
        (_, after, _), _ = stream.latest_timed()
        moved = ((after.initials[i] - have) // 2) % 27 if after.initial_index == i else 0
        attempts.append({"letter": i, "control": list(control), "from": have, "to": after.initials[i]})
        if moved:
            learned[1 if moved <= 13 else -1] = control
        elif control not in learned.values():
            k += 1  # this one does nothing here: the next
    return False, attempts


def start_game(stream, broker, coins):
    (_, state, _), _ = stream.latest_timed()
    if state.playing:
        return
    for _ in range(coins):
        broker.tap("COIN")
        time.sleep(0.6)
    # After a game with a high score the game asks for three initials and ignores START until they are in.
    deadline = time.time() + 45
    while time.time() < deadline:
        (_, state, _), _ = stream.latest_timed()
        if state.entering_initials:
            enter_initials(stream, broker)
        broker.tap("START")
        time.sleep(1.0)
        (_, state, _), _ = stream.latest_timed()
        if state.playing:
            return
    raise RuntimeError("the game did not start (coins, start, initials)")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--policy", choices=sorted(POLICIES), default="pattern")
    parser.add_argument("--hz", type=float, default=10.0, help="decisions a second")
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--coins", type=int, default=None, help="coins one play costs (default: the game's "
                        "COINS_PER_PLAY, which assumes its SETTINGS were applied by start_pi_game.py)")
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    parser.add_argument("--out", default=str(ROOT / "runs"))
    parser.add_argument("--tag", default="")
    parser.add_argument("--observatory", default="%s:%d" % DEFAULT_ADDRESS,
                        help="HOST:PORT of the Observatory (tools/observatory.py), or none")
    args = parser.parse_args(argv)

    game = load_game("arcade/bzone")
    policy = POLICIES[args.policy]
    label = "-".join(p for p in (time.strftime("%Y%m%d-%H%M%S"), "arcade_bzone-lab", args.policy,
                                 f"{args.hz:g}hz", args.tag) if p)
    path = Path(args.out) / f"{label}.jsonl"
    path.parent.mkdir(exist_ok=True)
    log = open(path, "w", buffering=1)
    stream = StateStream(args.host, game=game)
    stream.start_latest()
    broker = BrokerLink(args.host)
    coins = game.COINS_PER_PLAY if args.coins is None else args.coins
    run_record = {"event": "run", "label": label, "game": "arcade/bzone", "policy": args.policy, "hz": args.hz,
                  "decider": f"lab: {args.policy} (code)", "model": None, "knowledge": None, "goal": None,
                  "strategist": None, "games": 1, "switches": {"hz": args.hz}, "seconds": args.seconds,
                  "settings": game.SETTINGS, "coins": coins, "t": time.time()}
    log.write(json.dumps(run_record) + "\n")
    stop, paused = [], [False]

    def command(m):  # from the Observatory: stop the run, or the game was paused / resumed
        if m.get("op") == "stop":
            stop.append(1)
        elif m.get("op") == "pause":
            paused[0] = bool(m.get("on"))
    live = None
    if args.observatory != "none":
        host, _, port = args.observatory.rpartition(":")
        live = LiveSink((host, int(port)), hello=lambda: [run_record], on_command=command)
    start_game(stream, broker, coins)

    clock = TickClock(args.hz)
    began, previous, last_frame, held, kills = time.monotonic(), None, None, frozenset(), 0
    try:
        shown = 0.0
        while time.monotonic() - began < args.seconds and not stop:
            tick = clock.wait()
            if paused[0]:  # the game is paused: hold nothing, and the pause does not count toward the run's length
                if broker.holding:
                    broker.release_all()
                    log.write(json.dumps({"event": "paused", "t": time.time()}) + "\n")
                began += 1 / args.hz
                continue
            try:
                (frame, state, _), arrived = stream.latest_timed(timeout=1.0)
            except TimeoutError:  # no state (paused from elsewhere, or the stream reconnecting): skip the tick
                began += 1 / args.hz
                continue
            t = tick.began - began
            t0 = time.perf_counter()
            facts = derive(state)
            names, why = policy(state, facts, t, held)
            decide_ms = (time.perf_counter() - t0) * 1000  # facts and policy together
            held = frozenset(names)
            before = broker.holding
            t1 = time.perf_counter()
            broker.hold(broker_actions(names))
            broker_ms = (time.perf_counter() - t1) * 1000
            age_ms = (time.time() - arrived) * 1000  # how old the observation was when the command had gone out
            record = {"event": "tick", "tick": tick.index, "t": round(t, 3), "interval_ms": round(tick.interval * 1000, 1),
                      "late_ms": round(tick.late_ms, 1), "frame": frame, "new_frame": frame != last_frame,
                      "obs_age_ms": round(age_ms, 1), "state": digest(state), "facts": vars(facts),
                      "game_turn": state.game_turn, "action": sorted(names),
                      "action_words": describe(names), "why": why,
                      "pressed": sorted(map(list, broker.holding - before)),
                      "released": sorted(map(list, before - broker.holding)),
                      "decide_ms": round(decide_ms, 3), "broker_ms": round(broker_ms, 1),
                      "changes": changes(previous, state)}
            clock.done(tick)
            record["work_ms"] = round(tick.work_ms, 1)
            log.write(json.dumps(record) + "\n")
            if live and tick.began - shown >= 0.2:  # the Observatory: five status lines a second
                shown = tick.began
                live.send({**status(state, facts, frame, describe(names), why, kills), "t": round(time.time(), 3)})
            for change in record["changes"] if live else ():
                live.send({"event": "lab", "what": change, "t": round(time.time(), 3)})
            kills += any(c.startswith("score") for c in record["changes"])  # a tank, missile or saucer destroyed
            previous, last_frame = state, frame
            if previous.playing is False and t > 5:
                broker.release_all()
                for _ in range(40):  # a high score: the initials screen follows the game within a few seconds
                    (_, state, _), _ = stream.latest_timed()
                    if state.entering_initials:
                        entered, attempts = enter_initials(stream, broker)
                        log.write(json.dumps({"event": "initials", "entered": entered, "attempts": attempts,
                                              "t": time.time()}) + "\n")
                        break
                    time.sleep(0.25)
                break  # the game ended
    except KeyboardInterrupt:
        pass
    finally:
        broker.release_all()
        summary = {"event": "summary", "clock": clock.summary(), "final": digest(previous) if previous else None,
                   "t": time.time()}
        log.write(json.dumps(summary) + "\n")
        log.close()
        try:
            from games.arcade.bzone.scripts.summarize import summarize
            result = summarize(path) or {}
        except Exception as exc:  # the measures are a report: a failure here must not lose the run's end
            result = {"error": repr(exc)}
        print("measured: " + json.dumps(result))
        if live:
            words = {"score": "score", "kills": "kills", "deaths": "lives lost", "seconds": "survived (s)",
                     "shots": "shots fired", "distance": "distance moved", "still_threatened_s":
                     "still while the enemy may fire (s)", "enemy_shots_survived": "enemy shots survived"}
            live.send({"event": "lab", "what": "measured: " + ", ".join(
                f"{w} {result.get(k)}" + (f" of {result.get('enemy_shots')}" if k == "enemy_shots_survived" else "")
                for k, w in words.items() if k in result), "t": round(time.time(), 3)})
            live.send({"event": "run_end", "label": label, "games_completed": int(bool(previous and not previous.playing)), "t": time.time()})
            live.close(2.0)
        stream.close()
    print(json.dumps(summary["clock"], indent=1))
    print(f"log: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
