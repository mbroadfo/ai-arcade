"""Versioned game-adapter contract. The engine calls this. It does not name a game.

An adapter supplies identity, capabilities, controls, observations, rewards, and
the comparison its benchmarks use. Savestates, RAM inspection, and frame-accurate
input are capabilities. An adapter that lacks one says so, and the engine skips
that operation.
"""
from __future__ import annotations

CONTRACT_VERSION = 1
SENSES = ("maximize", "minimize")

# A bootable title with no adapter is scored by how long it survives.
SURVIVAL_SENSE = "maximize"


def capabilities_of(adapter) -> dict:
    """The operations this adapter actually supports."""
    raw = getattr(adapter, "capabilities", None)
    raw = dict(raw) if isinstance(raw, dict) else {}
    return {
        "contract": int(raw.get("contract") or CONTRACT_VERSION),
        "pixels": bool(raw.get("pixels")),
        "ram": bool(raw.get("ram")),
        "savestate": bool(raw.get("savestate")),
        "frame_accurate": bool(raw.get("frame_accurate")),
        "structured": bool(raw.get("structured")),
    }


def require_sense(sense: str) -> str:
    if sense not in SENSES:
        raise ValueError("an adapter must say whether its metric is maximize or minimize")
    return sense


def sense_of(adapter) -> str | None:
    """Comparison direction declared by the adapter or its protocol."""
    if adapter is None:
        return None
    named = getattr(adapter, "sense", None)
    if named in SENSES:
        return named
    protocol_of = getattr(adapter, "evaluation_protocol", None)
    if not callable(protocol_of):
        return None
    try:
        protocol = protocol_of()
    except Exception:
        return None
    if isinstance(protocol, dict) and protocol.get("sense") in SENSES:
        return protocol["sense"]
    return None


def better(sense: str, challenger, incumbent) -> bool:
    """True when challenger beats incumbent on this metric."""
    require_sense(sense)
    if sense == "minimize":
        return challenger < incumbent
    return challenger > incumbent


def training_prefers(sense: str, score: int, seat: int, best: dict | None) -> bool:
    """Tie break is the lower seat. The sense decides which score wins."""
    if best is None:
        return True
    require_sense(sense)
    current = int(best["score"])
    if score != current:
        return better(sense, score, current)
    return seat < int(best["seat"])


def ordered(sense: str, value, seat: int) -> tuple:
    """A key for max(). The better outcome sorts last. The lower seat wins a tie."""
    require_sense(sense)
    if sense == "minimize":
        return (-value, -seat)
    return (value, -seat)


def open_experiment(adapter):
    """Bind one adapter to a fresh environment. This does not train."""
    if adapter is None or not getattr(adapter, "id", None):
        raise ValueError("an experiment needs an adapter")
    protocol_of = getattr(adapter, "evaluation_protocol", None)
    if not callable(protocol_of):
        raise ValueError("the adapter has no evaluation protocol")
    protocol = protocol_of()
    if not isinstance(protocol, dict) or not protocol.get("name"):
        raise ValueError("the protocol has no name")
    require_sense(protocol.get("sense"))
    open_env = getattr(adapter, "open_env", None)
    if not callable(open_env):
        raise ValueError("the adapter cannot open an environment")
    return {
        "adapter": adapter.id,
        "runtime": getattr(adapter, "system", None),
        "protocol": protocol,
        "capabilities": capabilities_of(adapter),
        "env": open_env(),
    }
