import json

import compare_runs


def write_run(tmp_path, label, manifest, games, events):
    (tmp_path / f"{label}-manifest.json").write_text(json.dumps(dict(manifest, label=label)))
    (tmp_path / f"{label}-games.jsonl").write_text("".join(json.dumps(g) + "\n" for g in games))
    (tmp_path / f"{label}-decisions.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))


def test_runs_are_compared_from_old_and_new_formats(tmp_path, capsys):
    old_events = ([{"event": "move", "by": "model"}] * 3 + [{"event": "move", "by": "reflex-override"}]
                  + [{"event": "late", "why": "in_flight"}, {"event": "decision", "source": "model", "latency_ms": 80}])
    write_run(tmp_path, "a-v13", {"tag": "v13", "decider": "ollama", "knowledge": "L2",
                                  "models": {"decider": {"model": "tev1:0.8b"}},
                                  "switches": {"no_reflex": True, "park": False, "chain": None}},
              [{"score": 1000}, {"score": 3000}], old_events)
    new_events = [{"event": "move", "by": "model", "via": "junction"}, {"event": "move", "by": "code-late", "via": "keep"}]
    write_run(tmp_path, "b-v17", {"tag": "v17", "decider": "rule", "knowledge": None, "emulated_fps": 51.2,
                                  "switches": {"reflex": {"value": False, "kind": "override"},
                                               "late": {"value": "keep", "kind": "override"},
                                               "park": {"value": False, "kind": "skill"}}},
              [{"score": 500}, {"score": 900, "partial": True}], new_events)
    assert compare_runs.main(["v13", "v17", "--runs", str(tmp_path)]) == 0
    out = capsys.readouterr().out.splitlines()
    v13 = next(line for line in out if line.startswith("v13"))
    v17 = next(line for line in out if line.startswith("v17"))
    assert "tev1:0.8b" in v13 and "noreflex" in v13 and "2000" in v13 and "75%" in v13 and "in_flight 1" in v13
    assert "noreflex,late-keep" in v17 and "| 1 " in v17 and "50%" in v17 and "51.2" in v17  # the partial game is left out
