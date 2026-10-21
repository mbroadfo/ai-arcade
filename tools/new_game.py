"""Put a game on the AI: find the hardware family MAME says it belongs to, start it from a sibling that already has an AI
player when a kit covers the family, and prove it with the kit's own checks.

    python tools/new_game.py arcade/<zip>                 # the game is already on the cabinet (tools/onboard_game.py first)
    python tools/new_game.py arcade/<zip> --dry-run       # report what it would do; write nothing, run nothing on the Pi
    python tools/new_game.py arcade/<zip> --model nimble  # also let the model play one game after the rule-decider control

Steps, each reported:
  1. the game is on the Pi and MAME 0.251 accepts its set; MAME's driver file for it is its family;
  2. a kit covers that family (arcadekit/kits/<kit>/KIT.json lists the driver files it covers), or the report says what is
     missing and which games share the hardware;
  3. games/arcade/<zip>/ is scaffolded from the kit's template game: an __init__.py that binds the kit, a spec.py that is the
     template's spec with only the name changed (what else differs is for the checks to say), and profile.json from MAME
     (tools/game_profile.py). An existing file is never overwritten;
  4. the kit's validation runs against the live game (a PASS/FAIL table);
  5. a short smoke run: one game with the rule decider, which is the labelled control and is never reported as AI play; with
     --model, one game with the model, and the share of moves the model made itself.
A failed check is printed as ASK with the failing lines: that is where a person (or the game's own spec) has to step in.
"""
import argparse
import json
import re
import subprocess
import sys
import time

import paramiko

from board_families import load_kits, parse_machines
from gamelib import DEFAULT_PI_HOST, ROOT, pi_rompath, split_spec
from onboard_game import CONFIGS, PI_ROMS, Report, find_rom_files, sh

TOOLS = ROOT / "tools"


# ---------------------------------------------------------------- pure parts (tested without a Pi)

def short_name(title):
    """MAME's description without its parenthesised notes: "Puck Man (bootleg set 1)" -> "Puck Man"."""
    return re.sub(r"\s*\([^)]*\)", "", title).split(" / ")[0].strip()


def find_kit(source, kits):
    """(kit name, KIT.json) for the kit whose `sources` include this MAME driver file, or (None, None)."""
    for name, kit in kits.items():
        if source in kit["sources"]:
            return name, kit
    return None, None


def render_init(template_text, title, set_name, template, source):
    """The template game's __init__.py with its module docstring replaced: the code binding the kit is what carries over."""
    body = template_text[template_text.index('"""', 3) + 3:]
    doc = (f'"""{title} (MAME set "{set_name}"), put on the AI by tools/new_game.py from {template}: the same hardware\n'
           f'({source}), so it plays with the same kit, bound to its own spec.py."""')
    return doc + body


def render_spec(template, template_title, title, set_name, text_fields):
    """spec.py: the template game's spec with the name changed, and the name changed inside the texts that carry it. Nothing
    else is assumed to differ: the validation says what does."""
    module = f"games.{template.replace('/', '.')}.spec"
    replaced = "\n".join(f"    {f}=BASE.{f}.replace(BASE.name, NAME)," for f in text_fields)
    return (f'"""{title} (MAME set "{set_name}"): {template_title}\'s spec with only the name changed. What differs on this game\n'
            f'is found by the kit\'s validation (tools/new_game.py) and goes here as it is found."""\n'
            f"from dataclasses import replace\n\nfrom {module} import SPEC as BASE\n\n"
            f'NAME = "{short_name(title)}"\n\n'
            f"SPEC = replace(\n    BASE,\n    name=NAME,\n{replaced}\n)\n")


def render_readme(title, set_name, source, kit_name, template, lines, when):
    """README.md for a scaffolded game: what tools/new_game.py did and what it found, as it stood on `when`."""
    return (f"# {title}\n\nMAME set `{set_name}`, hardware {source}. Put on the AI by `tools/new_game.py` from `{template}` "
            f"with the kit `{kit_name}` (`arcadekit/kits/{kit_name}`); its spec.py is the template's with the name changed, plus "
            f"whatever the checks found.\n\n## Onboarding status ({when})\n\n"
            + "\n".join(f"- {l.strip()}" for l in lines) + "\n")


def parse_validation(text):
    """A validation script's output -> {"passed": n, "failed": [labels]}. Lines look like `  [PASS] label detail`."""
    passed, failed = 0, []
    for line in text.splitlines():
        m = re.match(r"\s*\[(PASS|FAIL)\]\s+(.*)", line)
        if m:
            if m.group(1) == "PASS":
                passed += 1
            else:
                failed.append(m.group(2).strip())
    return {"passed": passed, "failed": failed}


