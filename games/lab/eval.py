"""Independent evaluation of a saved policy.

The shared tape, hints, and any forced button stay out. A training score is a
record of assisted play. It does not, by itself, say the network can do the route.

Comparable results share one protocol. Touching the World 1-1 flagpole is its
own milestone. It is not entry into a later world.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

EVAL_NAME = "best.eval.json"
PROTOCOL_NAME = "smb-unassisted-v1"
PROTOCOL_ATTEMPTS = 5
PROTOCOL_LIMIT = 2000
PROTOCOL_FRAME_SKIP = 4
PROTOCOL_ACTIONS = 12
DEFAULT_BENCHMARK = "enter-world-4"
GAME_START = "game"

# Explicit success definitions. A later milestone is never implied by an earlier one.
BENCHMARKS = {
    "clear-1-1-flag": (
        "Mario touches the World 1-1 flagpole while that stage is showing. "
        "This does not mean he entered a later world."
    ),
    "reach-world-1-2": (
        "The emulator is in World 1-2 or any later level, and Mario is alive. "
        "The World 1-1 castle walk does not count."
    ),
    "enter-world-4": (
        "The emulator shows World 4 and Mario is alive. "
        "A flagpole does not count, including the World 1-1 flagpole."
    ),
}


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


def blank_milestones() -> dict:
    return {name: False for name in BENCHMARKS}


def update_milestones(reached: dict, info: dict) -> dict:
    """Latch milestones from one env step. The flagpole does not latch a later world."""
    reached = dict(reached or blank_milestones())
    for name in BENCHMARKS:
        reached.setdefault(name, False)
    try:
        world = int(info.get("world") or 1)
        stage = int(info.get("stage") or 1)
    except (TypeError, ValueError):
        return reached
    alive = not info.get("dead") and not info.get("dying")
    if info.get("flag_get") and world == 1 and stage == 1 and alive:
        reached["clear-1-1-flag"] = True
    if alive and (world > 1 or (world == 1 and stage >= 2)):
        reached["reach-world-1-2"] = True
    if alive and world >= 4:
        reached["enter-world-4"] = True
    return reached


def _position_supports(episode: dict, benchmark: str) -> bool:
    """The recorded ending still agrees with a milestone the episode claims."""
    try:
        world = int(episode.get("world") or 0)
        stage = int(episode.get("stage") or 0)
    except (TypeError, ValueError):
        return False
    if benchmark == "enter-world-4":
        return world > 4 or (world == 4 and stage >= 1)
    if benchmark == "reach-world-1-2":
        return world > 1 or (world == 1 and stage >= 2)
    if benchmark == "clear-1-1-flag":
        return True
    return True


def failed_evaluation(reason: str, identity: dict | None = None) -> dict:
    """An evaluation that did not produce a usable measurement."""
    identity = dict(identity or {})
    benchmark = identity.get("benchmark") or DEFAULT_BENCHMARK
    result = {
        "assisted": False,
        "failed": True,
        "failure": reason,
        "attempts": 0,
        "successes": 0,
        "success_rate": 0.0,
        "deaths": 0,
        "clears": 0,
        "frames": 0,
        "furthest": None,
        "seeds": [],
        "episodes": [],
        "record": "independent",
        "protocol": PROTOCOL_NAME,
        "benchmark": benchmark,
        "benchmark_definition": BENCHMARKS.get(benchmark, identity.get("benchmark_definition") or ""),
        "definitions": dict(BENCHMARKS),
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
        if identity.get(key) is not None:
            result[key] = identity[key]
    return result


def _protocol(identity: dict) -> dict:
    """Fields that make two evaluations the same experiment."""
    identity = dict(identity or {})
    benchmark = identity.get("benchmark") or DEFAULT_BENCHMARK
    if benchmark in BENCHMARKS:
        definition = BENCHMARKS[benchmark]
    else:
        definition = str(identity.get("benchmark_definition") or "")
    deterministic = identity.get("deterministic")
    return {
        "protocol": PROTOCOL_NAME,
        "benchmark": benchmark,
        "benchmark_definition": definition,
        "definitions": dict(BENCHMARKS),
        "game": identity.get("game") or "smb_1_1",
        "objective": identity.get("objective") or "progress",
        "frame_skip": int(identity.get("frame_skip") or PROTOCOL_FRAME_SKIP),
        "deterministic": True if deterministic is None else bool(deterministic),
        "limit": int(identity.get("limit") or PROTOCOL_LIMIT),
        "n_actions": int(identity.get("n_actions") or PROTOCOL_ACTIONS),
        "start": identity.get("start") or GAME_START,
        "model": identity.get("model"),
        "rom_sha1": identity.get("rom_sha1"),
        "core_sha1": identity.get("core_sha1"),
        "checkpoint_sha256": identity.get("checkpoint_sha256"),
        "seed": int(identity.get("seed") or 0),
    }


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


def evaluate_attempts(run_one, attempts: int, identity: dict) -> dict:
    """Run standardized attempts. run_one(seed) plays one life with no assistance.

    Success follows the named benchmark. A flagpole milestone stays in the
    episode and does not count as entering a later world.
    """
    stamped = _protocol(identity)
    benchmark = stamped["benchmark"]
    if benchmark in BENCHMARKS:
        pass
    elif not stamped["benchmark_definition"]:
        return failed_evaluation("benchmark has no definition", stamped)
    missing = [
        key for key in ("rom_sha1", "core_sha1", "checkpoint_sha256", "model")
        if not stamped.get(key)
    ]
    if missing:
        return failed_evaluation("missing " + ", ".join(missing), stamped)
    try:
        attempts = int(attempts)
    except (TypeError, ValueError):
        return failed_evaluation("attempts are not a number", stamped)
    if attempts < 1:
        return failed_evaluation("no attempts", stamped)
    base = int(stamped.get("seed") or 0)
    episodes = []
    for index in range(attempts):
        seed = base + index
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
        milestones = {name: bool(raw.get(name)) for name in set(BENCHMARKS) | set(raw)}
        episodes.append({
            **episode,
            "seed": seed,
            "failed": False,
            "milestones": milestones,
            "success": bool(milestones.get(benchmark)),
            "cleared": bool(milestones.get("clear-1-1-flag")),
        })
    good = [episode for episode in episodes if not episode.get("failed")]
    if not good:
        result = failed_evaluation("every attempt failed", stamped)
        result["attempts"] = attempts
        result["episodes"] = episodes
        result["seeds"] = [base + index for index in range(attempts)]
        return result
    successes = _counted_successes(episodes, benchmark)
    furthest = _furthest(good)
    frames = [int(episode.get("frames") or 0) for episode in episodes if episode.get("success")]
    counts = {
        name: sum(1 for episode in good if (episode.get("milestones") or {}).get(name))
        for name in BENCHMARKS
    }
    return {
        "assisted": False,
        "failed": False,
        "failure": None,
        "attempts": attempts,
        "successes": successes,
        "success_rate": successes / attempts,
        "deaths": sum(1 for episode in good if episode.get("dead")),
        "clears": counts["clear-1-1-flag"],
        "frames": min(frames) if frames else 0,
        "furthest": {
            "score": int(furthest.get("score") or 0),
            "world": int(furthest.get("world") or 1),
            "stage": int(furthest.get("stage") or 1),
            "x_pos": int(furthest.get("x_pos") or 0),
            "time": int(furthest.get("time") or 0),
        },
        "seeds": [base + index for index in range(attempts)],
        "episodes": episodes,
        "milestone_counts": counts,
        "record": "independent",
        **stamped,
    }


def _episode_from_trace(last: dict, reached: dict, frames: int, benchmark: str) -> dict:
    milestones = {name: bool(reached.get(name)) for name in set(BENCHMARKS) | set(reached)}
    return {
        "score": int(last.get("score") or 0),
        "world": int(last.get("world") or 1),
        "stage": int(last.get("stage") or 1),
        "x_pos": int(last.get("x_pos") or 0),
        "dead": bool(last.get("dead")),
        "time": int(last.get("time") or 0),
        "cleared": bool(milestones.get("clear-1-1-flag")),
        "success": bool(milestones.get(benchmark)),
        "milestones": milestones,
        "frames": frames,
        "forced": False,
        "assisted": False,
        "demonstration_steps": 0,
    }


def play_unassisted(env, choose, *, seed: int, limit: int = PROTOCOL_LIMIT, benchmark: str = DEFAULT_BENCHMARK) -> dict:
    """One life. choose(observation) is the policy. A forced step aborts the attempt."""
    _obs, info = env.reset(seed=seed)
    if not independent_episode(info):
        raise EvalIsolationError("reset was assisted")
    last = info
    frames = 0
    reached = update_milestones(blank_milestones(), info)
    for _ in range(int(limit)):
        _obs, _reward, terminated, truncated, info = env.step(choose(_obs))
        if info.get("forced") or info.get("assisted"):
            raise EvalIsolationError("step was forced")
        frames += 1
        last = info
        reached = update_milestones(reached, info)
        if terminated or truncated:
            break
    return _episode_from_trace(last, reached, frames, benchmark)


def compare_independent(before: dict, after: dict) -> dict:
    """Success rates from two finished evaluations of the same benchmark."""
    for label, item in (("before", before), ("after", after)):
        if not isinstance(item, dict) or item.get("assisted") or item.get("failed"):
            raise ValueError(f"{label} is not a finished independent evaluation")
        if item.get("record") != "independent":
            raise ValueError(f"{label} is not a finished independent evaluation")
    for key in (
        "protocol",
        "benchmark",
        "model",
        "start",
        "attempts",
        "rom_sha1",
        "core_sha1",
        "frame_skip",
        "objective",
        "game",
        "limit",
        "n_actions",
        "deterministic",
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


def accept_eval(
    result: dict | None,
    zip_path: Path,
    *,
    model: str | None = None,
    benchmark: str | None = None,
    start: str | None = None,
) -> bool:
    """True when this file is the standard independent measurement of these weights.

    The protocol is fixed: the same game, objective, frame skip, action count,
    step limit, deterministic policy, and attempt count. The benchmark names
    which milestone `success_rate` counts. The default benchmark is entering
    World 4. A flagpole record does not pass that benchmark.
    """
    if not isinstance(result, dict) or result.get("assisted") or result.get("failed"):
        return False
    if result.get("record") != "independent":
        return False
    if result.get("protocol") != PROTOCOL_NAME:
        return False
    expected_benchmark = benchmark or DEFAULT_BENCHMARK
    if result.get("benchmark") != expected_benchmark:
        return False
    if expected_benchmark in BENCHMARKS and result.get("benchmark_definition") != BENCHMARKS[expected_benchmark]:
        return False
    if expected_benchmark not in BENCHMARKS and not result.get("benchmark_definition"):
        return False
    expected_model = model if model is not None else result.get("model")
    if not expected_model or result.get("model") != expected_model:
        return False
    if result.get("start") != (start or GAME_START):
        return False
    if result.get("game") != "smb_1_1" or result.get("objective") != "progress":
        return False
    if result.get("deterministic") is not True:
        return False
    try:
        if int(result.get("frame_skip")) != PROTOCOL_FRAME_SKIP:
            return False
        if int(result.get("limit")) != PROTOCOL_LIMIT:
            return False
        if int(result.get("n_actions")) != PROTOCOL_ACTIONS:
            return False
        attempts = int(result.get("attempts") or 0)
        successes = int(result.get("successes") or 0)
        rate = float(result.get("success_rate"))
    except (TypeError, ValueError):
        return False
    if attempts != PROTOCOL_ATTEMPTS or successes < 0 or successes > attempts:
        return False
    if abs(rate - (successes / attempts)) > 1e-9 or not 0.0 <= rate <= 1.0:
        return False
    episodes = result.get("episodes")
    if not isinstance(episodes, list) or len(episodes) != attempts:
        return False
    for episode in episodes:
        if not isinstance(episode, dict):
            return False
        if episode.get("failed"):
            continue
        milestones = episode.get("milestones")
        if not isinstance(milestones, dict):
            return False
        if expected_benchmark in BENCHMARKS:
            for name in BENCHMARKS:
                if name not in milestones:
                    return False
        claimed = bool(milestones.get(expected_benchmark))
        if claimed and not _position_supports(episode, expected_benchmark):
            return False
        if bool(episode.get("success")) != claimed:
            return False
    if _counted_successes(episodes, expected_benchmark) != successes:
        return False
    rom = result.get("rom_sha1")
    core = result.get("core_sha1")
    if not isinstance(rom, str) or not rom or not isinstance(core, str) or not core:
        return False
    if result.get("checkpoint_sha256") != checkpoint_sha256(zip_path):
        return False
    return True


def play_loaded(model, *, seed: int, limit: int = PROTOCOL_LIMIT, benchmark: str = DEFAULT_BENCHMARK) -> dict:
    """One life on the env the loaded policy is attached to. No tape and no hint.

    Recurrent policies keep the hidden state returned by predict. episode_start
    is True on the first decision of the life and False after that. The life
    ends when the env says so, so the next attempt starts from begin_life again.
    """
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
    frames = 0
    reached = update_milestones(blank_milestones(), reset_info)
    memory = begin_life(int(getattr(vec, "num_envs", 1) or 1))
    for _ in range(int(limit)):
        action, memory = decide(model, observation, memory)
        observation, _reward, dones, infos = vec.step(action)
        info = dict(infos[0] or {})
        if info.get("forced") or info.get("assisted"):
            raise EvalIsolationError("step was forced")
        frames += 1
        last = info
        reached = update_milestones(reached, info)
        if bool(dones[0]):
            break
    return _episode_from_trace(last, reached, frames, benchmark)


def run_checkpoint(
    checkpoint: Path,
    model: str,
    attempts: int,
    seed: int,
    limit: int = PROTOCOL_LIMIT,
    benchmark: str = DEFAULT_BENCHMARK,
) -> dict:
    """Load weights into a fresh game. A missing ROM or torch is a failed evaluation."""
    checkpoint = Path(checkpoint)
    identity: dict = {
        "model": model,
        "seed": int(seed),
        "limit": int(limit),
        "benchmark": benchmark,
        "start": GAME_START,
        "deterministic": True,
        "game": "smb_1_1",
        "objective": "progress",
    }
    try:
        identity["checkpoint_sha256"] = checkpoint_sha256(checkpoint)
    except OSError as exc:
        return failed_evaluation(str(exc), identity)
    if benchmark not in BENCHMARKS:
        return failed_evaluation(f"unknown benchmark {benchmark}", identity)
    try:
        import hashlib
        from games.lab.cores import ensure_core
        from games.lab.env import make_env
        from games.lab.integrations.smb_1_1 import INTEGRATION
        from games.lab.models import registry
        from games.lab.roms import SMB_SHA1, pinned_smb
        rom = pinned_smb()
        if rom is None:
            return failed_evaluation("ROM is missing", identity)
        core = ensure_core("nes")
        identity["rom_sha1"] = SMB_SHA1
        identity["core_sha1"] = hashlib.sha1(core.read_bytes()).hexdigest()
        identity["objective"] = INTEGRATION.objective
        identity["n_actions"] = len(INTEGRATION.actions)
        env = make_env("nes", rom, INTEGRATION)
        identity["frame_skip"] = int(getattr(env.unwrapped, "frame_skip", 0) or 0)
        if identity["frame_skip"] != PROTOCOL_FRAME_SKIP or identity["n_actions"] != PROTOCOL_ACTIONS:
            env.close()
            return failed_evaluation("environment does not match the protocol", identity)
        loaded = registry.load(model, str(checkpoint), env)
        try:
            return evaluate_attempts(
                lambda one_seed: play_loaded(loaded, seed=one_seed, limit=limit, benchmark=benchmark),
                attempts,
                identity,
            )
        finally:
            env.close()
    except Exception as exc:
        return failed_evaluation(f"{type(exc).__name__}: {exc}", identity)


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Evaluate a checkpoint with no tape and no hints")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--attempts", type=int, default=PROTOCOL_ATTEMPTS)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--limit", type=int, default=PROTOCOL_LIMIT)
    parser.add_argument("--benchmark", default=DEFAULT_BENCHMARK)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    result = run_checkpoint(
        Path(args.checkpoint),
        args.model,
        args.attempts,
        args.seed,
        args.limit,
        args.benchmark,
    )
    if args.out:
        write_eval(Path(args.out), result)
    print(json.dumps(result))
    return 2 if result.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
