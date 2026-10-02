import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from arcadekit.manifest import build_manifest, model_digest
from games.arcade.pacman import experiment


def args(**kw):
    base = dict(game="arcade/pacman", host="pi", decider="rule", strategist="code", knowledge="L2", goal="auto",
                min_confidence=0.0, seed=7, games=3, seconds=900, tag="t", model="nimble", strategist_model="nimble",
                ollama_host="http://127.0.0.1:9")
    base.update(kw)
    return argparse.Namespace(**base)


def switches(**kw):
    vals = {o.name: o.default for o in experiment.OPTIONS}
    vals.update(kw)
    return vals


def test_the_manifest_names_the_code_the_game_the_decider_and_every_switch_with_its_kind():
    m = build_manifest(args(), "label-1", experiment.OPTIONS, switches(park=True, chain_depth=2))
    assert m["label"] == "label-1" and m["game"] == "arcade/pacman" and m["decider"] == "rule"
    assert m["git"]["sha"] and len(m["git"]["sha"]) == 40 and isinstance(m["git"]["dirty"], bool)
    assert set(m["switches"]) == {o.name for o in experiment.OPTIONS}
    assert m["switches"]["park"] == {"value": True, "kind": "skill"}
    assert m["switches"]["chain_depth"] == {"value": 2, "kind": "timing"}
    assert m["switches"]["reflex"] == {"value": True, "kind": "override"}
    assert (m["seed"], m["games_requested"], m["seconds_cap"], m["knowledge"]) == (7, 3, 900, "L2")
    json.dumps(m)  # it must be writable as it stands


def test_a_rule_run_records_no_model_and_an_unreachable_server_does_not_break_it():
    assert build_manifest(args(), "x")["models"] == {}
    m = build_manifest(args(decider="ollama"), "x")  # nothing listens on port 9
    assert m["models"]["decider"] == {"model": "nimble", "digest": None}


def test_the_models_digest_is_recorded_when_a_server_answers():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"models": [{"name": "nimble:latest", "digest": "abc123"}]}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host = f"http://127.0.0.1:{server.server_port}"
    assert model_digest(host, "nimble") == "abc123" and model_digest(host, "other") is None
    m = build_manifest(args(strategist="ollama", ollama_host=host), "x")
    assert m["models"]["strategist"]["digest"] == "abc123" and m["ollama_host"] == host
    m = build_manifest(args(ollama_host=host), "x", experiment.OPTIONS, switches(danger_query=True, danger_model="nimble"))
    assert m["models"]["danger_model"] == {"model": "nimble", "digest": "abc123"} and m["ollama_host"] == host
    server.shutdown()
