#!/usr/bin/env python3
import argparse
import datetime
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ES_CFG = Path('/opt/retropie/configs/all/emulationstation/es_input.cfg')
RA_DIR = Path('/opt/retropie/configs/all/retroarch/autoconfig')
INSTALL_DIR = Path('/opt/ai-arcade')
SERVICE_NAME = 'ai-arcade-controller.service'
SERVICE_DST = Path('/etc/systemd/system') / SERVICE_NAME
MODULES_FILE = Path('/etc/modules-load.d/ai-arcade.conf')
RA_CFG = Path('/opt/retropie/configs/all/retroarch.cfg')
INPUT_SCRIPT = Path('/opt/retropie/supplementary/emulationstation/scripts/inputconfiguration.sh')


def run(*args, check=True):
    print('+', ' '.join(str(a) for a in args))
    return subprocess.run([str(a) for a in args], check=check)


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


def stop_legacy_brokers():
    """Stop manually launched brokers so systemd can own port 8765."""
    run('systemctl', 'stop', SERVICE_NAME, check=False)
    me = os.getpid()
    victims = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == me:
            continue
        try:
            cmdline = (proc / 'cmdline').read_bytes().replace(b'\x00', b' ').decode('utf-8', errors='replace')
        except (OSError, IOError):
            continue
        if 'controller_broker.py' in cmdline:
            victims.append(int(proc.name))
    for pid in victims:
        print('+ stopping legacy controller broker pid', pid)
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    if victims:
        time.sleep(0.5)


def set_retroarch_setting(path, key, value):
    """Set one RetroArch config value without disturbing unrelated settings."""
    text = path.read_text(errors='replace')
    lines = text.splitlines()

    found = False
    output = []

    for line in lines:
        stripped = line.strip()

        if '=' in stripped:
            existing_key = stripped.split('=', 1)[0].strip()
            if existing_key == key:
                output.append('{} = "{}"'.format(key, value))
                found = True
                continue

        output.append(line)

    if not found:
        output.append('{} = "{}"'.format(key, value))

    path.write_text('\n'.join(output) + '\n')


def configure_keyboard(source):
    """Give the keyboard to RetroPie's own input configuration, as if it had been set up in EmulationStation's
    menu: inputconfiguration.sh writes the same keys into RetroArch (and the other emulators that take a keyboard)."""
    if not INPUT_SCRIPT.exists():
        print('+ RetroPie input configuration not installed; keyboard left to EmulationStation only')
        return
    user = ES_CFG.owner()
    temp = Path(os.path.expanduser('~' + user)) / '.emulationstation' / 'es_temporaryinput.cfg'
    if not temp.parent.exists():
        temp.parent.mkdir()
        shutil.chown(str(temp.parent), user, user)
    run(sys.executable, str(source / 'patch_es_input.py'), str(temp), '--keyboard-only')
    try:
        # Its exit status is whatever its last check returned (often 1, "this emulator has no finishing step"), as
        # EmulationStation, which ignores it, expects; the written configuration is what verify.py checks.
        run('sudo', '-u', user, 'bash', str(INPUT_SCRIPT), check=False)
    finally:
        temp.unlink()


def require_root():
    geteuid = getattr(os, 'geteuid', None)
    if geteuid is None:
        raise SystemExit('ERROR: this installer must run on Linux')
    if geteuid() != 0:
        raise SystemExit('ERROR: run with sudo/root')


def main():
    parser = argparse.ArgumentParser(description='Install AI Arcade Pi services')
    parser.add_argument('--source', default=str(Path(__file__).resolve().parent))
    parser.add_argument('--timeout', type=float, default=30)
    args = parser.parse_args()
    if not 0 <= args.timeout <= 600:
        parser.error('--timeout must be between 0 and 600 seconds')
    source = Path(args.source).resolve()

    require_root()
    if not ES_CFG.exists():
        raise SystemExit('ERROR: RetroPie EmulationStation config not found: %s' % ES_CFG)
    if not RA_DIR.is_dir():
        raise SystemExit('ERROR: RetroArch autoconfig directory not found: %s' % RA_DIR)
    if not RA_CFG.exists():
        raise SystemExit('ERROR: RetroArch config not found: %s' % RA_CFG)
    
    if not Path('/dev/uinput').exists():
        run('modprobe', 'uinput')
    if not Path('/dev/uinput').exists():
        raise SystemExit('ERROR: /dev/uinput unavailable after modprobe')

    MODULES_FILE.write_text('uinput\n')
    ensure_evdev()
    stop_legacy_brokers()

    stamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')
    backup = INSTALL_DIR / 'backups' / stamp
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(ES_CFG), str(backup / 'es_input.cfg'))
    shutil.copy2(str(RA_CFG), str(backup / 'retroarch.cfg'))

    for name in ('AI Arcade Player 1.cfg', 'AI Arcade Player 2.cfg'):
        existing = RA_DIR / name
        if existing.exists():
            shutil.copy2(str(existing), str(backup / name))

    set_retroarch_setting(
        RA_CFG,
        'network_cmd_enable',
        'true'
    )

    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(source / 'controller_broker.py'), str(INSTALL_DIR / 'controller_broker.py'))
    shutil.copy2(str(source / 'verify.py'), str(INSTALL_DIR / 'verify.py'))
    os.chmod(str(INSTALL_DIR / 'controller_broker.py'), 0o755)
    os.chmod(str(INSTALL_DIR / 'verify.py'), 0o755)

    for name in ('AI Arcade Player 1.cfg', 'AI Arcade Player 2.cfg'):
        shutil.copy2(str(source / 'retropie' / name), str(RA_DIR / name))

    run(sys.executable, str(source / 'patch_es_input.py'), str(ES_CFG))
    configure_keyboard(source)
    shutil.copy2(str(source / 'systemd' / SERVICE_NAME), str(SERVICE_DST))

    run('systemctl', 'daemon-reload')
    run('systemctl', 'enable', SERVICE_NAME)
    run('systemctl', 'restart', SERVICE_NAME)
    run(sys.executable, str(INSTALL_DIR / 'verify.py'), '--timeout', str(args.timeout))

    print('\nAI Arcade Pi installation complete.')
    print('Backup snapshot:', backup)


if __name__ == '__main__':
    main()
