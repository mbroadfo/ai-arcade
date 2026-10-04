"""Bring the old cabinet's emulator choices to a new one: each system's default emulator and the per-game choices
(RetroPie's /opt/retropie/configs/<system>/emulators.cfg and configs/all/emulators.cfg).

Emulators the old Pi 3 had and a 64-bit Pi does not are translated to their nearest replacement (TRANSLATE). A choice
whose emulator is not installed on the new Pi is skipped and reported, so this can be run again after more emulators
are installed (pi/setup_pi5.sh emulators). Safe to re-run.

    python tools/migrate_pi_settings.py [--old 192.168.10.155] [--new ADDRESS]
"""
import argparse
import re
import sys

import paramiko

from gamelib import DEFAULT_PI_HOST
from probe_mame_input import run

CONFIGS = "/opt/retropie/configs"
TRANSLATE = {
    "mame4all": "lr-mame2000",      # the same MAME 0.37b5 ROM sets
    "advmame-1.4": "advmame",       # AdvanceMAME 3 reads the 0.106 sets 1.4 did
    "advmame-0.94": "advmame",
    "lr-snes9x2010": "lr-snes9x",
}
# Vector games: lr-mame2000 (the MAME4All stand-in) draws them at a small fixed size that a 1080p screen stretches into
# jagged lines; lr-mame2003 draws them at the screen's height, antialiased. Each of these loads its ROM there (checked
# on the Pi 5); the Cinematronics ones have no sound samples on either cabinet. A game the old cabinet gave another
# emulator (AdvanceMAME, lr-mame2003) keeps it.
VECTOR_GAMES = ("asteroid astdelux barrier boxingb bradley bwidow demon elim2 esb gravitar llander mhavoc redbaron "
                "ripoff spacduel spacewar spacfury speedfrk starhawk starwars tailg warrior wotw").split()
VECTOR_OPTIONS = {"mame2003_vector_resolution": "1440x1080", "mame2003_vector_antialias": "enabled"}
# TRS-80 (sdltrs): the old Pi listed .cmd and .bas files and ran a .cmd by handing sdl2trs its path (the old config's
# "-exec %ROM%": sdl2trs ignores the flag, takes the path as the program to load and runs it; checked on both builds,
# headless, 4 October 2026: entry point 0x8005 for timetrk1.cmd). RetroPie's stock launcher gives the path to -disk0,
# which only fits disk images (a .cmd there fails with "trs_disk_command(0xB7) not implemented"). So disks keep the
# stock launcher and each program gets its own, chosen per game. The old .bas launcher's line was cut off (no closing
# quote), so this one is its intent: NEWDOS-80 in drive 0, the program's disk in drive 1; untested past loading.
SDLTRS = "/opt/retropie/emulators/sdltrs/sdl2trs -fullscreen -nomousepointer -showled"
TRS80_MODELS = {  # the old Pi's own command lines, minus the file argument
    "model1": f"{SDLTRS} -m1 -romfile /home/pi/RetroPie/BIOS/level2.rom",
    "model3": f"{SDLTRS} -m3 -romfile3 /home/pi/RetroPie/BIOS/level3.rom",
    "model4": f"{SDLTRS} -m4 -romfile3 /home/pi/RetroPie/BIOS/level4.rom",
    "model4p": f"{SDLTRS} -m4p -romfile4p /home/pi/RetroPie/BIOS/level4p.rom",
}
TRS80_LAUNCHERS = {f"sdltrs-{m}-cmd": f"{base} -exec %ROM%" for m, base in TRS80_MODELS.items()}
TRS80_LAUNCHERS["sdltrs-model1-bas"] = (f"{TRS80_MODELS['model1']} -disk0 /home/pi/RetroPie/roms/trs-80/NEWDOS_80.DSK "
                                        "-disk1 %ROM%")
TRS80_EXTENSIONS = ".dsk .DSK .cmd .CMD .bas .BAS"
ES_SYSTEMS = "/etc/emulationstation/es_systems.cfg"
LINE = re.compile(r'^\s*([^=\s]+)\s*=\s*"(.*)"\s*$')


def connect(host):
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(hostname=host, username="pi", timeout=10)
    return ssh


def parse(text):
    return [(m.group(1), m.group(2)) for m in map(LINE.match, text.splitlines()) if m]


def set_options(ssh, sftp, options):
    """Set libretro core options, leaving the others as they are."""
    path = f"{CONFIGS}/all/retroarch-core-options.cfg"
    current = dict(parse(run(ssh, f"cat {path} 2>/dev/null || true")))
    current.update(options)
    with sftp.file(path, "w") as f:
        f.write("".join(f'{k} = "{v}"\n' for k, v in current.items()))


def trs80(new, sftp):
    """Make the TRS-80 programs listed and launchable; returns {per-game key: launcher} for all/emulators.cfg."""
    cfg = f"{CONFIGS}/trs-80/emulators.cfg"
    current = parse(run(new, f"cat {cfg}"))
    lines = [f'{k} = "{v}"' for k, v in current if k not in TRS80_LAUNCHERS]
    lines += [f'{k} = "{v}"' for k, v in TRS80_LAUNCHERS.items()]
    with sftp.file(cfg, "w") as f:
        f.write("\n".join(lines) + "\n")
    text = run(new, f"cat {ES_SYSTEMS}")
    fixed = re.sub(r"(<name>trs-80</name>.*?<extension>)[^<]*(</extension>)", rf"\g<1>{TRS80_EXTENSIONS}\g<2>", text,
                   count=1, flags=re.S)
    if fixed != text:
        with sftp.file("/tmp/ai-arcade-es_systems.cfg", "w") as f:
            f.write(fixed)
        run(new, f"test -e {ES_SYSTEMS}.before-ai-arcade || sudo cp -p {ES_SYSTEMS} {ES_SYSTEMS}.before-ai-arcade")
        run(new, f"sudo install -m 644 /tmp/ai-arcade-es_systems.cfg {ES_SYSTEMS}")
        print(f"TRS-80 extensions in {ES_SYSTEMS}: {TRS80_EXTENSIONS} (restart EmulationStation to list them)")
    files = run(new, "ls /home/pi/RetroPie/roms/trs-80").split()
    choice = {}
    for name in files:
        stem, ext = name.rsplit(".", 1) if "." in name else (name, "")
        if ext.lower() == "cmd":
            choice[f"trs-80_{stem}"] = "sdltrs-model1-cmd"
        elif ext.lower() == "bas":
            choice[f"trs-80_{stem}"] = "sdltrs-model1-bas"
    return choice


