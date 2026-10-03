"""The benchmark report (benchmark.py's JSON) as a page: scores per question and model, by kind of situation, and the
situations each model got wrong.

    python games/arcade/bzone/scripts/bench_report.py runs/bench-*.json --out report.html
"""
import argparse
import html
import json
import sys

QUESTIONS = {
    "goal": ("Goal", "Picks a sensible goal: missile, evade a shot, search behind, attack a lined-up or turned-away "
                     "enemy (or approach one that can fire back)."),
    "turn": ("Turn", "Told to ATTACK with the enemy 4-90 degrees off the nose: the first tread command turns it toward "
                     "the sights."),
    "duration": ("Duration", "Given a pivot toward the enemy: picks the duration (0.1-3 s) that leaves it closest to the "
                             "sights."),
    "fire": ("Fire", "Fires exactly when the shot would hit, holds when it would miss."),
}
KINDS = ["ahead", "behind", "shot heard", "lined up", "missile"]


def pct(a, b):
    return 0 if not b else round(100 * a / b)


def bar(a, b, best):
    p = pct(a, b)
    return (f'<div class="bar{" best" if best else ""}"><span style="width:{p}%"></span></div>'
            f'<b>{a}/{b}</b><em>{p}%</em>')


def detail(q, s):
    if q == "duration":
        return f'{s["within_one"]}/{s["n"]} within one step'
    if q == "fire":
        return f'fired at {s["hits_fired"]}/{s["hits"]} hits &middot; held {s["misses_held"]}/{s["misses"]} misses'
    return ""


def misses(q, rows, n=4):
    wrong = [r for r in rows if not r["ok"]][:n]
    out = []
    for r in wrong:
        if q == "goal":
            what = f'chose <b>{r["answer"]}</b>, expected {" or ".join(r["expected"])}'
        elif q == "turn":
            what = f'chose <b>{r["answer"]}</b> with the enemy {abs(r["bearing"]):.0f}&deg; ' \
                   f'{"left" if r["bearing"] > 0 else "right"}'
        elif q == "duration":
            what = f'chose <b>{r["answer"]:g} s</b>, best {r["ideal"]:g} s for {abs(r["bearing"]):.0f}&deg;'
        else:
            what = f'chose <b>{r["answer"]}</b> when the shot would {"hit" if r["hits"] else "miss"}'
        out.append(f'<li><span class="kind">{html.escape(r["kind"])}</span>{what}'
                   f'<q>{html.escape(r["text"])}</q></li>')
    return "".join(out) or '<li class="none">No wrong answers.</li>'


def page(report, source):
    models = list(report["models"])
    head = "".join(f"<th>{html.escape(m)}</th>" for m in models)
    rows = []
    for q, (name, about) in QUESTIONS.items():
        scores = {m: report["models"][m]["summary"].get(q) for m in models}
        top = max((s["right"] / s["n"] for s in scores.values() if s and s["n"]), default=0)
        cells = "".join(
            f'<td>{bar(s["right"], s["n"], s["n"] and s["right"] / s["n"] == top)}<small>{detail(q, s)}</small></td>'
            if s else "<td>-</td>" for s in scores.values())
        rows.append(f'<tr><th scope="row">{name}<small>{about}</small></th>{cells}</tr>')
    lat = "".join(f'<td><b>{report["models"][m]["latency_ms_median"]} ms</b><small>median per question &middot; '
                  f'{report["models"][m]["seconds"]} s for the set</small></td>' for m in models)
    rows.append(f'<tr><th scope="row">Speed<small>One choice question, answered by the model server on this PC.'
                f'</small></th>{lat}</tr>')
    kinds = []
    for q, (name, _) in QUESTIONS.items():
        cells = []
        for m in models:
            bk = report["models"][m]["summary"].get(q, {}).get("by_kind", {})
            cells.append("<td>" + " ".join(f'<span class="chip"><i>{k}</i>{bk[k]}</span>' for k in KINDS if k in bk)
                         + "</td>")
        kinds.append(f'<tr><th scope="row">{name}</th>{"".join(cells)}</tr>')
    wrong = []
    for m in models:
        res = report["models"][m]["results"]
        blocks = "".join(f'<div class="wq"><h4>{QUESTIONS[q][0]}</h4><ul>{misses(q, res.get(q, []))}</ul></div>'
                         for q in QUESTIONS)
        wrong.append(f'<section class="wrong"><h3>{html.escape(m)}: wrong answers</h3><div class="wgrid">{blocks}'
                     f'</div></section>')
    kinds_count = " &middot; ".join(f"{report['kinds'].get(k, 0)} {k}" for k in KINDS)
    return TEMPLATE.format(n=report["situations"], kinds=kinds_count, head=head, rows="".join(rows),
                           kindrows="".join(kinds), wrong="".join(wrong), source=html.escape(source))


