#!/usr/bin/env python3
"""Move arcade games to standalone MAME 0.251 (human mode) one at a time, each only after it passes a check.

The ledger (/opt/retropie/configs/mame-0251/ledger.json) holds every arcade zip and where it stands:

    pending      planned: plays in MAME 0.251 as it is ("as-is") or once rebuilt from the collection ("rebuild")
    checked      the automatic check ran: see "check" (launch, coin, start, Escape, speed, screenshots)
    converted    approved after the check (screenshots looked at): EmulationStation now runs it in MAME 0.251
    kept         stays on the emulator it had, with the reason (missing files, failed check, ...)

Commands:
    plan PLAN.json            add games to the ledger (zip -> {"plan": "as-is"|"rebuild", "set": name})
    run [--batch N]           rebuild (if needed) and check the next N pending games
    approve ZIP...            switch these checked games to MAME 0.251
    keep ZIP... --why TEXT    leave these games on their emulator, with the reason
    finish                    pin every game not converted to the emulator it has, then make MAME 0.251 the default
    revert ZIP...             put converted games back on the emulator they had
    status                    counts, and the games waiting for a decision
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rebuild_set  # noqa: E402

CONFIG = Path("/opt/retropie/configs/mame-0251")
LEDGER = CONFIG / "ledger.json"
SETS = CONFIG / "sets.tsv"
CHECKS = CONFIG / "checks"
ARCADE_CFG = Path("/opt/retropie/configs/arcade/emulators.cfg")
GAMES_CFG = Path("/opt/retropie/configs/all/emulators.cfg")
EMULATOR = "mame-0.251"
SLOW_BOOT = 45  # seconds of start-up for the recheck of games that fail the normal check
LAUNCH = f'{EMULATOR} = "{HERE}/mame_human.sh %BASENAME%"'
LINE = re.compile(r'^\s*([^=\s]+)\s*=\s*"(.*)"\s*$')


def load():
    return json.loads(LEDGER.read_text()) if LEDGER.exists() else {}


def save(ledger):
    tmp = LEDGER.with_suffix(".tmp")
    tmp.write_text(json.dumps(ledger, indent=1, sort_keys=True))
    tmp.replace(LEDGER)


def read_cfg(path):
    if not path.exists():
        return []
    return [(m.group(1), m.group(2)) for m in map(LINE.match, path.read_text().splitlines()) if m]


def write_cfg(path, pairs):
    path.write_text("".join(f'{k} = "{v}"\n' for k, v in pairs))


def set_game(zip_name, emulator):
    """Set (or with None, remove) a game's own emulator choice in RetroPie's per-game file."""
    key = f"arcade_{zip_name}"
    pairs = [(k, v) for k, v in read_cfg(GAMES_CFG) if k != key]
    if emulator:
        pairs.append((key, emulator))
    write_cfg(GAMES_CFG, pairs)


def current(zip_name):
    """The emulator EmulationStation uses for this game now, and whether that is the game's own choice."""
    own = dict(read_cfg(GAMES_CFG)).get(f"arcade_{zip_name}")
    return (own, True) if own else (dict(read_cfg(ARCADE_CFG)).get("default"), False)


def register():
    """Offer MAME 0.251 among the arcade emulators (idempotent); the default is left alone."""
    lines = ARCADE_CFG.read_text().splitlines()
    lines = [l for l in lines if not l.startswith(f"{EMULATOR} =")]
    ARCADE_CFG.write_text("\n".join(lines + [LAUNCH]) + "\n")


def map_set(zip_name, set_name):
    rows = {}
    if SETS.exists():
        rows = dict(l.split("\t", 1) for l in SETS.read_text().splitlines() if "\t" in l)
    if set_name == zip_name:
        rows.pop(zip_name, None)
    else:
        rows[zip_name] = set_name
    SETS.write_text("".join(f"{k}\t{v}\n" for k, v in sorted(rows.items())))


def cmd_plan(args, ledger):
    plan = json.loads(Path(args.file).read_text())
    added = 0
    for zip_name, entry in plan.items():
        if zip_name not in ledger:
            ledger[zip_name] = {"plan": entry["plan"], "set": entry["set"], "status": "pending"}
            added += 1
    save(ledger)
    print(f"{added} games added; {len(ledger)} in the ledger")


