"""Independent evaluation of a saved policy.

The shared tape, hints, and any forced button stay out. A training score is a
record of assisted play. It does not, by itself, say the network can do the route.

The game adapter supplies the protocol: benchmark names, success definitions,
and how a step becomes a milestone. This module does not name a game.
Comparable results share one protocol, one scenario, and one seed list.
An attempt that does not finish leaves the whole evaluation incomplete.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

EVAL_NAME = "best.eval.json"
_SCENARIO_KEYS = (
    "protocol",
    "benchmark",
    "benchmark_definition",
    "game",
    "objective",
    "frame_skip",
    "deterministic",
    "limit",
    "n_actions",
    "start",
    "seed",
)


class EvalIsolationError(RuntimeError):
    """An evaluation step was scripted. That attempt does not count."""


def checkpoint_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def begin_life(n_envs: int = 1) -> tuple:
    """Hidden state for the first decision of one life.

    episode_start is True. A recurrent policy resets its memory on that call.
    The next decisions of the same life reuse the state `decide` returns, with
    episode_start False. A new life starts here again, which drops the old state.
    """
    count = max(int(n_envs), 1)
    return None, [True] * count


def decide(model, observation, memory: tuple):
    """One deterministic decision. Returns the action and the memory for the next one."""
    state, episode_start = memory
    action, state = model.predict(
        observation,
        state=state,
        episode_start=episode_start,
        deterministic=True,
    )
    return action, (state, [False] * len(episode_start))


def independent_episode(info: dict | None) -> bool:
    """True when this step was not produced by a tape, a hint, or a demonstration."""
    if not isinstance(info, dict):
        return False
    if info.get("forced") or info.get("assisted") or info.get("assisted_reset"):
        return False
    try:
        demonstrated = int(info.get("demonstration_steps") or 0)
    except (TypeError, ValueError):
        return False
    return demonstrated == 0


def blank_milestones(protocol: dict) -> dict:
    return {name: False for name in protocol["benchmarks"]}


def _same(left, right) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return bool(left) is bool(right)
    try:
        return int(left) == int(right)
    except (TypeError, ValueError):
        return left == right


def bind_scenario(protocol: dict, identity: dict | None = None) -> tuple[dict | None, str | None]:
    """The experiment the adapter named, plus the checkpoint this run measured.

    Identity may name the benchmark, the start, the step cap, and the base seed.
    A game, objective, frame skip, or action count that disagrees with the
    adapter is rejected. Those fields are the scenario.
    """
    if not isinstance(protocol, dict) or not protocol.get("name") or not protocol.get("benchmarks"):
        return None, "protocol is missing"
    identity = dict(identity or {})
    benchmarks = dict(protocol["benchmarks"])
    benchmark = identity.get("benchmark") or protocol.get("default_benchmark")
    if benchmark not in benchmarks:
        return None, f"unknown benchmark {benchmark}"
    try:
        scenario = {
            "protocol": protocol["name"],
            "benchmark": benchmark,
            "benchmark_definition": benchmarks[benchmark],
            "definitions": benchmarks,
            "game": protocol["game"],
            "objective": protocol["objective"],
            "frame_skip": int(protocol["frame_skip"]),
            "deterministic": True,
            "limit": int(identity["limit"]) if identity.get("limit") is not None else int(protocol["limit"]),
            "n_actions": int(protocol["n_actions"]),
            "start": identity.get("start") or protocol["start"],
            "seed": int(identity["seed"]) if identity.get("seed") is not None else int(protocol.get("seed") or 0),
            "model": identity.get("model"),
            "rom_sha1": identity.get("rom_sha1"),
            "core_sha1": identity.get("core_sha1"),
            "checkpoint_sha256": identity.get("checkpoint_sha256"),
        }
    except (KeyError, TypeError, ValueError) as exc:
        return None, f"protocol is incomplete: {exc}"
    for key in ("game", "objective", "frame_skip", "n_actions"):
        if identity.get(key) is None:
            continue
        if not _same(identity[key], scenario[key]):
            return None, f"{key} differs from the protocol"
    return scenario, None


def failed_evaluation(reason: str, scenario: dict | None = None) -> dict:
    """An evaluation that did not produce a usable measurement."""
    scenario = dict(scenario or {})
    definitions = dict(scenario.get("definitions") or {})
    benchmark = scenario.get("benchmark")
    result = {
        "assisted": False,
        "failed": True,
        "failure": reason,
        "attempts": 0,
        "successes": 0,
        "success_rate": 0.0,
        "deaths": 0,
        "clears": 0,
        "decisions": 0,
        "frames": 0,
        "furthest": None,
        "seeds": [],
        "episodes": [],
        "record": "independent",
        "protocol": scenario.get("protocol"),
        "benchmark": benchmark,
        "benchmark_definition": scenario.get("benchmark_definition") or definitions.get(benchmark) or "",
        "definitions": definitions,
    }
    for key in (
        "rom_sha1",
        "core_sha1",
        "checkpoint_sha256",
        "model",
        "seed",
        "game",
        "objective",
        "frame_skip",
        "limit",
        "n_actions",
        "start",
        "deterministic",
    ):
        if scenario.get(key) is not None:
            result[key] = scenario[key]
    return result


def _furthest(episodes: list[dict]) -> dict | None:
    good = [episode for episode in episodes if not episode.get("failed")]
    if not good:
        return None
    return max(good, key=lambda episode: int(episode.get("score") or 0))


def _counted_successes(episodes: list[dict], benchmark: str) -> int:
    count = 0
    for episode in episodes:
        if episode.get("failed"):
            continue
        milestones = episode.get("milestones") or {}
        if milestones.get(benchmark):
            count += 1
    return count


def _record_furthest(episode: dict, protocol: dict) -> dict:
    sample = protocol["metrics"]({})
    return {key: episode.get(key, sample[key]) for key in sample}


def evaluate_attempts(run_one, attempts: int, identity: dict, protocol: dict) -> dict:
    """Run one protocol. run_one(seed) plays one life with no assistance.

    Success follows the named benchmark. A failed attempt makes the evaluation
    incomplete: the successes are not a rate that can be compared or promoted.
    """
    scenario, problem = bind_scenario(protocol, identity)
    if problem:
        return failed_evaluation(problem, scenario or identity)
    benchmark = scenario["benchmark"]
    benchmarks = protocol["benchmarks"]
    missing = [
        key for key in ("rom_sha1", "core_sha1", "checkpoint_sha256", "model")
        if not scenario.get(key)
    ]
    if missing:
        return failed_evaluation("missing " + ", ".join(missing), scenario)
    try:
        attempts = int(attempts)
    except (TypeError, ValueError):
        return failed_evaluation("attempts are not a number", scenario)
    if attempts < 1:
        return failed_evaluation("no attempts", scenario)
    base = int(scenario.get("seed") or 0)
    seeds = [base + index for index in range(attempts)]
    episodes = []
    for seed in seeds:
        try:
            episode = run_one(seed)
        except Exception as exc:
            episodes.append({"seed": seed, "failed": True, "failure": str(exc)})
            continue
        if not isinstance(episode, dict) or not independent_episode(episode):
            episodes.append({
                "seed": seed,
                "failed": True,
                "failure": "assisted or forced step in an independent evaluation",
            })
            continue
        raw = episode.get("milestones")
        if not isinstance(raw, dict):
            episodes.append({
                "seed": seed,
                "failed": True,
                "failure": "milestones missing",
            })
            continue
        milestones = {name: bool(raw.get(name)) for name in set(benchmarks) | set(raw)}
        clear_name = protocol.get("clear_benchmark")
        episodes.append({
            **episode,
            "seed": seed,
            "failed": False,
            "milestones": milestones,
            "success": bool(milestones.get(benchmark)),
            "cleared": bool(milestones.get(clear_name)) if clear_name else False,
        })
    if any(episode.get("failed") for episode in episodes):
        result = failed_evaluation("incomplete evaluation", scenario)
        result["attempts"] = attempts
        result["episodes"] = episodes
        result["seeds"] = seeds
        return result
    successes = _counted_successes(episodes, benchmark)
    furthest = _furthest(episodes)
    decision_values = [int(episode.get("decisions") or 0) for episode in episodes if episode.get("success")]
    frame_values = [int(episode.get("frames") or 0) for episode in episodes if episode.get("success")]
    counts = {
        name: sum(1 for episode in episodes if (episode.get("milestones") or {}).get(name))
        for name in benchmarks
    }
    clear_name = protocol.get("clear_benchmark")
    return {
        "assisted": False,
        "failed": False,
        "failure": None,
        "attempts": attempts,
        "successes": successes,
        "success_rate": successes / attempts,
        "deaths": sum(1 for episode in episodes if episode.get("dead")),
        "clears": counts.get(clear_name, 0) if clear_name else 0,
        "decisions": min(decision_values) if decision_values else 0,
        "frames": min(frame_values) if frame_values else 0,
        "furthest": _record_furthest(furthest, protocol),
        "seeds": seeds,
        "episodes": episodes,
        "milestone_counts": counts,
        "record": "independent",
        **scenario,
    }


def _episode_from_trace(last: dict, reached: dict, decisions: int, frames: int, benchmark: str, protocol: dict) -> dict:
    milestones = {name: bool(reached.get(name)) for name in set(protocol["benchmarks"]) | set(reached)}
    clear_name = protocol.get("clear_benchmark")
    return {
        **protocol["metrics"](last),
        "cleared": bool(milestones.get(clear_name)) if clear_name else False,
        "success": bool(milestones.get(benchmark)),
        "milestones": milestones,
        "decisions": int(decisions),
        "frames": int(frames),
        "forced": False,
        "assisted": False,
        "demonstration_steps": 0,
    }


def _watch(protocol: dict, reached: dict, info: dict) -> dict:
    observe = protocol.get("observe")
    if observe is None:
        return dict(reached)
    return observe(reached, info)


def play_unassisted(env, choose, *, seed: int, protocol: dict, limit: int | None = None, benchmark: str | None = None) -> dict:
    """One life. choose(observation) is the policy. A forced step aborts the attempt.

    `decisions` counts policy steps. `frames` counts emulator frames, one frame
    skip per decision.
    """
    scenario, problem = bind_scenario(protocol, {"limit": limit, "benchmark": benchmark, "seed": seed})
    if problem:
        raise EvalIsolationError(problem)
    step_limit = int(scenario["limit"])
    skip = int(scenario["frame_skip"])
    _obs, info = env.reset(seed=seed)
    if not independent_episode(info):
        raise EvalIsolationError("reset was assisted")
    last = info
    decisions = 0
    reached = _watch(protocol, blank_milestones(protocol), info)
    for _ in range(step_limit):
        _obs, _reward, terminated, truncated, info = env.step(choose(_obs))
        if info.get("forced") or info.get("assisted"):
            raise EvalIsolationError("step was forced")
        decisions += 1
        last = info
        reached = _watch(protocol, reached, info)
        if terminated or truncated:
            break
    return _episode_from_trace(last, reached, decisions, decisions * skip, scenario["benchmark"], protocol)


def compare_independent(before: dict, after: dict) -> dict:
    """Success rates from two finished evaluations of the same scenario and seeds."""
    for label, item in (("before", before), ("after", after)):
        if not isinstance(item, dict) or item.get("assisted") or item.get("failed"):
            raise ValueError(f"{label} is not a finished independent evaluation")
        if item.get("record") != "independent":
            raise ValueError(f"{label} is not a finished independent evaluation")
        episodes = item.get("episodes")
        if not isinstance(episodes, list) or any(episode.get("failed") for episode in episodes if isinstance(episode, dict)):
            raise ValueError(f"{label} is not a finished independent evaluation")
    for key in _SCENARIO_KEYS + (
        "model",
        "attempts",
        "rom_sha1",
        "core_sha1",
        "seeds",
    ):
        if before.get(key) != after.get(key):
            raise ValueError(f"{key} differs")
    before_score = int((before.get("furthest") or {}).get("score") or 0)
    after_score = int((after.get("furthest") or {}).get("score") or 0)
    return {
        "before_success_rate": before["success_rate"],
        "after_success_rate": after["success_rate"],
        "before_furthest": before_score,
        "after_furthest": after_score,
        "attempts": [before["attempts"], after["attempts"]],
        "seeds": before.get("seeds"),
        "benchmark": before.get("benchmark"),
        "improved": after["success_rate"] > before["success_rate"] or after_score > before_score,
        "record": "independent",
    }


def read_eval(path: Path) -> dict | None:
    file = Path(path)
    if not file.is_file():
        return None
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_eval(path: Path, result: dict) -> None:
    from games.lab.worker import atomic_json
    atomic_json(Path(path), result)


def _expected_seeds(protocol: dict, attempts: int) -> list[int]:
    base = int(protocol.get("seed") or 0)
    return [base + index for index in range(attempts)]


def accept_eval(
    result: dict | None,
    zip_path: Path,
    *,
    protocol: dict,
    model: str | None = None,
    benchmark: str | None = None,
    start: str | None = None,
) -> bool:
    """True when this file is a complete independent measurement of these weights.

    The protocol is the requested experiment. A different game, benchmark,
    frame skip, action count, step cap, attempt count, or seed list is a
    different experiment. An episode that failed leaves the file incomplete.
    """
    if not isinstance(protocol, dict) or not protocol.get("benchmarks"):
        return False
    if not isinstance(result, dict) or result.get("assisted") or result.get("failed"):
        return False
    if result.get("record") != "independent":
        return False
    if result.get("protocol") != protocol.get("name"):
        return False
    expected_benchmark = benchmark or protocol.get("default_benchmark")
    if result.get("benchmark") != expected_benchmark:
        return False
    definitions = protocol["benchmarks"]
    if expected_benchmark not in definitions:
        return False
    if result.get("benchmark_definition") != definitions[expected_benchmark]:
        return False
    expected_model = model if model is not None else result.get("model")
    if not expected_model or result.get("model") != expected_model:
        return False
    if result.get("start") != (start or protocol.get("start")):
        return False
    if result.get("game") != protocol.get("game") or result.get("objective") != protocol.get("objective"):
        return False
    if result.get("deterministic") is not True:
        return False
    try:
        if int(result.get("frame_skip")) != int(protocol["frame_skip"]):
            return False
        if int(result.get("limit")) != int(protocol["limit"]):
            return False
        if int(result.get("n_actions")) != int(protocol["n_actions"]):
            return False
        if int(result.get("seed")) != int(protocol.get("seed") or 0):
            return False
        attempts = int(result.get("attempts") or 0)
        successes = int(result.get("successes") or 0)
        rate = float(result.get("success_rate"))
    except (KeyError, TypeError, ValueError):
        return False
    if attempts != int(protocol["attempts"]) or successes < 0 or successes > attempts:
        return False
    if abs(rate - (successes / attempts)) > 1e-9 or not 0.0 <= rate <= 1.0:
        return False
    expected_seeds = _expected_seeds(protocol, attempts)
    if result.get("seeds") != expected_seeds:
        return False
    if protocol.get("rom_sha1") and result.get("rom_sha1") != protocol["rom_sha1"]:
        return False
    if protocol.get("core_sha1") and result.get("core_sha1") != protocol["core_sha1"]:
        return False
    episodes = result.get("episodes")
    if not isinstance(episodes, list) or len(episodes) != attempts:
        return False
    supports = protocol.get("supports")
    for episode, seed in zip(episodes, expected_seeds):
        if not isinstance(episode, dict) or episode.get("failed"):
            return False
        try:
            episode_seed = int(episode["seed"])
        except (KeyError, TypeError, ValueError):
            return False
        if episode_seed != seed:
            return False
        milestones = episode.get("milestones")
        if not isinstance(milestones, dict):
            return False
        for name in definitions:
            if name not in milestones:
                return False
        claimed = bool(milestones.get(expected_benchmark))
        if claimed and supports is not None and not supports(episode, expected_benchmark):
            return False
        if bool(episode.get("success")) != claimed:
            return False
    if _counted_successes(episodes, expected_benchmark) != successes:
        return False
    rom = result.get("rom_sha1")
    core = result.get("core_sha1")
    if not isinstance(rom, str) or not rom or not isinstance(core, str) or not core:
        return False
    try:
        digest = checkpoint_sha256(zip_path)
    except OSError:
        return False
    if result.get("checkpoint_sha256") != digest:
        return False
    return True


def play_loaded(model, *, seed: int, protocol: dict, limit: int | None = None, benchmark: str | None = None) -> dict:
    """One life on the env the loaded policy is attached to. No tape and no hint.

    Recurrent policies keep the hidden state returned by predict. episode_start
    is True on the first decision of the life and False after that. The life
    ends when the env says so, so the next attempt starts from begin_life again.
    `decisions` counts those policy steps. `frames` multiplies by the protocol
    frame skip, which is how many emulator frames one decision holds.
    """
    scenario, problem = bind_scenario(protocol, {"limit": limit, "benchmark": benchmark, "seed": seed})
    if problem:
        raise EvalIsolationError(problem)
    vec = model.get_env()
    if vec is None:
        raise EvalIsolationError("the policy has no environment")
    model.set_random_seed(int(seed))
    observation = vec.reset()
    reset_info = {}
    infos = getattr(vec, "reset_infos", None)
    if infos:
        reset_info = dict(infos[0] or {})
    if reset_info.get("forced") or reset_info.get("assisted") or reset_info.get("assisted_reset"):
        raise EvalIsolationError("reset was assisted")
    if int(reset_info.get("demonstration_steps") or 0) != 0:
        raise EvalIsolationError("reset was assisted")
    last = reset_info
    decisions = 0
    reached = _watch(protocol, blank_milestones(protocol), reset_info)
    memory = begin_life(int(getattr(vec, "num_envs", 1) or 1))
    skip = int(scenario["frame_skip"])
    for _ in range(int(scenario["limit"])):
        action, memory = decide(model, observation, memory)
        observation, _reward, dones, infos = vec.step(action)
        info = dict(infos[0] or {})
        if info.get("forced") or info.get("assisted"):
            raise EvalIsolationError("step was forced")
        decisions += 1
        last = info
        reached = _watch(protocol, reached, info)
        if bool(dones[0]):
            break
    return _episode_from_trace(last, reached, decisions, decisions * skip, scenario["benchmark"], protocol)


def run_checkpoint(
    checkpoint: Path,
    model: str,
    attempts: int,
    seed: int,
    protocol: dict,
    limit: int | None = None,
    benchmark: str | None = None,
) -> dict:
    """Load weights into the adapter's game. A missing ROM or torch is a failed evaluation."""
    checkpoint = Path(checkpoint)
    identity: dict = {
        "model": model,
        "seed": int(seed),
        "benchmark": benchmark,
        "deterministic": True,
    }
    if limit is not None:
        identity["limit"] = int(limit)
    scenario, problem = bind_scenario(protocol, identity)
    if problem:
        return failed_evaluation(problem, scenario or identity)
    try:
        identity["checkpoint_sha256"] = checkpoint_sha256(checkpoint)
    except OSError as exc:
        return failed_evaluation(str(exc), scenario)
    try:
        import hashlib
        from games.lab.cores import ensure_core
        from games.lab.env import make_env
        from games.lab.integrations import get
        from games.lab.models import registry
        integration = get(protocol["game"])
        rom = integration.pinned_rom()
        if rom is None:
            return failed_evaluation("ROM is missing", {**scenario, **identity})
        core = ensure_core(integration.system)
        identity["rom_sha1"] = integration.rom_sha1()
        identity["core_sha1"] = hashlib.sha1(core.read_bytes()).hexdigest()
        identity["objective"] = integration.objective
        identity["game"] = integration.id
        identity["n_actions"] = len(integration.actions)
        env = make_env(integration.system, rom, integration)
        identity["frame_skip"] = int(getattr(env.unwrapped, "frame_skip", 0) or 0)
        scenario, problem = bind_scenario(protocol, identity)
        if problem:
            env.close()
            return failed_evaluation(problem, scenario or identity)
        loaded = registry.load(model, str(checkpoint), env)
        try:
            return evaluate_attempts(
                lambda one_seed: play_loaded(
                    loaded,
                    seed=one_seed,
                    protocol=protocol,
                    limit=scenario["limit"],
                    benchmark=scenario["benchmark"],
                ),
                attempts,
                identity,
                protocol,
            )
        finally:
            env.close()
    except Exception as exc:
        return failed_evaluation(f"{type(exc).__name__}: {exc}", {**scenario, **identity})


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Evaluate a checkpoint with no tape and no hints")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--game", default="smb_1_1", help="Adapter that supplies the protocol. Mario is the reference.")
    parser.add_argument("--attempts", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--benchmark", default=None)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    from games.lab.integrations import get
    protocol = get(args.game).evaluation_protocol()
    attempts = protocol["attempts"] if args.attempts is None else args.attempts
    seed = protocol.get("seed") or 0 if args.seed is None else args.seed
    result = run_checkpoint(
        Path(args.checkpoint),
        args.model,
        attempts,
        seed,
        protocol,
        args.limit,
        args.benchmark,
    )
    if args.out:
        write_eval(Path(args.out), result)
    print(json.dumps(result))
    return 2 if result.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
