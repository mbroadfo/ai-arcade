"""Independent evaluation of a saved policy.

The shared tape, hints, and any forced button stay out. A training score is a
record of assisted play. It does not, by itself, say the network can do the route.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

EVAL_NAME = "best.eval.json"


class EvalIsolationError(RuntimeError):
    """An evaluation step was scripted. That attempt does not count."""


def checkpoint_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def failed_evaluation(reason: str, identity: dict | None = None) -> dict:
    """An evaluation that did not produce a usable measurement."""
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
    }
    for key in ("rom_sha1", "core_sha1", "checkpoint_sha256", "model", "seed"):
        if identity and identity.get(key) is not None:
            result[key] = identity[key]
    return result


def _furthest(episodes: list[dict]) -> dict | None:
    good = [episode for episode in episodes if not episode.get("failed")]
    if not good:
        return None
    return max(good, key=lambda episode: int(episode.get("score") or 0))


def evaluate_attempts(run_one, attempts: int, identity: dict) -> dict:
    """Run standardized attempts. run_one(seed) plays one life with no assistance.

    identity carries the ROM, the core, and the checkpoint hash. A missing piece,
    or a life that was assisted, is a failed evaluation rather than a score.
    """
    identity = dict(identity or {})
    missing = [
        key for key in ("rom_sha1", "core_sha1", "checkpoint_sha256", "model")
        if not identity.get(key)
    ]
    if missing:
        return failed_evaluation("missing " + ", ".join(missing), identity)
    try:
        attempts = int(attempts)
    except (TypeError, ValueError):
        return failed_evaluation("attempts are not a number", identity)
    if attempts < 1:
        return failed_evaluation("no attempts", identity)
    base = int(identity.get("seed") or 0)
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
        episodes.append({"seed": seed, "failed": False, **episode})
    good = [episode for episode in episodes if not episode.get("failed")]
    if not good:
        result = failed_evaluation("every attempt failed", identity)
        result["attempts"] = attempts
        result["episodes"] = episodes
        result["seeds"] = [base + index for index in range(attempts)]
        return result
    successes = [episode for episode in good if episode.get("success")]
    furthest = _furthest(good)
    frames = [int(episode.get("frames") or 0) for episode in successes]
    return {
        "assisted": False,
        "failed": False,
        "failure": None,
        "attempts": attempts,
        "successes": len(successes),
        "success_rate": len(successes) / attempts,
        "deaths": sum(1 for episode in good if episode.get("dead")),
        "clears": sum(1 for episode in good if episode.get("cleared")),
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
        "rom_sha1": identity["rom_sha1"],
        "core_sha1": identity["core_sha1"],
        "checkpoint_sha256": identity["checkpoint_sha256"],
        "model": identity["model"],
        "seed": base,
        "record": "independent",
    }


def play_unassisted(env, choose, *, seed: int, limit: int = 2000) -> dict:
    """One life. choose(observation) is the policy. A forced step aborts the attempt."""
    _obs, info = env.reset(seed=seed)
    if not independent_episode(info):
        raise EvalIsolationError("reset was assisted")
    last = info
    frames = 0
    success = False
    for _ in range(int(limit)):
        _obs, _reward, terminated, truncated, info = env.step(choose(_obs))
        if info.get("forced") or info.get("assisted"):
            raise EvalIsolationError("step was forced")
        frames += 1
        last = info
        success = success or bool(info.get("success") or info.get("flag_get"))
        if terminated or truncated:
            break
    return {
        "score": int(last.get("score") or 0),
        "world": int(last.get("world") or 1),
        "stage": int(last.get("stage") or 1),
        "x_pos": int(last.get("x_pos") or 0),
        "dead": bool(last.get("dead")),
        "time": int(last.get("time") or 0),
        "cleared": bool(last.get("flag_get") or success),
        "success": bool(success or last.get("flag_get")),
        "frames": frames,
        "forced": False,
        "assisted": False,
        "demonstration_steps": 0,
    }


def compare_independent(before: dict, after: dict) -> dict:
    """Success rates from two finished independent evaluations."""
    for label, item in (("before", before), ("after", after)):
        if not isinstance(item, dict) or item.get("assisted") or item.get("failed"):
            raise ValueError(f"{label} is not a finished independent evaluation")
    before_score = int((before.get("furthest") or {}).get("score") or 0)
    after_score = int((after.get("furthest") or {}).get("score") or 0)
    return {
        "before_success_rate": before["success_rate"],
        "after_success_rate": after["success_rate"],
        "before_furthest": before_score,
        "after_furthest": after_score,
        "attempts": [before["attempts"], after["attempts"]],
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


def accept_eval(result: dict | None, zip_path: Path) -> bool:
    """True when this file is an independent measurement of these exact weights."""
    if not isinstance(result, dict) or result.get("assisted") or result.get("failed"):
        return False
    if result.get("record") not in (None, "independent"):
        return False
    try:
        attempts = int(result.get("attempts") or 0)
        rate = float(result.get("success_rate"))
    except (TypeError, ValueError):
        return False
    if attempts < 1 or not 0.0 <= rate <= 1.0:
        return False
    if result.get("checkpoint_sha256") != checkpoint_sha256(zip_path):
        return False
    return True


def play_loaded(model, *, seed: int, limit: int = 2000) -> dict:
    """One life on the env the loaded policy is attached to. No tape and no hint."""
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
    success = False
    for _ in range(int(limit)):
        action, _state = model.predict(observation, deterministic=True)
        observation, _reward, dones, infos = vec.step(action)
        info = dict(infos[0] or {})
        if info.get("forced") or info.get("assisted"):
            raise EvalIsolationError("step was forced")
        frames += 1
        last = info
        success = success or bool(info.get("success") or info.get("flag_get"))
        if bool(dones[0]):
            break
    return {
        "score": int(last.get("score") or 0),
        "world": int(last.get("world") or 1),
        "stage": int(last.get("stage") or 1),
        "x_pos": int(last.get("x_pos") or 0),
        "dead": bool(last.get("dead")),
        "time": int(last.get("time") or 0),
        "cleared": bool(last.get("flag_get") or success),
        "success": bool(success or last.get("flag_get")),
        "frames": frames,
        "forced": False,
        "assisted": False,
        "demonstration_steps": 0,
    }


def run_checkpoint(checkpoint: Path, model: str, attempts: int, seed: int, limit: int = 2000) -> dict:
    """Load weights into a fresh game. A missing ROM or torch is a failed evaluation."""
    checkpoint = Path(checkpoint)
    identity: dict = {"model": model, "seed": int(seed)}
    try:
        identity["checkpoint_sha256"] = checkpoint_sha256(checkpoint)
    except OSError as exc:
        return failed_evaluation(str(exc), identity)
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
        env = make_env("nes", rom, INTEGRATION)
        loaded = registry.load(model, str(checkpoint), env)
        try:
            return evaluate_attempts(
                lambda one_seed: play_loaded(loaded, seed=one_seed, limit=limit),
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
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    result = run_checkpoint(Path(args.checkpoint), args.model, args.attempts, args.seed, args.limit)
    if args.out:
        write_eval(Path(args.out), result)
    print(json.dumps(result))
    return 2 if result.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())

