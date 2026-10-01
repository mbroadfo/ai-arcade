"""System One client interface: structured state + typed questions in, calibrated choices out.

Real clients (Ollama's /v1/systemone, TypeSafe's Jev) share one request/response shape, so a
decider written against `ask()` works with any of them. MockSystemOne stands in for tests: it sees
the same facts a model would and answers after a realistic delay.
"""
import json
import math
import random
import time
import urllib.request

class SystemOneError(RuntimeError):
    pass


class OllamaSystemOne:
    """POST {host}/v1/systemone (Ollama 0.35+). Request/response per docs.ollama.com/api/systemone."""

    def __init__(self, model="nimble", host="http://localhost:11434", keep_alive="30m", timeout=5.0):
        self.model, self.host, self.keep_alive, self.timeout = model, host.rstrip("/"), keep_alive, timeout

    def ask(self, state, questions, hint=None):
        body = json.dumps({"model": self.model, "state": state, "questions": questions,
                           "keep_alive": self.keep_alive}).encode()
        request = urllib.request.Request(self.host + "/v1/systemone", data=body,
                                         headers={"Content-Type": "application/json"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read())
        except OSError as exc:
            raise SystemOneError(str(exc)) from exc
        return {"answers": data["answers"], "latency_ms": (time.time() - t0) * 1000,
                "usage": data.get("usage")}


class MockSystemOne:
    """Stands in for a real model. Scores options from `hint` (the same facts the text state
    describes) with the game's `scorer(goal, option)`, softmaxes them into probabilities with a
    little noise, and sleeps like a model."""

    def __init__(self, scorer, latency_ms=(90, 500), temperature=0.7, noise=0.15, seed=0):
        self.scorer = scorer
        self.latency_ms, self.temperature, self.noise = latency_ms, temperature, noise
        self.rng = random.Random(seed)

    def ask(self, state, questions, hint=None):
        latency = self.rng.uniform(*self.latency_ms)
        time.sleep(latency / 1000)
        answers = {}
        for name, question in questions.items():
            if question["type"] != "choice":
                raise SystemOneError("mock only answers choice questions")
            options = list(question["criteria"])
            extra = (hint["mods"],) if hint.get("mods") else ()  # the stance, for games that have one
            scores = [self.scorer(hint["goal"], hint["options"][o], *extra) + self.rng.gauss(0, self.noise)
                      for o in options]
            top = max(scores)
            weights = [math.exp((s - top) / self.temperature) for s in scores]
            total = sum(weights)
            probs = {o: w / total for o, w in zip(options, weights)}
            choice = max(probs, key=probs.get)
            answers[name] = {"type": "choice", "choice": choice, "probabilities": probs,
                             "confidence": probs[choice]}
        return {"answers": answers, "latency_ms": latency, "usage": None}
