"""Small, interactive cabinet tests; no LLM required."""
import argparse
import re
import socket
import sys
import time
from pathlib import Path

import paramiko

from controller_client import send
from es_state import fetch

TARGET = '/home/pi/RetroPie/roms/arcade/pacman.zip'
REMAP = '/opt/retropie/configs/arcade/MAME 2003 (0.78)/MAME 2003 (0.78).rmp'


def remote(ssh, command):
    _, out, err = ssh.exec_command(command, timeout=15)
    value = out.read().decode('utf-8')
    if out.channel.recv_exit_status():
        raise RuntimeError(err.read().decode('utf-8') or value)
    return value


def coin_start_actions(remap):
    values = dict(
        re.findall(
            r'^\s*(input_player1_btn_\w+)\s*=\s*"(\d+)"',
            remap,
            re.M
        )
    )

    select = int(values.get('input_player1_btn_select', '2'))
    start = int(values.get('input_player1_btn_start', '3'))

    if (select, start) == (2, 3):
        return 'COIN', 'START'

    if (select, start) == (3, 2):
        return 'START', 'COIN'

    raise RuntimeError('Unrecognized Coin/Start remap; refusing to guess.')


def launch(read, tap, sleep=time.sleep):
    """Navigate by observed selections; only select the exact target ROM."""
    initial = read()
    session = (initial['boot_id'], initial['pid'])
    seen = set()

    for _ in range(1200):
        state = read()

        if (state['boot_id'], state['pid']) != session:
            raise RuntimeError('ES restarted during navigation.')

        if state['overlay_open']:
            raise RuntimeError('Close the ES menu/dialog before launching.')

        if state['sleeping'] or state['screensaver_active']:
            tap('UP')
            sleep(0.4)
            continue

        view = state['view']
        system = state.get('system', {}).get('name')
        selection = state.get('selection') or {}

        marker = (
            view,
            system,
            selection.get('path')
        )

        if marker in seen:
            raise RuntimeError(
                'Navigation repeated a selection; no game launched.'
            )

        seen.add(marker)

        if view not in ('system_select', 'game_list'):
            raise RuntimeError('Unsupported ES view: ' + view)

        if system != 'arcade':
            action = 'RIGHT'

        elif view == 'system_select':
            action = 'BUTTON_1'

        elif (
            selection.get('path') == TARGET
            and selection.get('type') == 'game'
        ):
            print('Verified Pac-Man; launching.', flush=True)
            tap('BUTTON_1')
            return

        else:
            action = 'DOWN'

        print(
            'ES:',
            system,
            selection.get('name', ''),
            flush=True
        )

        tap(action)

        for _ in range(20):
            sleep(0.15)
            updated = read()

            if updated['sequence'] > state['sequence']:
                new_marker = (
                    updated['view'],
                    (updated.get('system') or {}).get('name'),
                    (updated.get('selection') or {}).get('path')
                )

                if new_marker != marker:
                    break
        else:
            raise RuntimeError('ES selection did not change.')

    raise RuntimeError('Navigation limit reached.')


def send_retroarch_command(host, command):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        sock.sendto(
            command.encode('ascii'),
            (host, 55355)
        )
    finally:
        sock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        'command',
        choices=['pacman', 'reboot', 'controls']
    )

    parser.add_argument(
        '--host',
        default='192.168.10.155'
    )

    parser.add_argument(
        '--user',
        default='pi'
    )

    parser.add_argument(
        '--key',
        default=str(Path.home() / '.ssh/id_rsa')
    )

    args = parser.parse_args()

    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())

    def tap(action):
        result = send(
            args.host,
            8765,
            {
                'op': 'tap',
                'player': 1,
                'action': action,
                'ms': 180
            }
        )

        if not result.get('ok'):
            raise RuntimeError(str(result))

    try:
        ssh.connect(
            args.host,
            username=args.user,
            key_filename=args.key,
            timeout=10
        )

        if args.command == 'reboot':
            remote(
                ssh,
                'sudo -n shutdown -r +1'
            )

            print('Pi reboot scheduled in one minute.')

        elif args.command == 'pacman':
            launch(
                lambda: fetch(ssh),
                tap
            )

        else:
            import msvcrt

            processes = remote(
                ssh,
                "pgrep -a retroarch 2>/dev/null || true; "
                "pgrep -a mame 2>/dev/null || true"
            )

            retroarch_mode = (
                TARGET in processes
                and 'mame2003_libretro.so' in processes
            )

            standalone_mame_mode = (
                'mame' in processes
                and 'pacman' in processes
                and not retroarch_mode
            )

            if not retroarch_mode and not standalone_mame_mode:
                raise RuntimeError('Pac-Man is not running.')

            if retroarch_mode:
                remap = remote(
                    ssh,
                    "if [ -f '" + REMAP + "' ]; "
                    "then cat '" + REMAP + "'; fi"
                )

                coin, start = coin_start_actions(remap)

                print('Pac-Man emulator: RetroArch / lr-mame2003')
                print(
                    'C = coin | 1 = one-player start | '
                    'WASD/arrows = joystick | P = pause | Q = quit tester'
                )

            else:
                coin = 'COIN'
                start = 'START'

                print('Pac-Man emulator: standalone MAME')
                print(
                    'C = coin | 1 = one-player start | '
                    'WASD/arrows = joystick | Q = quit tester'
                )
                print(
                    'P is not mapped yet for standalone MAME.'
                )

            print(
                'Each direction is a short tap; '
                'hold a key to repeat.'
            )

            print(
                'Q closes only this tester; '
                'it does not exit Pac-Man.'
            )

            print(
                'Broker actions: '
                'coin=' + coin + ', start=' + start
            )

            keys = {
                'c': coin,
                '1': start,
                'w': 'UP',
                'a': 'LEFT',
                's': 'DOWN',
                'd': 'RIGHT'
            }

            arrows = {
                'H': 'UP',
                'K': 'LEFT',
                'P': 'DOWN',
                'M': 'RIGHT'
            }

            while True:
                key = msvcrt.getwch()

                if key.lower() == 'q' or key == '\x03':
                    break

                if key.lower() == 'p':
                    if retroarch_mode:
                        send_retroarch_command(
                            args.host,
                            'PAUSE_TOGGLE'
                        )
                    else:
                        print(
                            'Pause is not mapped for standalone MAME.'
                        )

                    continue

                if key in ('\x00', '\xe0'):
                    action = arrows.get(
                        msvcrt.getwch()
                    )
                else:
                    action = keys.get(
                        key.lower()
                    )

                if action:
                    tap(action)

    except (
        OSError,
        ValueError,
        RuntimeError,
        paramiko.SSHException
    ) as exc:
        print('ERROR:', repr(exc), file=sys.stderr)
        return 1

    finally:
        if args.command != 'reboot':
            try:
                send(
                    args.host,
                    8765,
                    {'op': 'release_all'}
                )
            except OSError:
                pass

        ssh.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())