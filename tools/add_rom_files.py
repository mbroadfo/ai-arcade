"""Add ROM files from newer MAME sets to the Pi, and build the MAME 0.251 sets they complete.

The zips go to ~/RetroPie/mame-0251/extra, a pool EmulationStation never lists; the cabinet's own zips are not touched.
Each named set is then built from the collection plus that pool by pi/mame_human/rebuild_set.py into
~/RetroPie/mame-0251/roms, where AI mode (gamelib.pi_rompath) and MAME 0.251 in human mode look first, and kept only if
MAME verifies it. A game moves to MAME 0.251 in human mode only through pi/mame_human/convert.py, after its check.

    python tools/add_rom_files.py C:/Users/me/Downloads/bzone.zip --sets bzone
    python tools/add_rom_files.py --sets tempest bwidow          # files already added: just build these sets
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import paramiko

from gamelib import DEFAULT_PI_HOST, ROOT
from probe_mame_input import run

CODE = "/home/pi/ai-arcade/mame_human"
EXTRA = "/home/pi/RetroPie/mame-0251/extra"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("zips", nargs="*", help="zip files with the ROM files to add")
    parser.add_argument("--sets", nargs="+", default=[], help="MAME 0.251 sets to build afterwards")
    parser.add_argument("--replace", action="store_true", help="overwrite an added zip of the same name")
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    args = parser.parse_args()
    if not args.zips and not args.sets:
        parser.error("name zips to add, sets to build, or both")
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(args.host, username="pi", timeout=10)
    try:
        run(ssh, f"mkdir -p {EXTRA}")
        sftp = ssh.open_sftp()
        sftp.put(str(ROOT / "pi" / "mame_human" / "rebuild_set.py"), f"{CODE}/rebuild_set.py")  # knows EXTRA
        for path in map(Path, args.zips):
            target = f"{EXTRA}/{path.name}"
            local = hashlib.sha256(path.read_bytes()).hexdigest()
            there = run(ssh, f"sha256sum {target} 2>/dev/null | cut -d' ' -f1").strip()
            if there == local:
                print(f"{path.name}: already there")
                continue
            if there and not args.replace:
                print(f"{path.name}: a different file of that name is there; --replace to overwrite")
                return 1
            sftp.put(str(path), target)
            print(f"{path.name}: added to {EXTRA}")
        sftp.close()
        failed = 0
        if args.sets:
            _, stdout, _ = ssh.exec_command(f"cd {CODE} && python3 rebuild_set.py {' '.join(args.sets)}",
                                            timeout=300)  # reads every zip in the collection: longer than run() allows
            out = stdout.read().decode()
            for line in out.strip().splitlines():
                result = json.loads(line)
                failed += not result["ok"]
                print(f"{result['set']}: " + (f"built and verified, {result['files']} files from {result['from']}"
                                               if result["ok"] else f"not built: {result['why']} "
                                               f"{result.get('missing') or result.get('mame_said') or ''}"))
        return 1 if failed else 0
    finally:
        ssh.close()


if __name__ == "__main__":
    sys.exit(main())
