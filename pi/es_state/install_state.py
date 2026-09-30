#!/usr/bin/env python3
"""Build, install and activate a pinned ES state exporter through RetroPie's wrapper."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
import urllib.request
import zipfile

from patch_source import patch
from read_state import read_state
from read_catalog import read_catalog

REVISION = 'c9d905c31acf4b92d0a76b76c5cdf49e2b266d43'
ARCHIVE_SHA256 = 'f198fe3658fc717fe00aa391a9adf7fc9c9f871e9781f744d3277d22049b8c3a'
PUGI_REVISION = 'd2deb420bc70369faa12785df2b5dd4d390e523d'
PUGI_SHA256 = '47a22618fea3efcdad2f3eeb2ac80f8712389081c9605326903e96495fe4f5a8'
ES_DIR = Path('/opt/retropie/supplementary/emulationstation')
ROOT = Path('/opt/ai-arcade/es-state')
HERE = Path(__file__).resolve().parent
DEPENDENCIES = ['build-essential', 'cmake', 'libfreeimage-dev', 'libfreetype6-dev',
                'libcurl4-openssl-dev', 'libasound2-dev', 'libsdl2-dev',
                'libvlc-dev', 'libvlccore-dev', 'rapidjson-dev']


def run(*args):
    print('+', ' '.join(str(a) for a in args), flush=True)
    subprocess.run([str(a) for a in args], check=True)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def running_es(allow_absent=False):
    matches = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            args = (proc / 'cmdline').read_bytes().split(b'\0')
            if args[0].decode() == str(ES_DIR / 'emulationstation'):
                matches.append(int(proc.name))
        except (OSError, UnicodeError):
            continue
    if not matches and allow_absent:
        return None
    if len(matches) != 1:
        raise RuntimeError('Expected exactly one running RetroPie EmulationStation')
    return matches[0]


def check_restart(pid):
    status = Path('/proc/{}/status'.format(pid)).read_text()
    parent = next(line.split()[1] for line in status.splitlines() if line.startswith('PPid:'))
    command = Path('/proc/{}/cmdline'.format(parent)).read_bytes().split(b'\0')
    if str(ES_DIR / 'emulationstation.sh').encode() not in command:
        raise RuntimeError('ES is not managed by the expected RetroPie restart wrapper')
    # Refuse to terminate ES while it is waiting for an emulator/other child.
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            lines = (proc / 'status').read_text().splitlines()
        except FileNotFoundError:
            continue  # A short-lived process exited while scanning.
        if any(line.split() == ['PPid:', str(pid)] for line in lines):
            raise RuntimeError('ES has a running child; exit the game before installing state support')


def restart_es(pid):
    check_restart(pid)
    marker = Path('/tmp/es-restart')
    marker.touch()
    owner = Path('/proc/{}'.format(pid)).stat()
    # The unprivileged wrapper must be able to remove this file in sticky /tmp.
    os.chown(str(marker), owner.st_uid, owner.st_gid)
    os.kill(pid, signal.SIGTERM)


def wait_ready(timeout=90):
    deadline = time.monotonic() + timeout
    error = None
    while time.monotonic() < deadline:
        try:
            state = read_state()
            binary = ES_DIR / 'emulationstation'
            if os.stat('/proc/{}/exe'.format(state['pid'])).st_ino == binary.stat().st_ino:
                catalog = read_catalog()
                print('ES catalog: {} loaded systems'.format(len(catalog['systems'])), flush=True)
                print(json.dumps(state, indent=2), flush=True)
                return
        except (OSError, ValueError, KeyError, TypeError) as exc:
            error = exc
        time.sleep(1)
    raise RuntimeError('Patched ES did not publish live state: {}'.format(error))


def main():
    import pwd  # Pi-only account lookup; helpers also run in Windows unit tests.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rollback', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run as root')
    ROOT.mkdir(parents=True, exist_ok=True)
    binary = ES_DIR / 'emulationstation'
    original = ROOT / 'emulationstation.original'
    if args.rollback:
        pid = running_es(allow_absent=True)
        if pid is not None:
            check_restart(pid)
        staging = ES_DIR / 'emulationstation.ai-arcade-new'
        shutil.copy2(str(original), str(staging))
        os.replace(str(staging), str(binary))
        if pid is not None:
            restart_es(pid)
        else:
            # Recover a failed frontend through the existing console autologin.
            run('systemctl', 'restart', 'getty@tty1.service')
        if (ROOT / 'enabled').exists():
            (ROOT / 'enabled').unlink()
        if (ROOT / 'catalog-enabled').exists():
            (ROOT / 'catalog-enabled').unlink()
        print('Original ES restored and restart requested.')
        return
    metadata = (ES_DIR / 'retropie.pkg').read_text()
    if 'pkg_repo_commit="{}"'.format(REVISION) not in metadata:
        raise RuntimeError('Unsupported ES package revision; refusing to replace it')
    pid = running_es()
    identity = hashlib.sha256((REVISION + digest(HERE / 'ArcadeState.h')
                              + digest(HERE / 'patch_source.py')).encode()).hexdigest()
    build_root = ROOT / identity
    # Reuse a completed worktree for incremental patch updates on slow Pi CPUs.
    # CMake keeps the same absolute build path; changed headers are recompiled.
    if not build_root.exists():
        previous = sorted(path for path in ROOT.iterdir()
                          if path.is_dir() and (path / 'built.sha256').exists()
                          and (path / 'source/es-app/src/main.cpp').exists()
                          and (path / 'source.zip').exists()
                          and digest(path / 'source.zip') == ARCHIVE_SHA256)
        if previous:
            build_root = previous[-1]
    built = build_root / 'source' / 'emulationstation'
    stamp = build_root / 'built.sha256'
    expected_stamp = identity + ':' + digest(built) if built.exists() else ''
    legacy_stamp = (build_root.name == identity and built.exists() and stamp.exists()
                    and stamp.read_text() == digest(built))
    if not (stamp.exists() and built.exists()
            and (stamp.read_text() == expected_stamp or legacy_stamp)):
        missing = []
        for package in DEPENDENCIES:
            result = subprocess.run(['dpkg-query', '-W', '-f=${Status}', package],
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            # Multiarch packages can produce more than one identical status.
            if not result.stdout or result.stdout.replace(b'install ok installed', b'').strip():
                missing.append(package)
        if missing:
            run('apt-get', 'update')
            run('apt-get', 'install', '-y', *missing)
        build_root.mkdir(parents=True, exist_ok=True)
        archive = build_root / 'source.zip'
        if not archive.exists() or digest(archive) != ARCHIVE_SHA256:
            print('Downloading pinned EmulationStation source...', flush=True)
            with urllib.request.urlopen('https://codeload.github.com/RetroPie/EmulationStation/zip/' + REVISION,
                                        timeout=60) as response, archive.open('wb') as output:
                shutil.copyfileobj(response, output)
        if digest(archive) != ARCHIVE_SHA256:
            raise RuntimeError('ES source archive checksum mismatch')
        source = build_root / 'source'
        if not source.exists():
            with zipfile.ZipFile(str(archive)) as bundle:
                bundle.extractall(str(build_root))
            (build_root / ('EmulationStation-' + REVISION)).rename(source)
        patch(source, HERE / 'ArcadeState.h')
        pugi = source / 'external/pugixml'
        if not (pugi / 'CMakeLists.txt').exists():
            archive = build_root / 'pugixml.zip'
            with urllib.request.urlopen('https://codeload.github.com/zeux/pugixml/zip/' + PUGI_REVISION,
                                        timeout=60) as response, archive.open('wb') as output:
                shutil.copyfileobj(response, output)
            if digest(archive) != PUGI_SHA256:
                raise RuntimeError('pugixml source archive checksum mismatch')
            with zipfile.ZipFile(str(archive)) as bundle:
                for member in bundle.infolist():
                    parts = member.filename.split('/')[1:]
                    if not parts or not parts[-1]:
                        continue
                    destination = pugi.joinpath(*parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.open(member) as src, destination.open('wb') as dst:
                        shutil.copyfileobj(src, dst)
        run('cmake', '-S', source, '-B', source / 'build', '-DRPI=On', '-DUSE_GLES1=On',
            '-DFREETYPE_INCLUDE_DIRS=/usr/include/freetype2/')
        # One compiler process keeps the Pi 3 within its RAM budget.
        run('cmake', '--build', source / 'build', '--', '-j1')
        stamp.write_text(identity + ':' + digest(built))
    pid = running_es()
    check_restart(pid)
    user = pwd.getpwuid(Path('/proc/{}'.format(pid)).stat().st_uid)
    tmpfiles = Path('/etc/tmpfiles.d/ai-arcade-state.conf')
    tmpfiles.write_text('d /run/ai-arcade 0755 {} {} -\n'.format(user.pw_name, user.pw_gid))
    run('systemd-tmpfiles', '--create', tmpfiles)
    for name in ('read_state.py', 'read_catalog.py', 'install_state.py', 'patch_source.py', 'ArcadeState.h'):
        if HERE != ROOT:
            shutil.copy2(str(HERE / name), str(ROOT / name))
    if digest(binary) != digest(built):
        if not original.exists():
            shutil.copy2(str(binary), str(original))
        staging = ES_DIR / 'emulationstation.ai-arcade-new'
        shutil.copy2(str(built), str(staging))
        os.chmod(str(staging), 0o755)
        os.replace(str(staging), str(binary))
        restart_es(pid)
    elif os.stat('/proc/{}/exe'.format(pid)).st_ino != binary.stat().st_ino:
        restart_es(pid)
    wait_ready()
    (ROOT / 'enabled').write_text(identity + '\n')
    (ROOT / 'catalog-enabled').write_text('1\n')
    print('ES state installation and verification complete.', flush=True)


if __name__ == '__main__':
    main()
