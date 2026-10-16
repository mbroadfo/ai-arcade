"""Read-only: what controls each arcade game on the cabinet needs (MAME 0.251's own input descriptions) and which
emulator launches it. Writes docs/data/cabinet-controls-catalog.json; docs/CABINET_CONTROLS.md summarises it.

    python tools/catalog_controls.py
"""
import collections
import json
import os
import xml.etree.ElementTree as ET

import paramiko

from gamelib import DEFAULT_PI_HOST, ROOT

OUT = str(ROOT / "docs" / "data" / "cabinet-controls-catalog.json")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
s = paramiko.SSHClient()
s.load_system_host_keys()
s.set_missing_host_key_policy(paramiko.RejectPolicy())
s.connect(DEFAULT_PI_HOST, username="pi", timeout=10)


def sh(cmd, t=300):
    i, o, e = s.exec_command(cmd, timeout=t)
    return o.read().decode(errors="replace")


stems = [x[:-4] for x in sh("ls /home/pi/RetroPie/roms/arcade").split() if x.endswith(".zip")]
emulators = {}
for line in sh("cat /opt/retropie/configs/all/emulators.cfg").splitlines():
    if line.startswith("arcade_") and "=" in line:
        k, v = line.split("=", 1)
        emulators[k.strip()[7:]] = v.strip().strip('"')
default = "mame-0.251"
sets = dict(l.split("\t")[:2] for l in sh("cat /opt/retropie/configs/mame-0251/sets.tsv").splitlines() if "\t" in l)
names = sorted({sets.get(x, x) for x in stems})
xml = sh("mame -listxml " + " ".join(names), t=600)
root = ET.fromstring(xml[xml.index("<mame"):] if "<mame" in xml else xml)
known = {}
for m in root.iter("machine"):
    inp = m.find("input")
    controls = []
    if inp is not None:
        for c in inp.findall("control"):
            controls.append({k: c.get(k) for k in ("type", "player", "buttons", "ways") if c.get(k)})
    known[m.get("name")] = {"title": m.findtext("description"), "year": m.findtext("year"),
                            "players": int(inp.get("players", 0)) if inp is not None else 0,
                            "coins": int(inp.get("coins", 0)) if inp is not None else 0,
                            "controls": controls}
rows = []
for stem in stems:
    name = sets.get(stem, stem)
    info = known.get(name)
    rows.append({"zip": stem, "mame_name": name, "emulator": emulators.get(stem, default),
                 **(info or {"unknown_to_mame_0251": True})})
json.dump({"generated": "2026-10-15", "source": "mame 0.251 -listxml on the Pi; emulators.cfg", "games": rows},
          open(OUT, "w"), indent=1)


def kind(info):
    if not info.get("controls"):
        return "none/unknown"
    types = sorted({(c["type"], c.get("ways")) for c in info["controls"] if c.get("player", "1") == "1"})
    return "+".join(f"{t}{'-' + w if w else ''}" for t, w in types)


tally = collections.Counter(kind(r) for r in rows)
print(len(rows), "arcade zips;", sum(1 for r in rows if r.get("unknown_to_mame_0251")), "unknown to 0.251")
for k, n in tally.most_common():
    print(f"{n:4d}  {k}")
print("players:", dict(collections.Counter(r.get("players") for r in rows)))
btn = collections.Counter(max([int(c.get("buttons", 0)) for c in r.get("controls", [])] or [0]) for r in rows)
print("max buttons on a control:", sorted(btn.items()))
print("emulators:", dict(collections.Counter(r["emulator"] for r in rows)))
