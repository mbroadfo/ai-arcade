#!/usr/bin/env python3
import argparse
import json
import socket
import subprocess
import time
from pathlib import Path
import xml.etree.ElementTree as ET

ES_CFG = Path('/opt/retropie/configs/all/emulationstation/es_input.cfg')
RA_DIR = Path('/opt/retropie/configs/all/retroarch/autoconfig')
SERVICE = 'ai-arcade-controller.service'
ES_STATE_ROOT = Path('/opt/ai-arcade/es-state')
EXPECTED = {
    'AI Arcade Player 1': '030000000912000001a1000001000000',
    'AI Arcade Player 2': '030000000912000002a1000001000000',
}


def check(label, ok, detail=''):
    status = 'PASS' if ok else 'FAIL'
    suffix = (' - ' + detail) if detail else ''
    print('{:<34} {}{}'.format(label, status, suffix))
    return bool(ok)


def broker_ping(timeout=2):
    try:
        deadline = time.monotonic() + timeout
        s = socket.create_connection(('127.0.0.1', 8765), timeout=timeout)
        try:
            s.sendall(b'{"op":"ping"}\n')
            data = b''
            while not data.endswith(b'\n'):
                s.settimeout(max(0.001, deadline - time.monotonic()))
                if time.monotonic() >= deadline or len(data) > 65536:
                    return False
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
        finally:
            s.close()
        obj = json.loads(data.decode('utf-8'))
        return (isinstance(obj, dict) and obj.get('ok') is True
                and obj.get('service') == 'ai-arcade-controller-broker'
                and obj.get('players') == [1, 2])
    except Exception:
        return False


def systemctl_ok(operation):
    try:
        return subprocess.run(
            ['systemctl', operation, '--quiet', SERVICE],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2
        ).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def runtime_checks():
    results = {'/dev/uinput': Path('/dev/uinput').exists(),
               'controller broker service': systemctl_ok('is-active')}
    try:
        devices = Path('/proc/bus/input/devices').read_text(errors='replace')
    except OSError:
        devices = ''
    for name in EXPECTED:
        results[name] = ('N: Name="%s"' % name) in devices
    results['broker TCP ping'] = broker_ping()
    if (ES_STATE_ROOT / 'enabled').exists():
        try:
            results['EmulationStation live state'] = subprocess.run(
                ['/usr/bin/python3', str(ES_STATE_ROOT / 'read_state.py')],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3
            ).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            results['EmulationStation live state'] = False
    return results


def wait_for_runtime(timeout=30, interval=0.5):
    deadline = time.monotonic() + timeout
    while True:
        results = runtime_checks()
        if all(results.values()) or time.monotonic() >= deadline:
            return results
        print('Waiting for: ' + ', '.join(k for k, ok in results.items() if not ok),
              flush=True)
        time.sleep(min(interval, max(0, deadline - time.monotonic())))


def diagnostics():
    for command in (
        ['systemctl', 'status', SERVICE, '--no-pager', '--full'],
        ['journalctl', '-u', SERVICE, '-b', '-n', '100', '--no-pager'],
        ['tail', '-n', '60', str(ES_CFG.parent / 'es_log.txt')],
    ):
        print('\nDiagnostics: ' + ' '.join(command), flush=True)
        try:
            subprocess.run(command, check=False, timeout=10)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print('Could not collect diagnostics:', exc)


def main():
    parser = argparse.ArgumentParser(description='Verify AI Arcade Pi readiness')
    parser.add_argument('--timeout', type=float, default=30,
                        help='Readiness retry window in seconds (default: 30; 0: one check)')
    args = parser.parse_args()
    if not 0 <= args.timeout <= 600:
        parser.error('--timeout must be between 0 and 600 seconds')
    results = [check(label, ok) for label, ok in wait_for_runtime(args.timeout).items()]
    results.append(check('controller broker enabled at boot', systemctl_ok('is-enabled')))


    es_ok = ES_CFG.exists()
    found = {}
    if es_ok:
        try:
            root = ET.parse(str(ES_CFG)).getroot()
            found = {
                node.get('deviceName'): node.get('deviceGUID')
                for node in root.findall('inputConfig')
            }
        except Exception as exc:
            es_ok = False
            print('EmulationStation XML parse error:', exc)
    results.append(check('EmulationStation config parses', es_ok))
    for name, guid in EXPECTED.items():
        results.append(check('ES mapping ' + name[-1], found.get(name) == guid))

    for player in (1, 2):
        path = RA_DIR / ('AI Arcade Player %d.cfg' % player)
        good = path.exists() and ('input_device = "AI Arcade Player %d"' % player) in path.read_text(errors='replace')
        results.append(check('RetroArch mapping P%d' % player, good))

    print()
    if all(results):
        print('AI Arcade Pi verification: PASS')
        return 0
    print('AI Arcade Pi verification: FAIL')
    diagnostics()
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
