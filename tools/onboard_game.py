"""Bring one game onto the cabinet for people to play: check it, work out what is special about its controls, record that in
the game's own folder, and say what is left for a person to decide.

    python tools/onboard_game.py arcade/<rom>              # the ROM is already in the Pi's arcade folder
    python tools/onboard_game.py arcade/<rom> --dry-run    # report only; write nothing
    python tools/onboard_game.py nes/<rom>                 # another system: the basic checks

For an arcade game it:
  1. finds the ROM on the Pi and asks MAME 0.251 whether the set is complete (`--set NAME` when the cabinet's zip has another
     name than the set MAME runs: the answer is kept in sets.tsv, as pi/mame_human/convert.py does);
  2. reads the game's own description from MAME (title, year, players, controls) into the controls catalog;
  3. asks MAME, with a short Lua probe, whether the players take turns or play together, and which coin-slot DIP switches
     exist and what they are set to (one coin for one credit is applied when the factory setting is something else);
  4. runs the same check EmulationStation's launch gets (game_check.py: it starts, a coin and a start reach it, Escape quits);
  5. writes games/arcade/<rom>/controls.json: roms, mame set, pointer (trackball or spinner), play (single, turns,
     simultaneous), dips. Nothing about the game is in the framework.
Then `--install` puts it on the Pi (install_mame_human.py, install_controls.py --apply). Without it, the report says so.

Anything that needs a person is printed as ASK: a set MAME rejects, a failed check, a coin switch with no one-coin setting,
a game that runs in an emulator other than MAME 0.251.
"""
import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import paramiko

from gamelib import DEFAULT_PI_HOST, ROOT, pi_rompath, split_spec
from inventory_pointers import classify

CATALOG = ROOT / "docs" / "data" / "cabinet-controls-catalog.json"
PI_ROMS = "/home/pi/RetroPie/roms"
CONFIGS = "/opt/retropie/configs"
HUMAN = "/home/pi/ai-arcade/mame_human"
PROBE_LUA = ROOT / "tools" / "mame_onboard_probe.lua"
ONE_COIN = re.compile(r"^1 coins?\s*/\s*1 credits?$", re.I)


# ---------------------------------------------------------------- pure parts (tested without a Pi)

def parse_listxml(xml_text, machine):
    """MAME's `-listxml` for one machine -> {title, year, players, coins, controls} like the controls catalog, or None."""
    root = ET.fromstring(xml_text[xml_text.index("<mame"):] if "<mame" in xml_text else xml_text)
    for m in root.iter("machine"):
        if m.get("name") != machine:
            continue
        inp = m.find("input")
        controls = []
        if inp is not None:
            for c in inp.findall("control"):
                controls.append({k: c.get(k) for k in ("type", "player", "buttons", "ways") if c.get(k)})
        return {"title": m.findtext("description"), "year": m.findtext("year"),
                "players": int(inp.get("players", 0)) if inp is not None else 0,
                "coins": int(inp.get("coins", 0)) if inp is not None else 0, "controls": controls}
    return None


def parse_probe(text):
    """The probe's output (mame_onboard_probe.lua) -> {"turns": {...} or None, "coin": [{tag, name, mask, defvalue, settings}]}."""
    turns, coin = None, {}
    for line in text.splitlines():
        if line.startswith("TURNS "):
            f = dict(p.split("=") for p in line.split()[1:])
            turns = {"p2": int(f["p2"]), "cocktail": int(f["cocktail"]), "real": int(f["real"]),
                     "cabinet_dip": f["cabinet_dip"] == "yes", "p3": int(f["p3"])}
        elif line.startswith("COIN "):
            m = re.match(r"COIN tag=(\S+) name=(.+?) mask=(\d+) defvalue=(\d+)$", line)
            if m:
                coin[m.group(2)] = {"tag": m.group(1), "name": m.group(2), "mask": int(m.group(3)),
                                    "defvalue": int(m.group(4)), "settings": {}}
        elif line.startswith("COINSETTING "):
            m = re.match(r"COINSETTING name=(.+?) value=(\d+) label=(.*)$", line)
            if m and m.group(1) in coin:
                coin[m.group(1)]["settings"][int(m.group(2))] = m.group(3).strip()
    return {"turns": turns, "coin": list(coin.values())}