def gamelists(old, new):
    """Copy the old Pi's ES gamelists (names, play counts, favourites) for systems the new Pi has none for. ES writes
    its gamelists when it exits, so it is stopped first (getty@tty1 owns it) and started again after."""
    base = "/home/pi/.emulationstation/gamelists"
    wanted = [s for s in run(old, f"ls {base}").split()
              if run(old, f"test -f {base}/{s}/gamelist.xml && echo y || echo n").strip() == "y"
              and run(new, f"test -f {base}/{s}/gamelist.xml && echo y || echo n").strip() == "n"]
    if not wanted:
        print("Gamelists: nothing to copy")
        return
    run(new, "sudo systemctl stop getty@tty1")
    try:
        old_sftp, new_sftp = old.open_sftp(), new.open_sftp()
        for system in wanted:
            run(new, f"mkdir -p {base}/{system}")
            with old_sftp.file(f"{base}/{system}/gamelist.xml") as src, new_sftp.file(f"{base}/{system}/gamelist.xml", "w") as dst:
                dst.write(src.read())
            print(f"  gamelist copied: {system}")
        old_sftp.close()
        new_sftp.close()
    finally:
        run(new, "sudo systemctl restart getty@tty1")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", default="192.168.10.155")
    parser.add_argument("--new", default=DEFAULT_PI_HOST)
    parser.add_argument("--only", choices=["trs-80", "gamelists"], help="run just this step, leaving every other setting as it is "
                        "(the full run rewrites each system's default from the old Pi, undoing later choices)")
    args = parser.parse_args()
    if args.only == "gamelists":
        old, new = connect(args.old), connect(args.new)
        try:
            gamelists(old, new)
        finally:
            old.close()
            new.close()
        return 0
    if args.only == "trs-80":
        new = connect(args.new)
        try:
            sftp = new.open_sftp()
            chosen = trs80(new, sftp)
            path = f"{CONFIGS}/all/emulators.cfg"
            games = dict(parse(run(new, f"cat {path} 2>/dev/null || true")))
            games.update(chosen)
            with sftp.file(path, "w") as f:
                f.write("\n".join(f'{k} = "{v}"' for k, v in games.items()) + "\n")
            print(f"{len(chosen)} TRS-80 per-game launcher choices written")
            sftp.close()
        finally:
            new.close()
        return 0
    old, new = connect(args.old), connect(args.new)
    try:
        sftp = new.open_sftp()
        installed = {}  # system -> the emulator names its emulators.cfg offers on the new Pi

        def offers(system):
            if system not in installed:
                text = run(new, f"cat {CONFIGS}/{system}/emulators.cfg 2>/dev/null || true")
                installed[system] = {k for k, _ in parse(text) if k != "default"}
            return installed[system]

        skipped = []
        print("System defaults:")
        for line in run(old, f"grep -H '^default' {CONFIGS}/*/emulators.cfg || true").splitlines():
            path, _, setting = line.partition(":")
            system = path.split("/")[-2]
            (_, emulator), = parse(setting)
            emulator = TRANSLATE.get(emulator, emulator)
            if emulator not in offers(system):
                skipped.append(f"{system} default {emulator}")
                continue
            cfg = f"{CONFIGS}/{system}/emulators.cfg"
            lines = [f'{k} = "{v}"' for k, v in parse(run(new, f"cat {cfg}")) if k != "default"]
            with sftp.file(cfg, "w") as f:
                f.write("\n".join(lines + [f'default = "{emulator}"']) + "\n")
            print(f"  {system}: {emulator}")

        games = {}
        for key, emulator in parse(run(old, f"cat {CONFIGS}/all/emulators.cfg 2>/dev/null || true")):
            system = key.split("_", 1)[0]
            emulator = TRANSLATE.get(emulator, emulator)
            if emulator in offers(system):
                games[key] = emulator
            else:
                skipped.append(f"{key} {emulator}")
        arcade_default = dict(parse(run(new, f"cat {CONFIGS}/arcade/emulators.cfg"))).get("default")
        moved = [g for g in VECTOR_GAMES if games.get(f"arcade_{g}", arcade_default) == "lr-mame2000"]
        if moved and "lr-mame2003" in offers("arcade"):
            games.update({f"arcade_{g}": "lr-mame2003" for g in moved})
            set_options(new, sftp, VECTOR_OPTIONS)
            print(f"Vector games moved to lr-mame2003 ({VECTOR_OPTIONS['mame2003_vector_resolution']}): {' '.join(moved)}")
        games.update(trs80(new, sftp))
        with sftp.file(f"{CONFIGS}/all/emulators.cfg", "w") as f:
            f.write("\n".join(f'{k} = "{v}"' for k, v in games.items()) + "\n")
        print(f"Per-game choices: {len(games)} written")
        sftp.close()

        if skipped:
            print(f"\nSkipped (emulator not installed on {args.new}; run again once it is):")
            for item in skipped:
                print("  " + item)
    finally:
        old.close()
        new.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
