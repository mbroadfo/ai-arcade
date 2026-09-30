#!/usr/bin/env python3
import argparse
import datetime
import os
import shutil
import subprocess
import sys
from pathlib import Path

ES_CFG = Path('/opt/retropie/configs/all/emulationstation/es_input.cfg')
RA_DIR = Path('/opt/retropie/configs/all/retroarch/autoconfig')
INSTALL_DIR = Path('/opt/ai-arcade')
SERVICE_NAME = 'ai-arcade-controller.service'
SERVICE_DST = Path('/etc/systemd/system') / SERVICE_NAME
MODULES_FILE = Path('/etc/modules-load.d/ai-arcade.conf')


def run(*args):
    print('+', ' '.join(str(a) for a in args))
    subprocess.run([str(a) for a in args], check=True)


def require_root():
    if os.geteuid() != 0:
        raise SystemExit('ERROR: run with sudo/root')


def ensure_evdev():
    try:
        import evdev  # noqa: F401
        return
    except ImportError:
        pass
    if shutil.which('pip3') is None:
        run('apt-get', 'update')
        run('apt-get', 'install', '-y', 'python3-pip')
    run('pip3', 'install', 'evdev>=1.6,<2')


def main():
    parser = argparse.ArgumentParser(description='Install AI Arcade Pi services')
    parser.add_argument('--source', default=str(Path(__file__).resolve().parent))
    args = parser.parse_args()
    source = Path(args.source).resolve()

    require_root()
    if not ES_CFG.exists():
        raise SystemExit('ERROR: RetroPie EmulationStation config not found: %s' % ES_CFG)
    if not RA_DIR.is_dir():
        raise SystemExit('ERROR: RetroArch autoconfig directory not found: %s' % RA_DIR)

    if not Path('/dev/uinput').exists():
        run('modprobe', 'uinput')
    if not Path('/dev/uinput').exists():
        raise SystemExit('ERROR: /dev/uinput unavailable after modprobe')

    MODULES_FILE.write_text('uinput\n')
    ensure_evdev()

    stamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    backup = INSTALL_DIR / 'backups' / stamp
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(ES_CFG), str(backup / 'es_input.cfg'))
    for name in ('AI Arcade Player 1.cfg', 'AI Arcade Player 2.cfg'):
        existing = RA_DIR / name
        if existing.exists():
            shutil.copy2(str(existing), str(backup / name))

    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(source / 'controller_broker.py'), str(INSTALL_DIR / 'controller_broker.py'))
    shutil.copy2(str(source / 'verify.py'), str(INSTALL_DIR / 'verify.py'))
    os.chmod(str(INSTALL_DIR / 'controller_broker.py'), 0o755)
    os.chmod(str(INSTALL_DIR / 'verify.py'), 0o755)

    for name in ('AI Arcade Player 1.cfg', 'AI Arcade Player 2.cfg'):
        shutil.copy2(str(source / 'retropie' / name), str(RA_DIR / name))

    run(sys.executable, str(source / 'patch_es_input.py'), str(ES_CFG))
    shutil.copy2(str(source / 'systemd' / SERVICE_NAME), str(SERVICE_DST))

    run('systemctl', 'daemon-reload')
    run('systemctl', 'enable', SERVICE_NAME)
    run('systemctl', 'restart', SERVICE_NAME)
    run(sys.executable, str(INSTALL_DIR / 'verify.py'))

    print('\nAI Arcade Pi installation complete.')
    print('Backup snapshot:', backup)


if __name__ == '__main__':
    main()
