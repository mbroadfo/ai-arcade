"""Check that the old cabinet's games made it to the new one, and that EmulationStation will list and launch them.
Read-only on both Pis. For every system that has files on the old Pi it checks:

  files       every ROM/disk/BIOS file is on the new Pi with the same size (--hash: the same SHA-256)
  listed      the new es_systems.cfg accepts the file's extension (a file with an extension the system does not list is
              on disk but never shown: Time Trek's .cmd files)
  launch      the emulator the old Pi launched it with exists on the new Pi (after migrate_pi_settings.py's TRANSLATE),
              and its command line is the same (a changed command can leave a file listed but not launchable)
  gamelist    the old Pi's gamelist.xml (names, play counts) exists on the new Pi

    python tools/verify_migration.py [--old 192.168.10.155] [--new ADDRESS] [--system trs-80] [--hash] [--verbose]

Exits 1 when anything is missing or different, so it can run after every migration step.
"""
import argparse
import collections
import posixpath
import sys
import xml.etree.ElementTree as ET

from gamelib import DEFAULT_PI_HOST
from migrate_pi_settings import CONFIGS, TRANSLATE, connect, parse
from probe_mame_input import run

HOME = "/home/pi"
SYSTEM_FILES = ("/etc/emulationstation/es_systems.cfg", f"{CONFIGS}/all/emulationstation/es_systems.cfg")
SKIP_NAMES = {"gamelist.xml", "systeminfo.txt"}  # ES's own files, not games


def listing(ssh, root):
    """{relative path: size} of every file under root."""
    out = run(ssh, f"cd {root} 2>/dev/null && find . -type f -printf '%P\\t%s\\n' || true")
    files = {}
    for line in out.splitlines():
        path, _, size = line.rpartition("\t")
        if path and posixpath.basename(path) not in SKIP_NAMES:
            files[path] = int(size)
    return files


def hashes(ssh, root, paths):
    """{relative path: sha256} for the given files (one remote call per 200)."""
    result = {}
    for i in range(0, len(paths), 200):
        quoted = " ".join("'" + p.replace("'", "'\\''") + "'" for p in paths[i:i + 200])
        for line in run(ssh, f"cd {root} && sha256sum -- {quoted}").splitlines():
            digest, _, path = line.partition("  ")
            result[path] = digest
    return result


def extensions(ssh):
    """{system: set of lower-case extensions ES lists for it}; the later file overrides the earlier."""
    systems = {}
    for path in SYSTEM_FILES:
        text = run(ssh, f"cat {path} 2>/dev/null || true").strip()
        if not text:
            continue
        for node in ET.fromstring(text).iter("system"):
            systems[node.findtext("name")] = {e.lower() for e in (node.findtext("extension") or "").split()}
    return systems


def emulator_lines(ssh, system):
    """(default emulator or None, {emulator name: command line}) from the system's emulators.cfg."""
    pairs = parse(run(ssh, f"cat {CONFIGS}/{system}/emulators.cfg 2>/dev/null || true"))
    return next((v for k, v in pairs if k == "default"), None), {k: v for k, v in pairs if k != "default"}


def per_game(ssh):
    """{system_game: emulator} from configs/all/emulators.cfg."""
    return dict(parse(run(ssh, f"cat {CONFIGS}/all/emulators.cfg 2>/dev/null || true")))


def installed(ssh, command):
    """Whether the launch command's program exists on this Pi (a libretro core id or a PATH name is not checked)."""
    words = command.split()
    if words and words[0].startswith("/"):
        return run(ssh, f"test -e {words[0]} && echo yes || echo no").strip() == "yes"
    return True


def gamelist_paths(ssh, system):
    text = run(ssh, f"cat {HOME}/.emulationstation/gamelists/{system}/gamelist.xml 2>/dev/null || true").strip()
    return [g.findtext("path") for g in ET.fromstring(text).iter("game")] if text else None