def parse_play_summary(text):
    """tools/play.py's summary -> {"scores": [...], "model_share": percent or None, "games": n}."""
    scores = [int(m.group(1)) for m in re.finditer(r"GAME \d+/\d+ over: score=(\d+)", text)]
    share = re.search(r"The model's own: (\d+)%", text)
    return {"scores": scores, "games": len(scores), "model_share": int(share.group(1)) if share else None}


# ---------------------------------------------------------------- the Pi

TIMED_OUT = 124  # the exit code run_tool reports when a step took longer than its allowance
VALIDATE_SECONDS = 240  # a kit's validation takes about two minutes on a game it fits
GAME_SECONDS = {"control": 300, "model": 600}  # one game of Pac-Man-style play lasts two to four minutes


def run_tool(args, timeout):
    """(output, exit code) of a tool run in tools/; a step that exceeds `timeout` is stopped and reports TIMED_OUT."""
    try:
        p = subprocess.run([sys.executable] + [str(a) for a in args], cwd=TOOLS, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout or ""
        return (partial.decode(errors="replace") if isinstance(partial, bytes) else partial), TIMED_OUT
    return p.stdout + p.stderr, p.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("game", help="<system>/<zip name>, e.g. arcade/pacplus")
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    parser.add_argument("--set", help="the MAME set the zip runs as, when it is not the zip's own name")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-validate", action="store_true")
    parser.add_argument("--skip-smoke", action="store_true")
    parser.add_argument("--model", help="after the control run, one game with this model (needs the Ollama server)")
    args = parser.parse_args()
    system, zip_name = split_spec(args.game)
    if system != "arcade":
        print("tools/new_game.py handles arcade games (MAME); other systems have no AI path yet.")
        return 2
    report = Report()
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(args.host, username="pi", timeout=10)
    try:
        print(f"Putting {args.game} on the AI")
        listing, _ = sh(ssh, f"ls -1 {PI_ROMS}/arcade/ 2>/dev/null")
        if not find_rom_files(listing, zip_name, {".zip", ".7z"}):
            report.ask(f"{zip_name}.zip is not on the Pi: copy it to {PI_ROMS}/arcade/ and run tools/onboard_game.py first")
            return finish(report)
        sets, _ = sh(ssh, f"cat {CONFIGS}/mame-0251/sets.tsv 2>/dev/null")
        set_name = args.set or dict(l.split("\t", 1) for l in sets.splitlines() if "\t" in l).get(zip_name, zip_name)
        verify, _ = sh(ssh, f"mame -rompath {pi_rompath('arcade')} -verifyroms {set_name} 2>&1 | grep -E '^romset' | head -1")
        if " is good" not in verify and "best available" not in verify:
            report.ask(f"MAME 0.251 does not accept the set {set_name} ({verify.strip()}): run tools/onboard_game.py first")
            return finish(report)
        report.ok(f"on the Pi, and MAME 0.251 accepts the set {set_name}")
        xml, _ = sh(ssh, f"mame -listxml {set_name}", timeout=120)
        machine = parse_machines(xml, {set_name}).get(set_name)
        title = re.search(r"<description>(.*?)</description>", xml).group(1)
        if machine is None:
            report.ask(f"MAME has no driver data for {set_name}")
            return finish(report)
        source = machine["source"]
        report.ok(f"{title}: MAME driver {source} ({', '.join(machine['cpus'])})")
        kits = load_kits()
        kit_name, kit = find_kit(source, kits)
        if kit is None:
            siblings = json.loads((ROOT / "docs" / "data" / "board-families.json").read_text(encoding="utf-8"))["families"]
            same = next((f for f in siblings if f["source"] == source), None)
            others = ", ".join(g["zip"] for g in (same or {}).get("games", []) if g["zip"] != zip_name) or "none on this cabinet"
            report.ask(f"no AI kit covers {source}: the first game on this hardware needs its decoder written (games/README.md, "
                       f"docs/GAME_WORKSHOP.md); siblings that would then follow cheaply: {others}")
            report.note("what can be done now without a kit: python tools/game_profile.py <set>; python tools/discover_state.py <set> "
                        "(score, lives and position memory by experiment)")
            return finish(report)
        template = kit["template"]
        report.ok(f"kit {kit_name} ({kit['genre']}) covers {source}; starting from {template}")
        template_dir = ROOT / "games" / template
        folder = ROOT / "games" / "arcade" / zip_name
        files = {"__init__.py": render_init((template_dir / "__init__.py").read_text(encoding="utf-8"), title, set_name, template, source),
                 "spec.py": render_spec(template, json.loads((template_dir / "profile.json").read_text(encoding="utf-8")).get("description", template),
                                        title, set_name, kit["spec_fields_with_name"])}
        if args.dry_run:
            for name, text in files.items():
                report.note(f"dry run: would write {folder.relative_to(ROOT).as_posix()}/{name}:\n{text}")
            return finish(report, dry_run=True)
        folder.mkdir(parents=True, exist_ok=True)
        for name, text in files.items():
            if (folder / name).exists():
                report.note(f"{name} already exists: left as it is")
            else:
                (folder / name).write_text(text, encoding="utf-8")
                report.ok(f"wrote {folder.relative_to(ROOT).as_posix()}/{name}")
        profile = folder / "profile.json"
        if not profile.exists():
            out, code = run_tool(["game_profile.py", set_name, "--host", args.host], 300)
            made = ROOT / "games" / "arcade" / set_name / "profile.json"
            if code != 0 or not made.exists():
                report.ask("the profile could not be built from MAME:\n" + out[-400:])
                return finish(report)
            data = json.loads(made.read_text(encoding="utf-8"))
            data["cabinet_file"] = zip_name
            profile.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            if made.parent != folder:
                made.unlink()
                made.parent.rmdir()
            report.ok(f"profile.json from MAME (romset {data['romset']}, cabinet file {zip_name})")
        if not args.skip_validate:
            cmd = [a.replace("{game}", args.game) for a in kit["validate"]]
            out, code = run_tool([ROOT / cmd[0]] + cmd[1:] + ["--host", args.host], VALIDATE_SECONDS)
            v = parse_validation(out)
            if code == TIMED_OUT:
                report.ask(f"the kit's validation did not finish in {VALIDATE_SECONDS} s ({v['passed']} checks passed before it stopped): "
                           "the kit probably cannot read this game")
            elif v["failed"]:
                report.ask(f"the kit's validation: {v['passed']} passed, {len(v['failed'])} failed: " + "; ".join(v["failed"]))
            else:
                report.ok(f"the kit's validation: all {v['passed']} checks passed")
        if not args.skip_smoke:
            out, code = run_tool(["start_pi_game.py", "--game", args.game, "--host", args.host], 180)
            if code != 0:
                report.ask("the game would not start for the AI:\n" + out[-400:])
            else:
                runs = [("rule decider (the labelled control, not AI play)", ["--decider", "rule", "--games", "1"])]
                if args.model:
                    runs.append((f"model {args.model}", ["--decider", "ollama", "--model", args.model, "--knowledge", "L2", "--games", "1"]))
                for label, extra in runs:
                    seconds = GAME_SECONDS["model" if "ollama" in extra else "control"]
                    out, code = run_tool(["play.py", "--game", args.game, "--host", args.host, "--observatory", "none"] + extra, seconds)
                    s = parse_play_summary(out)
                    if code == TIMED_OUT:
                        report.ask(f"{label}: one game did not end in {seconds} s, so the shared player is not playing this game "
                                   "(it is stopped): the kit does not fit it, or the game needs its own rules")
                        break
                    if code != 0 or not s["scores"]:
                        report.ask(f"{label}: the player failed:\n" + out[-500:])
                    else:
                        share = f"; the model made {s['model_share']}% of the moves" if s["model_share"] is not None else ""
                        report.ok(f"{label}: scored {s['scores']}{share}")
        readme = folder / "README.md"
        if not readme.exists():
            readme.write_text(render_readme(title, set_name, source, kit_name, template,
                                            [re.sub(r"^\s*(ok|note|ASK)\s+", lambda m: ("" if m.group(1) == "ok" else m.group(1) + ": "), l, flags=re.M)
                                             for l in report.lines], time.strftime("%d %B %Y")), encoding="utf-8")
    finally:
        sh(ssh, "pkill -x mame; pkill -f '[s]tate_server.py'; pkill -f '[f]rame_server.py'; sudo systemctl restart getty@tty1")
        ssh.close()
    return finish(report)


def finish(report, dry_run=False):
    report.show()
    if report.asks:
        print(f"\n{report.asks} item(s) need a person (ASK above).")
    elif dry_run:
        print("\nDry run: nothing was written. Run without --dry-run to scaffold and check it.")
    else:
        print("\nOn the AI. It appears in the Observatory's AI list by itself (games/<system>/<name>/ with a profile and a player).")
    return 1 if report.asks else 0


if __name__ == "__main__":
    sys.exit(main())
