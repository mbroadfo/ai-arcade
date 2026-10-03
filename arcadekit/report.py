"""The run summary tools/play.py prints, the same for every game; the game adds its own metrics and lines."""
import statistics


def summary_lines(player, results, broker=None, metrics=(), extra_lines=()):
    """player: the game's player (stats, ledger, latencies, sources, strategy). results: the finished games' records.
    metrics: the game's (key, about) to print per game. extra_lines: lines only the game knows how to make."""
    lines, s = [], getattr(player, "stats", {})
    if s:
        lines.append(f"decisions: {s.get('on_time', 0)} on time, {s.get('late_rule', 0)} late (rule filled in), "
                     f"{s.get('late_keep', 0)} late (kept going or waited), {s.get('queries', 0)} queries "
                     f"({s.get('chained', 0)} chained), {s.get('revised', 0)} stale answers revised; "
                     f"late because {s.get('late_why', {})}; sources {getattr(player, 'sources', {})}"
                     + (f"; queue {s['queue']}" if s.get("queue") else ""))
    if hasattr(player, "ledger"):
        lines.append(player.ledger.summary())
    strategy = getattr(player, "strategy", None)
    if hasattr(strategy, "stats"):
        lines.append(f"strategist: {strategy.stats}; asked {strategy.strategist.stats}")
    latencies = getattr(player, "latencies", [])
    if latencies:
        lines.append(f"model latency: median {statistics.median(latencies):.0f} ms, max {max(latencies):.0f} ms")
    if broker is not None and broker.call_ms:
        lines.append(f"broker calls: {broker.calls}, median {statistics.median(broker.call_ms):.1f} ms")
    if results:
        scores = [r["score"] for r in results]
        lines.append(f"scores: mean {statistics.mean(scores):.0f}, best {max(scores)}, worst {min(scores)}")
        for key in ("boards_cleared",) + tuple(k for k, _ in metrics):
            if key in results[0]:
                lines.append(f"{key}: per game {[r.get(key) for r in results]}")
        if "lives" in results[0]:
            for r in results:
                lines.append(f"game {r['game']} lives (seconds, score earned): "
                             + ", ".join(f"({life['seconds']}, {life['score']})" for life in r["lives"]))
    lines.extend(extra_lines)
    return lines
