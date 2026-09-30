#!/usr/bin/env python3
import json
import socket
import subprocess
from pathlib import Path
import xml.etree.ElementTree as ET

ES_CFG = Path('/opt/retropie/configs/all/emulationstation/es_input.cfg')
RA_DIR = Path('/opt/retropie/configs/all/retroarch/autoconfig')
SERVICE = 'ai-arcade-controller.service'
EXPECTED = {
    'AI Arcade Player 1': '030000000912000001a1000001000000',
    'AI Arcade Player 2': '030000000912000002a1000001000000',
}


def check(label, ok, detail=''):
    status = 'PASS' if ok else 'FAIL'
    suffix = (' - ' + detail) if detail else ''
    print('{:<34} {}{}'.format(label, status, suffix))
    return bool(ok)


def broker_ping():
    try:
        s = socket.create_connection(('127.0.0.1', 8765), timeout=2)
        try:
            s.sendall(b'{"op":"ping"}\n')
            data = b''
            while not data.endswith(b'\n'):
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
        finally:
            s.close()
        obj = json.loads(data.decode('utf-8'))
        return obj.get('ok') is True
    except Exception:
        return False


def main():
    results = []
    results.append(check('/dev/uinput', Path('/dev/uinput').exists()))

    service_ok = subprocess.run(
        ['systemctl', 'is-active', '--quiet', SERVICE],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    ).returncode == 0
    results.append(check('controller broker service', service_ok))

    devices = Path('/proc/bus/input/devices').read_text(errors='replace')
    for name in EXPECTED:
        results.append(check(name, ('N: Name="%s"' % name) in devices))

    results.append(check('broker TCP ping', broker_ping()))

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
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
