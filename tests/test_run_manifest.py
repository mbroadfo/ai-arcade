import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from arcadekit.manifest import SWITCHES, build_manifest, model_digest


def args(**kw):
    base = dict(game="arcade/pacman", host="pi", decider="rule", strategist="code", knowledge="L2", goal="auto",
                revise=False, no_reflex=False, chain=2, lookahead=None, park=True, refuge=False, min_confidence=0.0,
                seed=7, games=3, seconds=900, tag="t", model="nimble", strategist_model="nimble",
                ollama_host="http://127.0.0.1:9")
    base.update(kw)
    return argparse.Namespace(**base)


def test_the_manifest_names_the_code_the_game_the_decider_and_every_switch():
    m = build_manifest(args(), "label-1")
    assert m["label"] == "label-1" and m["game"] == "arcade/pacman" and m["decider"] == "rule"
    assert m["git"]["sha"] and len(m["git"]["sha"]) == 40 and isinstance(m["git"]["dirty"], bool)
    assert set(m["switches"]) == set(SWITCHES) and m["switches"]["park"] is True and m["switches"]["chain"] == 2
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
    server.shutdown()