def check_system(old, new, system, args, old_ext, new_ext, old_games, new_games):
    """(row, problems, notes) for one system (notes: choices that differ, which may be deliberate), or None when the old Pi has no files for it."""
    root = f"{HOME}/RetroPie/{'BIOS' if system == 'BIOS' else 'roms/' + system}"
    old_files = listing(old, root)
    if not old_files:
        return None
    new_files = listing(new, root)
    bad, notes = [], []
    missing = sorted(set(old_files) - set(new_files))
    differ = sorted(p for p in old_files if p in new_files and old_files[p] != new_files[p])
    if args.hash:
        same_size = sorted(p for p in old_files if p in new_files and p not in differ)
        a, b = hashes(old, root, same_size), hashes(new, root, same_size)
        differ += [p for p in same_size if a.get(p) != b.get(p)]
    bad += [f"file missing on the new Pi: {p}" for p in missing]
    bad += [f"file differs: {p}" for p in differ]
    unlisted, launch = [], 0
    if system != "BIOS":
        accepted = new_ext.get(system)
        ext_of = lambda p: posixpath.splitext(p)[1].lower()  # noqa: E731
        if accepted is None:
            bad.append("the new Pi's EmulationStation has no such system")
        else:
            listed_before = old_ext.get(system, set())
            unlisted = [p for p in old_files if "/" not in p and ext_of(p) in listed_before and ext_of(p) not in accepted]
            if unlisted:
                counts = collections.Counter(ext_of(p) for p in unlisted)
                bad.append("on disk but never listed by ES, extension not accepted on the new Pi: "
                           + ", ".join(f"{e} x{n}" for e, n in counts.items())
                           + f"  (new accepts: {' '.join(sorted(accepted)) or 'nothing'}; old accepted: "
                           + f"{' '.join(sorted(listed_before))})")
        old_default, old_cmds = emulator_lines(old, system)
        new_default, new_cmds = emulator_lines(new, system)
        for name, command in old_cmds.items():
            target = TRANSLATE.get(name, name)
            if target not in new_cmds:
                launch += 1
                bad.append(f"emulator '{name}' (old Pi) is not offered on the new Pi")
            elif target == name and new_cmds[target] != command:
                launch += 1
                bad.append(f"launch command for '{name}' changed:\n        old: {command}\n        new: {new_cmds[target]}")
            elif not installed(new, new_cmds[target]):
                launch += 1
                bad.append(f"emulator '{target}' is offered but its program is not installed on the new Pi")
        if old_default and TRANSLATE.get(old_default, old_default) != new_default:
            notes.append(f"default emulator: old '{old_default}', new '{new_default}'")
        for key, emulator in old_games.items():
            if key.startswith(system + "_") and new_games.get(key) != TRANSLATE.get(emulator, emulator):
                notes.append(f"per-game emulator for {key[len(system) + 1:]}: old '{emulator}', "
                             f"new '{new_games.get(key, 'default')}'")
        listed_old = gamelist_paths(old, system)
        if listed_old is not None and gamelist_paths(new, system) is None:
            bad.append(f"gamelist.xml not carried over ({len(listed_old)} entries: names, play counts)")
    return (system, len(old_files), len(missing), len(differ), len(unlisted), launch), bad, notes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", default="192.168.10.155")
    parser.add_argument("--new", default=DEFAULT_PI_HOST)
    parser.add_argument("--system", action="append", help="only this system (repeat for several)")
    parser.add_argument("--hash", action="store_true", help="compare SHA-256, not just size (slow for big systems)")
    parser.add_argument("--verbose", action="store_true", help="list every problem, not the first few per system")
    args = parser.parse_args()
    old, new = connect(args.old), connect(args.new)
    rows, problems, notes = [], collections.OrderedDict(), collections.OrderedDict()
    try:
        names = [s for s in run(old, f"ls {HOME}/RetroPie/roms").split() if not args.system or s in args.system]
        if not args.system:
            names.append("BIOS")
        old_ext, new_ext = extensions(old), extensions(new)
        old_games, new_games = per_game(old), per_game(new)
        for system in names:
            done = check_system(old, new, system, args, old_ext, new_ext, old_games, new_games)
            if done:
                rows.append(done[0])
                problems[system], notes[system] = done[1], done[2]
    finally:
        old.close()
        new.close()

    print(f"{'system':<18}{'files':>7}{'missing':>9}{'differ':>8}{'unlisted':>10}{'launch':>8}")
    for row in rows:
        system = row[0]
        print(f"{system:<18}{row[1]:>7}{row[2]:>9}{row[3]:>8}{row[4]:>10}{row[5]:>8}" + ("  <--" if problems[system] else ""))
    total = 0
    for system, items in problems.items():
        if not items:
            continue
        shown = items if args.verbose else items[:8]
        print(f"\n{system}:")
        for text in shown:
            print("  - " + text)
        if len(items) > len(shown):
            print(f"  ... and {len(items) - len(shown)} more (--verbose)")
        total += len(items)
    changed = {s: n for s, n in notes.items() if n}
    if changed:
        print("\nNotes (different from the old Pi; fine if deliberate, e.g. a newer emulator):")
        for system, items in changed.items():
            shown = items if args.verbose else items[:3]
            more = f"; ... {len(items) - len(shown)} more (--verbose)" if len(items) > len(shown) else ""
            print(f"  {system}: " + "; ".join(shown) + more)
    if total:
        print(f"\n{total} problem(s) in {sum(1 for v in problems.values() if v)} system(s).")
    else:
        print("\nOK: everything on the old Pi is on the new one, listed and launchable.")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
