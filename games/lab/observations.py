"""Checks a declared observation specification.

Callers read the id, the dtype, the shape, and the value range. Any other
field stays in the document so a change to it changes the digest. This module
does not interpret those fields and does not train.
"""
from __future__ import annotations

import copy
import hashlib
import json


def _number(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"observation spec {label} must be a number")
    return float(value)


def require_spec(spec: dict) -> dict:
    """Return a checked copy. The digest covers this copy, extra fields included."""
    if not isinstance(spec, dict):
        raise ValueError("observation spec must be a dict")
    name = spec.get("id")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("observation spec id must be a non-empty string")
    if spec.get("dtype") != "float32":
        raise ValueError("observation spec dtype must be float32")
    shape = spec.get("shape")
    if isinstance(shape, (str, bytes)) or not isinstance(shape, (list, tuple)) or len(shape) != 1:
        raise ValueError("observation spec shape must have one positive length")
    length = shape[0]
    if isinstance(length, bool) or not isinstance(length, int) or length <= 0:
        raise ValueError("observation spec shape must have one positive length")
    low = _number(spec.get("low"), "low")
    high = _number(spec.get("high"), "high")
    if not low < high:
        raise ValueError("observation spec low must be below high")
    checked = copy.deepcopy(spec)
    checked["id"] = name
    checked["dtype"] = "float32"
    checked["shape"] = [length]
    checked["low"] = low
    checked["high"] = high
    return checked


def vector_length(spec: dict) -> int:
    return int(require_spec(spec)["shape"][0])


def spec_digest(spec: dict) -> str:
    """SHA-256 of the canonical JSON for the checked document.

    Key order is sorted and there is no extra whitespace. ``json.dumps`` writes
    ``-1.0`` for a float low or high, so two machines hash the same string.
    """
    checked = require_spec(spec)
    text = json.dumps(checked, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def body_parameters(n: int, hidden: int = 16, outputs: int = 12) -> int:
    """Weights of one hidden layer plus a linear output, including both biases."""
    length = int(n)
    width = int(hidden)
    outs = int(outputs)
    if length <= 0 or width <= 0 or outs <= 0:
        raise ValueError("parameter counts need positive sizes")
    return (length + 1) * width + (width + 1) * outs


def value_parameters(n: int, hidden: int = 16) -> int:
    """Weights of one hidden layer plus a scalar head, including biases."""
    length = int(n)
    width = int(hidden)
    if length <= 0 or width <= 0:
        raise ValueError("parameter counts need positive sizes")
    return length * width + width + width + 1
