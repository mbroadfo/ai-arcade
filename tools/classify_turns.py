"""Record, in each game's own folder, whether its players take turns on one set of controls, only one plays, or both play at
once, from MAME 0.251's own answer (docs/data/turns-probe.json, made by tools/mame_turns_probe.lua).

    python tools/classify_turns.py

Writes "play": "single" | "turns" | "simultaneous" into games/arcade/<rom>/controls.json (merging into a file that is there)
and "mame": [the set the cabinet runs] when it is not the ROM's own name. The framework reads "play": for single and turns
games Player 2's encoder also plays Player 1's controls (panel_profiles.shared_ports); simultaneous games are left alone.
"""
import json
import os

from gamelib import ROOT

PROBE = ROOT / "docs" / "data" / "turns-probe.json"
CATALOG = ROOT / "docs" / "data" / "cabinet-controls-catalog.json"


def main():
    probe = json.loads(PROBE.read_text(encoding="utf-8"))["games"]
    titles = {g["zip"]: (g["title"], g["year"]) for g in json.loads(CATALOG.read_text(encoding="utf-8"))["games"]}
    for rom, r in sorted(probe.items()):
        folder = ROOT / "games" / "arcade" / rom
        path = folder / "controls.json"
        title, year = titles[rom]
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
            "comment": f"{title} ({year}): this game's controls, where they differ from the cabinet's defaults. Read by pi/mame_human/pad_map.py.",
            "roms": [rom]}
        data["play"] = r["play"]
        if r["set"] != rom:
            data["mame"] = [r["set"]]
        os.makedirs(folder, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    counts = {}
    for r in probe.values():
        counts[r["play"]] = counts.get(r["play"], 0) + 1
    print(counts)


if __name__ == "__main__":
    main()
