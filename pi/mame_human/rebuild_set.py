#!/usr/bin/env python3
"""Build MAME 0.251 ROM sets from files already in the collection, without touching the originals.

For each set name: ask MAME (-listxml) which ROMs it needs, find each one by checksum in any zip of the source folder
(and of EXTRA: files from newer sets added with tools/add_rom_files.py, which EmulationStation never lists),
and write a self-contained (non-merged) <set>.zip into the destination folder. MAME then verifies it (-verifyroms);
a set that does not verify is deleted again. One JSON line per set.

    python3 rebuild_set.py [--source DIR] [--dest DIR] set [set ...]
"""
import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

SOURCE = Path.home() / "RetroPie/roms/arcade"
DEST = Path.home() / "RetroPie/mame-0251/roms"
EXTRA = Path.home() / "RetroPie/mame-0251/extra"


def index(source, extra=EXTRA):
    """checksum -> (zip, member) for every file in every zip of the source folder, then of the extra folder."""
    pool = {}
    for z in sorted(source.glob("*.zip")) + sorted(extra.glob("*.zip")):
        try:
            with zipfile.ZipFile(z) as f:
                for info in f.infolist():
                    pool.setdefault("%08x" % info.CRC, (z, info.filename))
        except zipfile.BadZipFile:
            pass
    return pool


def needed(name):
    out = subprocess.run(["mame", "-listxml", name], capture_output=True, text=True).stdout
    for m in ET.fromstring(out).iter("machine"):
        if m.get("name") == name:
            return [(r.get("name") or "", r.get("crc"), r.get("optional") == "yes") for r in m.findall("rom")
                    if r.get("crc") and r.get("status") != "nodump"]
    return None


def verify(name, dest, source):
    out = subprocess.run(["mame", "-rompath", f"{dest};{source}", "-verifyroms", name],
                         capture_output=True, text=True).stdout
    return "1 were OK" in out, out.strip().splitlines()[-3:]


def build(name, pool, source, dest):
    roms = needed(name)
    if roms is None:
        return {"set": name, "ok": False, "why": "not a MAME 0.251 set"}
    missing = [n for n, crc, optional in roms if crc not in pool and not optional]
    if missing:
        return {"set": name, "ok": False, "why": "files not in the collection", "missing": missing}
    target = dest / f"{name}.zip"
    partial = dest / f"{name}.zip.partial"
    written = set()
    with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as out:
        for rom_name, crc, _ in roms:
            if crc not in pool or rom_name in written:
                continue
            src, member = pool[crc]
            with zipfile.ZipFile(src) as f:
                out.writestr(rom_name, f.read(member))
            written.add(rom_name)
    partial.replace(target)
    ok, said = verify(name, dest, source)
    if not ok:
        target.unlink()
        return {"set": name, "ok": False, "why": "MAME did not verify the rebuilt zip", "mame_said": said}
    sources = sorted({pool[c][0].stem for _, c, _ in roms if c in pool})
    return {"set": name, "ok": True, "zip": str(target), "files": len(written), "from": sources}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(SOURCE))
    parser.add_argument("--dest", default=str(DEST))
    parser.add_argument("sets", nargs="+")
    args = parser.parse_args()
    source, dest = Path(args.source), Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    pool = index(source)
    for name in args.sets:
        print(json.dumps(build(name, pool, source, dest)), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