def play_mode(turns, players):
    """single / turns / simultaneous, as tools/classify_turns.py defines them; None when MAME gave no answer."""
    if turns is None:
        return None
    if players == 1:
        return "single"
    return "simultaneous" if turns["real"] > 0 or turns["p3"] > 0 or players > 2 else "turns"


def one_coin_dips(coin_fields):
    """([DIP settings to apply], [notes]) so that one coin buys one credit: only a field whose factory value is something
    else and which offers a "1 Coin/1 Credit" setting gets a dip entry."""
    dips, notes = [], []
    for f in coin_fields:
        want = next((v for v, label in f["settings"].items() if ONE_COIN.match(label)), None)
        if want is None:
            notes.append(f"{f['name']}: no one-coin-one-credit setting ({', '.join(sorted(f['settings'].values()))})")
        elif want != f["defvalue"]:
            dips.append({"tag": f["tag"], "mask": f["mask"], "defvalue": f["defvalue"], "value": want, "name": f["name"]})
    return dips, notes


def merge_controls(existing, rom, set_name, info, pointer, play, dips):
    """The game's controls.json with what onboarding found added. What a person already put there stays."""
    data = dict(existing) if existing else {
        "comment": f"{info['title']} ({info['year']}): this game's controls, where they differ from the cabinet's defaults. "
                   "Read by pi/mame_human/pad_map.py and tools/install_controls.py.",
        "roms": [rom]}
    if set_name != rom:
        data["mame"] = [set_name]
    if pointer:
        data["pointer"] = pointer
    if play:
        data["play"] = play
    if dips:
        data.pop("dip", None)
        data["dips"] = dips
    return data


def update_catalog(catalog, rom, set_name, emulator, info):
    """The controls catalog with this game's entry added or replaced (sorted by ROM name)."""
    row = {"zip": rom, "mame_name": set_name, "emulator": emulator, **info}
    games = [g for g in catalog["games"] if g["zip"] != rom] + [row]
    return {**catalog, "games": sorted(games, key=lambda g: g["zip"])}


def find_rom_files(listing, rom, allowed=None):
    """The files in a system's folder (one name per line) that are this ROM: the same name without the extension (case does
    not matter), and, when the extensions EmulationStation lists for the system are known, one of those (a save state with
    the ROM's name is not the ROM)."""
    found = []
    for name in listing.splitlines():
        p = Path(name)
        if p.stem.lower() == rom.lower() and (allowed is None or p.suffix.lower() in allowed):
            found.append(name)
    return found


def es_extensions(es_systems_text, system):
    """The file extensions EmulationStation lists for a system, from es_systems.cfg."""
    for s in ET.fromstring(es_systems_text).iter("system"):
        if s.findtext("name") == system:
            return set((s.findtext("extension") or "").lower().split())
    return None


# ---------------------------------------------------------------- the Pi

def sh(ssh, command, timeout=300):
    _, out, err = ssh.exec_command(command, timeout=timeout)
    text = out.read().decode(errors="replace") + err.read().decode(errors="replace")
    return text, out.channel.recv_exit_status()


class Report:
    def __init__(self):
        self.lines, self.asks = [], 0

    def ok(self, text):
        self.lines.append(f"  ok    {text}")

    def note(self, text):
        self.lines.append(f"  note  {text}")

    def ask(self, text):
        self.lines.append(f"  ASK   {text}")
        self.asks += 1

    def show(self):
        print("\n".join(self.lines))


def cfg_values(text):
    """RetroPie's `key = "value"` lines -> {key: value}."""
    out = {}
    for line in text.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip().strip('"')
    return out


def effective_emulator(ssh, system, rom):
    """(the emulator EmulationStation uses for this game, whether that is the game's own choice)."""
    own = cfg_values(sh(ssh, f"cat {CONFIGS}/all/emulators.cfg 2>/dev/null")[0]).get(f"{system}_{rom}")
    default = cfg_values(sh(ssh, f"cat {CONFIGS}/{system}/emulators.cfg 2>/dev/null")[0]).get("default")
    return (own or default or "unknown"), bool(own)


