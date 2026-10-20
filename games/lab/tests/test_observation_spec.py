"""A declared observation is a checked document. No game module is imported."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from games.lab import observations
from games.lab.observations import (
    body_parameters,
    require_spec,
    spec_digest,
    value_parameters,
    vector_length,
)


def _sample() -> dict:
    return {
        "id": "declared-v1",
        "dtype": "float32",
        "shape": [4],
        "low": -1.0,
        "high": 1.0,
        "layout": {"kept": True},
    }


def test_require_spec_checks_the_document_and_keeps_extra_fields():
    checked = require_spec(_sample())
    assert checked["id"] == "declared-v1"
    assert checked["dtype"] == "float32"
    assert checked["shape"] == [4]
    assert checked["low"] == -1.0
    assert checked["high"] == 1.0
    assert checked["layout"] == {"kept": True}
    assert vector_length(checked) == 4
    assert require_spec(checked) == checked


def test_require_spec_rejects_a_bad_document():
    base = _sample()
    rejected = [
        {},
        {**base, "id": ""},
        {**base, "id": "  "},
        {**base, "dtype": "float64"},
        {**base, "shape": [4, 1]},
        {**base, "shape": []},
        {**base, "shape": [0]},
        {**base, "shape": [-1]},
        {**base, "shape": 4},
        {**base, "shape": [True]},
        {**base, "low": 1.0, "high": -1.0},
        {**base, "low": 1.0, "high": 1.0},
        {**base, "low": "low"},
        {**base, "low": True},
    ]
    for spec in rejected:
        with pytest.raises(ValueError):
            require_spec(spec)


def test_digest_is_stable_and_changes_when_a_field_changes():
    checked = require_spec(_sample())
    assert spec_digest(checked) == spec_digest(_sample())
    text = json.dumps(checked, sort_keys=True, separators=(",", ":"))
    assert "-1.0" in text
    changed = _sample()
    changed["high"] = 2
    assert spec_digest(changed) != spec_digest(checked)
    layout = _sample()
    layout["layout"] = {"kept": False}
    assert spec_digest(layout) != spec_digest(checked)


def test_parameter_counts_follow_the_hidden_layer_formula():
    assert body_parameters(80) == 1500
    assert value_parameters(80) == 1313
    assert body_parameters(110) == 1980
    assert value_parameters(110) == 1793
    assert body_parameters(4, hidden=2, outputs=3) == (4 + 1) * 2 + (2 + 1) * 3
    with pytest.raises(ValueError):
        body_parameters(0)


def test_the_spec_module_does_not_name_a_screen_or_a_game():
    text = Path(observations.__file__).read_text(encoding="utf-8").casefold()
    for word in ("tile", "mario", "goomba"):
        assert word not in text
