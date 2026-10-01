# ai-arcade's own Ollama

A model server for ai-arcade alone, separate from the Zork observatory project's (`zork-observatory-ollama-1`, port 11434).
Zork pins its engine and measures baselines on it, so ai-arcade does not share its settings; this one is on port **11435**,
which `tools/systemone.py` and `tools/play.py` use by default (override with `ARCADE_OLLAMA_HOST` or `--ollama-host`).

    docker compose -f tools/ollama/compose.yml up -d
    docker compose -f tools/ollama/compose.yml down

## One-time setup: put nimble in its own volume

The model is the project's own GGUF, so it cannot be pulled from the Ollama library; copy it from wherever it already is. From
the Zork volume (read-only), without touching it:

    docker volume create ai-arcade-ollama-models
    docker run --rm -v zork-observatory_ollama:/src:ro -v ai-arcade-ollama-models:/dst alpine sh -c 'set -e; M=models/manifests/registry.ollama.ai/library/nimble; mkdir -p /dst/models/blobs /dst/$M; cp /src/$M/latest /dst/$M/latest; for d in $(grep -o "sha256:[0-9a-f]*" /src/$M/latest | sort -u); do cp /src/models/blobs/sha256-${d#sha256:} /dst/models/blobs/; done'

The first request after a cold start loads 9.5 GB from disk and takes about 40 s; after that it answers in about 95 ms. Each
request asks the server to keep the model loaded for 30 minutes.

## Sharing the GPU

`nimble` takes 8.9 GB of the 12 GB card, so only one of the two servers can have it loaded. If Zork's server holds it, unload
it there (this changes no settings, it only unloads): `curl http://localhost:11434/api/generate -d '{"model":"nimble","keep_alive":0}'`

## What was measured here (1 Oct 2026, RTX 4070 12 GB, Ollama 0.35.0)

- One question takes about 95 ms alone (240 ms seen under other load).
- Concurrent requests are served one at a time: 2, 4, 8 or 12 at once all give about 11-12 answers a second in total, so extra
  client threads do not cut latency. Several questions in one request are slower (about 7 answers a second).
- Ollama's parallel slots exist, but not for this model: the log says "model architecture does not currently support parallel
  requests: architecture=qwen35" (`nimble` is built on that architecture), so `OLLAMA_NUM_PARALLEL=4` changed nothing. Its
  8194-token context is set inside the model, so `OLLAMA_CONTEXT_LENGTH` does not change it either. A dense model, or a later
  Ollama release, may batch requests; this compose file is the place to try that without touching Zork's.
- Budget: about 12 questions a second, roughly 4-5 per junction transition at 2-3 junctions a second.