TEMPLATE = """<title>Battlezone S1M Benchmark</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Saira+Condensed:wght@500;700&family=Source+Sans+3:wght@400;600&family=JetBrains+Mono:wght@400;600&display=swap">
<style>
/* layout: one reading column; a score matrix (question x model) first, then breakdowns, then the wrong answers */
:root {{
  --bg: #f3f5f2; --panel: #ffffff; --fg: #18211b; --muted: #5d6b61; --line: #d5ddd6;
  --accent: #1f8a4c; --track: #e3e9e4; --warn: #b4531f;
  --display: "Saira Condensed", "Arial Narrow", sans-serif; --body: "Source Sans 3", "Segoe UI", sans-serif;
  --mono: "JetBrains Mono", Consolas, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #0b100d; --panel: #111a14; --fg: #dfe9e2; --muted: #8fa396; --line: #22312a;
  --accent: #4fd88a; --track: #1c2a22; --warn: #f0965c; color-scheme: dark }} }}
:root[data-theme="dark"] {{ --bg: #0b100d; --panel: #111a14; --fg: #dfe9e2; --muted: #8fa396; --line: #22312a;
  --accent: #4fd88a; --track: #1c2a22; --warn: #f0965c; color-scheme: dark }}
body {{ background: var(--bg); color: var(--fg); font: 16px/1.55 var(--body); }}
.wrap {{ max-width: 1040px; margin: 0 auto; padding-inline: 20px; padding-block: 32px 56px; display: grid; gap: 28px; }}
header {{ display: grid; gap: 8px; }}
.eyebrow {{ font: 600 12px var(--mono); letter-spacing: .14em; text-transform: uppercase; color: var(--accent); }}
h1 {{ font: 700 clamp(30px, 5vw, 46px)/1.05 var(--display); letter-spacing: .01em; margin: 0; text-wrap: balance; }}
h2 {{ font: 700 22px var(--display); letter-spacing: .03em; margin: 0 0 10px; text-transform: uppercase; }}
h3 {{ font: 700 19px var(--display); margin: 0 0 10px; }}
h4 {{ font: 600 12px var(--mono); letter-spacing: .12em; text-transform: uppercase; color: var(--muted); margin: 0 0 6px; }}
p {{ margin: 0; max-width: 68ch; }}
.lede {{ color: var(--muted); }}
.panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 18px; min-width: 0; }}
.scroll {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; min-width: 560px; }}
th, td {{ text-align: left; vertical-align: top; padding: 12px 10px; border-top: 1px solid var(--line); }}
thead th {{ border-top: 0; font: 600 13px var(--mono); color: var(--muted); }}
tbody th {{ font: 700 17px var(--display); width: 34%; }}
th small, td small {{ display: block; font: 400 13px/1.4 var(--body); color: var(--muted); margin-top: 4px; }}
td b {{ font: 600 15px var(--mono); font-variant-numeric: tabular-nums; }}
td em {{ font: 400 13px var(--mono); color: var(--muted); font-style: normal; margin-left: 8px; }}
.bar {{ height: 8px; background: var(--track); border-radius: 4px; overflow: hidden; margin-bottom: 6px; }}
.bar span {{ display: block; height: 100%; background: var(--muted); }}
.bar.best span {{ background: var(--accent); }}
.chip {{ display: inline-flex; gap: 6px; font: 400 13px var(--mono); padding: 2px 8px; border: 1px solid var(--line);
  border-radius: 999px; margin: 0 4px 4px 0; font-variant-numeric: tabular-nums; }}
.chip i {{ font-style: normal; color: var(--muted); }}
.wgrid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; }}
.wq {{ min-width: 0; }}
.wq ul {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }}
.wq li {{ font-size: 14px; border-left: 2px solid var(--warn); padding-left: 10px; }}
.wq li.none {{ border-color: var(--accent); color: var(--muted); }}
.wq q {{ display: block; color: var(--muted); font-size: 13px; margin-top: 2px; quotes: none; }}
.kind {{ font: 600 11px var(--mono); text-transform: uppercase; letter-spacing: .08em; color: var(--muted); margin-right: 6px; }}
.method {{ display: grid; gap: 10px; }}
.method li {{ margin-bottom: 4px; }}
code {{ font: 13px var(--mono); }}
footer {{ font: 13px var(--mono); color: var(--muted); }}
</style>
<div class="wrap">
<header>
  <div class="eyebrow">Battlezone &middot; S1M driver &middot; offline benchmark</div>
  <h1>How well each model answers the driver's questions</h1>
  <p class="lede">{n} fixed moments from lab games ({kinds}). Each of the driver's questions is asked on its own, worded exactly as the driver asks it, and scored against the game's own facts. Higher is better; green marks the better model on each question.</p>
</header>
<section class="panel"><h2>Scores</h2><div class="scroll"><table><thead><tr><th>Question</th>{head}</tr></thead><tbody>{rows}</tbody></table></div></section>
<section class="panel"><h2>By kind of moment</h2><div class="scroll"><table><thead><tr><th>Question</th>{head}</tr></thead><tbody>{kindrows}</tbody></table></div></section>
{wrong}
<section class="panel method"><h2>How it is scored</h2><ul>
  <li><b>Goal</b>: missile &rarr; missile; a shot heard &rarr; evade; enemy behind or out of sight &rarr; search; a shot lined up &rarr; attack; enemy ahead &rarr; attack, or approach while it can fire back.</li>
  <li><b>Turn</b>: under the ATTACK goal, the first tread command must swing the nose toward the enemy.</li>
  <li><b>Duration</b>: the pivot time that leaves the enemy closest to the sights (0.1, 0.25, 0.5, 1, 2 or 3 s); "within one step" accepts the neighbouring choice.</li>
  <li><b>Fire</b>: right when it fires at a shot that would hit and holds a shot that would miss. The gun is taken as ready: the logs do not record it.</li>
  <li>Options are shuffled for every question, as in the game. The benchmark scores the model; it never plays.</li>
</ul></section>
<footer>{source}</footer>
</div>
"""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    report = json.load(open(args.report))
    open(args.out, "w", encoding="utf-8").write(page(report, f"games/arcade/bzone/scripts/benchmark.py &rarr; {args.report}"))
    print(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