def cmd_run(args, ledger):
    register()
    pending = [z for z in sorted(ledger) if ledger[z]["status"] == "pending"][:args.batch]
    if not pending:
        print("nothing pending")
        return
    ready = []
    pool = None
    for z in pending:
        entry = ledger[z]
        if entry["plan"] == "rebuild":
            if pool is None:
                pool = rebuild_set.index(rebuild_set.SOURCE)
            built = rebuild_set.build(entry["set"], pool, rebuild_set.SOURCE, rebuild_set.DEST)
            entry["rebuild"] = built
            if not built["ok"]:
                entry.update(status="kept", why=f"rebuild failed: {built['why']}", at=time.strftime("%F %T"))
                print(f"{z}: kept ({entry['why']})")
                continue
        map_set(z, entry["set"])
        ready.append(z)
    save(ledger)
    if not ready:
        return
    out = CHECKS / time.strftime("%Y%m%d-%H%M%S")
    def check(games, folder, extra=()):
        p = subprocess.run([sys.executable, str(HERE / "game_check.py"), "--out", str(folder), *extra] + games,
                           capture_output=True, text=True)
        found = {json.loads(l)["game"]: json.loads(l) for l in p.stdout.splitlines() if l.startswith("{")}
        for game, r in found.items():
            r["folder"] = str(folder / game)
        return p, found

    # Normal mode (10 s start-up) for the batch; whatever fails is checked again in slow mode, for games whose
    # first-run set-up or power-on test takes longer.
    proc, results = check(ready, out)
    slow = [z for z in ready if z in results and not results[z]["auto_pass"]]
    if slow:
        _, again = check(slow, out.with_name(out.name + "-slow"), ("--boot-seconds", str(SLOW_BOOT)))
        for z, r in again.items():
            r["slow_recheck"] = True
            results[z] = r
    for z in ready:
        r = results.get(z)
        entry = ledger[z]
        if r is None:
            entry.update(status="pending", last_error=proc.stderr[-500:])
            continue
        entry.update(status="checked", check=r, at=time.strftime("%F %T"))
        flag = ("auto-pass" if r["auto_pass"] else "needs a look") + (" (slow recheck)" if r.get("slow_recheck") else "")
        print(f"{z} ({entry['set']}): {flag}  speed {r['speed']}  coin {r['coin_reached_game']}  "
              f"start {r['start_reached_game']}  escape {r['quit_on_escape']}")
    save(ledger)


def cmd_approve(args, ledger):
    for z in args.zips:
        entry = ledger[z]
        if entry["status"] != "checked":
            print(f"{z}: is {entry['status']}, not checked; skipped")
            continue
        emulator, own = current(z)
        entry["previous"] = {"emulator": emulator, "own_choice": own}
        set_game(z, EMULATOR)
        entry.update(status="converted", at=time.strftime("%F %T"))
        print(f"{z}: now {EMULATOR} (was {emulator}{'' if own else ', the default'})")
    save(ledger)


def cmd_keep(args, ledger):
    for z in args.zips:
        ledger[z].update(status="kept", why=args.why, at=time.strftime("%F %T"))
        print(f"{z}: kept ({args.why})")
    save(ledger)


def cmd_revert(args, ledger):
    for z in args.zips:
        entry = ledger[z]
        prev = entry.get("previous")
        if entry["status"] != "converted" or not prev:
            print(f"{z}: not converted; skipped")
            continue
        set_game(z, prev["emulator"] if prev["own_choice"] else None)
        entry.update(status="kept", why="reverted", at=time.strftime("%F %T"))
        print(f"{z}: back on {prev['emulator']}")
    save(ledger)


def cmd_finish(args, ledger):
    games = sorted(p.stem for p in rebuild_set.SOURCE.glob("*.zip"))
    default = dict(read_cfg(ARCADE_CFG)).get("default")
    pinned = 0
    for z in games:
        if ledger.get(z, {}).get("status") == "converted":
            continue
        emulator, own = current(z)
        if not own:
            set_game(z, emulator)
            pinned += 1
    lines = [l for l in ARCADE_CFG.read_text().splitlines() if not l.startswith("default")]
    ARCADE_CFG.write_text("\n".join(lines + [f'default = "{EMULATOR}"']) + "\n")
    print(f"{pinned} games pinned to {default} (their previous default); arcade default is now {EMULATOR}")


def cmd_status(args, ledger):
    counts = {}
    for entry in ledger.values():
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    print(json.dumps(counts))
    for z in sorted(ledger):
        e = ledger[z]
        if e["status"] == "checked":
            c = e["check"]
            print(f"  {z} ({e['set']}): {'auto-pass' if c['auto_pass'] else 'needs a look'} {c['folder']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan").add_argument("file")
    sub.add_parser("run").add_argument("--batch", type=int, default=10)
    sub.add_parser("approve").add_argument("zips", nargs="+")
    keep = sub.add_parser("keep")
    keep.add_argument("zips", nargs="+")
    keep.add_argument("--why", required=True)
    sub.add_parser("revert").add_argument("zips", nargs="+")
    sub.add_parser("finish")
    sub.add_parser("status")
    args = parser.parse_args()
    CONFIG.mkdir(parents=True, exist_ok=True)
    ledger = load()
    globals()[f"cmd_{args.cmd}"](args, ledger)
    return 0


if __name__ == "__main__":
    sys.exit(main())
