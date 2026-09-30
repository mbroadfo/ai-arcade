#!/usr/bin/env python3
"""Live ES acceptance test: observe, RIGHT, observe, LEFT, confirm return. No launch inputs."""
import argparse
from pathlib import Path
import time

import paramiko
from controller_client import send
from es_state import fetch


def navigable_system(state):
    if (state['view'] not in ('system_select', 'game_list') or state['overlay_open']
            or state['screensaver_active'] or state['sleeping'] or not state['system']):
        raise RuntimeError('Test requires an unobstructed, awake ES carousel or game list')
    return state['system']['name']


def wait_changed(ssh, previous, expected=None):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = fetch(ssh)
        name = navigable_system(state)
        if state['pid'] != previous['pid'] or state.get('boot_id') != previous.get('boot_id'):
            raise RuntimeError('ES restarted during the navigation test')
        if state['view'] != previous['view']:
            raise RuntimeError('ES changed views during the directional test')
        if state['sequence'] > previous['sequence']:
            if (expected is None and name != previous['system']['name']) or name == expected:
                return state
        time.sleep(0.25)
    raise RuntimeError('Timed out waiting for the expected ES selection change')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='192.168.10.155')
    parser.add_argument('--user', default='pi')
    parser.add_argument('--key', default=str(Path.home() / '.ssh/id_rsa'))
    parser.add_argument('--port', type=int, default=22)
    args = parser.parse_args()
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    moved = False
    try:
        ssh.connect(args.host, port=args.port, username=args.user,
                    key_filename=str(Path(args.key).expanduser()), timeout=10)
        before = fetch(ssh)
        original = navigable_system(before)
        print('Before:', original, flush=True)
        moved = True
        response = send(args.host, 8765, {'player': 1, 'op': 'tap', 'action': 'RIGHT', 'ms': 120})
        if not response.get('ok'):
            raise RuntimeError(str(response))
        after = wait_changed(ssh, before)
        print('Right: ', navigable_system(after), flush=True)
        response = send(args.host, 8765, {'player': 1, 'op': 'tap', 'action': 'LEFT', 'ms': 120})
        moved = False
        if not response.get('ok'):
            raise RuntimeError(str(response))
        returned = wait_changed(ssh, after, original)
        print('Left:  ', navigable_system(returned), flush=True)
        print('ES navigation state test: PASS', flush=True)
    finally:
        try:
            if moved:
                send(args.host, 8765, {'player': 1, 'op': 'tap', 'action': 'LEFT', 'ms': 120})
            send(args.host, 8765, {'op': 'release_all'})
        finally:
            ssh.close()


if __name__ == '__main__':
    main()