def basic_checks(ssh, system, rom, report):
    allowed = es_extensions(sh(ssh, "cat /etc/emulationstation/es_systems.cfg")[0], system)
    if allowed is None:
        report.ask(f"EmulationStation has no system called {system}: install its emulator (pi/setup_pi5.sh emulators) first")
        return
    listing, _ = sh(ssh, f"ls -1 {PI_ROMS}/{system}/ 2>/dev/null")
    files = find_rom_files(listing, rom, allowed)
    if not files:
        others = find_rom_files(listing, rom)
        report.ask(f"{rom} is not in {PI_ROMS}/{system}/ as a file EmulationStation lists ({' '.join(sorted(allowed))})"
                   + (f"; the files with that name are {', '.join(others)}" if others else ": copy it there"))
        return
    report.ok(f"on the Pi: {files[0]}; EmulationStation lists {Path(files[0]).suffix.lower()} files for {system}")
    emulator, own = effective_emulator(ssh, system, rom)
    report.ok(f"launches with {emulator}{' (this game' + chr(39) + 's own choice)' if own else ' (the system default)'}")
    report.note(f"controls: the standard layouts apply; per-game changes go in games/{system}/{rom}/controls.json "
                "(retroarch_panel, retroarch_pad, pointer)")


def onboard_arcade(ssh, rom, args, report):
    listing, _ = sh(ssh, f"ls -1 {PI_ROMS}/arcade/ 2>/dev/null")
    files = find_rom_files(listing, rom, {".zip", ".7z"})
    if not files:
        report.ask(f"{rom}.zip is not in {PI_ROMS}/arcade/: copy it there, then run this again")
        return
    report.ok(f"on the Pi: {files[0]}")
    sets, _ = sh(ssh, f"cat {CONFIGS}/mame-0251/sets.tsv 2>/dev/null")
    mapped = dict(l.split("\t", 1) for l in sets.splitlines() if "\t" in l)
    set_name = args.set or mapped.get(rom, rom)
    verify, _ = sh(ssh, f"mame -rompath {pi_rompath('arcade')} -verifyroms {set_name} 2>&1 | grep -E '^romset' | head -1")
    if " is good" not in verify and "best available" not in verify:
        report.ask(f"MAME 0.251 does not accept the ROM set {set_name} ({verify.strip() or 'unknown to MAME'}): add the missing "
                   f"files with tools/add_rom_files.py PATH.zip --sets {set_name}, then run this again")
        return
    report.ok(f"MAME 0.251 accepts the set {set_name}")
    xml, _ = sh(ssh, f"mame -listxml {set_name}", timeout=120)
    info = parse_listxml(xml, set_name)
    if info is None:
        report.ask(f"MAME has no description for {set_name}")
        return
    report.ok(f"{info['title']} ({info['year']}): {info['players']} player(s), controls "
              + ", ".join(sorted({c['type'] for c in info['controls']})))
    device, _ = classify({"controls": info["controls"]})
    pointer = device if device in ("spinner", "trackball") else None
    report.ok(f"pointing device: {pointer}" if pointer else "no trackball or spinner")

    # the probe needs the screen: EmulationStation closes for it and comes back
    sftp = ssh.open_sftp()
    sftp.put(str(PROBE_LUA), "/tmp/mame_onboard_probe.lua")
    sftp.close()
    out, _ = sh(ssh, "pkill -f '[e]mulationstation/emulationstation'; sleep 1; cd /tmp; SDL_AUDIODRIVER=alsa timeout 60 mame "
                     f"-inipath {CONFIGS}/mame-0251 {set_name} -nowindow -skip_gameinfo "
                     "-autoboot_script /tmp/mame_onboard_probe.lua -str 2 2>&1 | grep -E '^(TURNS|COIN)'; true")
    probe = parse_probe(out)
    play = play_mode(probe["turns"], info["players"])
    if play:
        report.ok({"single": "one player", "turns": "the players take turns: either side of the panel can play",
                   "simultaneous": "the players play together: each side keeps its own controls"}[play])
    else:
        report.ask("MAME did not answer whether the players take turns; leaving the controls as they are")
    dips, notes = one_coin_dips(probe["coin"])
    for n in notes:
        report.ask("coins: " + n)
    if dips:
        report.ok("coins: " + "; ".join(f"{d['name']} will be set to one coin, one credit" for d in dips))
    elif not notes:
        report.ok("coins: already one coin for one credit" if probe["coin"] else "coins: no coin-slot switch to set")

    if not args.skip_check:
        check, _ = sh(ssh, f"cd {HUMAN} && python3 game_check.py --out /tmp/onboard-check {rom} 2>&1 | grep '^{{' | tail -1", timeout=240)
        result = json.loads(check) if check.strip().startswith("{") else None
        if result is None:
            report.ask("the launch check did not run")
        elif result.get("auto_pass"):
            report.ok(f"launch check passed: starts, coin and start reach it, Escape quits, speed {result.get('speed')}%")
        else:
            report.ask("the launch check needs a look: " + ", ".join(
                f"{k} {result.get(k)}" for k in ("launched", "coin_reached_game", "start_reached_game", "quit_on_escape", "speed")))
    else:
        report.note("launch check skipped")
    sh(ssh, "sudo systemctl restart getty@tty1")

    emulator, own = effective_emulator(ssh, "arcade", rom)
    if emulator != "mame-0.251":
        report.ask(f"it launches with {emulator}, not MAME 0.251: if the check passed, add \"emulator\": \"mame-0.251\" to its controls.json")
    else:
        report.ok("launches with MAME 0.251 (the arcade default)")

    folder = ROOT / "games" / "arcade" / rom
    path = folder / "controls.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    data = merge_controls(existing, rom, set_name, info, pointer, play, dips)
    catalog = update_catalog(json.loads(CATALOG.read_text(encoding="utf-8")), rom, set_name, emulator, info)
    if args.dry_run:
        report.note(f"dry run: would write {path.relative_to(ROOT)}:\n" + json.dumps(data, indent=2))
        return
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    CATALOG.write_text(json.dumps(catalog, indent=1) + "\n", encoding="utf-8")
    if set_name != rom and mapped.get(rom) != set_name:
        sh(ssh, f"printf '%s\\t%s\\n' {rom} {set_name} >> {CONFIGS}/mame-0251/sets.tsv")
        report.ok(f"sets.tsv on the Pi now maps {rom} to {set_name}")
    report.ok(f"wrote {path.relative_to(ROOT)} and the controls catalog entry")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("game", help="<system>/<rom name>, e.g. arcade/pacman")
    parser.add_argument("--set", help="the MAME set this ROM runs as, when it is not the ROM's own name")
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-check", action="store_true", help="skip the launch check (it closes EmulationStation for about 30 s)")
    parser.add_argument("--install", action="store_true", help="after writing, install onto the Pi")
    args = parser.parse_args()
    system, rom = split_spec(args.game)
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(args.host, username="pi", timeout=10)
    report = Report()
    try:
        print(f"Onboarding {system}/{rom}")
        (onboard_arcade if system == "arcade" else lambda s, r, a, rep: basic_checks(s, system, r, rep))(ssh, rom, args, report)
    finally:
        ssh.close()
    report.show()
    if args.install and not args.dry_run and report.asks == 0:
        for tool in ("install_mame_human.py", "install_controls.py"):
            subprocess.run([sys.executable, str(ROOT / "tools" / tool)] + (["--apply"] if tool == "install_controls.py" else []),
                           cwd=ROOT / "tools", check=False)
    elif report.asks:
        print(f"\n{report.asks} item(s) need a person (ASK above); nothing is installed until they are settled.")
    elif system != "arcade":
        print("\nNothing to write for this system: it is ready (EmulationStation picks the file up the next time it starts).")
    else:
        print("\nNothing left to decide. Put it on the Pi: python tools/install_mame_human.py; "
              "python tools/install_controls.py --apply (or run this again with --install).")
    return 1 if report.asks else 0


if __name__ == "__main__":
    sys.exit(main())
