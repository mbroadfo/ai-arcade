#!/usr/bin/env python3
"""Deploy and install the AI Arcade Pi runtime over SSH."""
import argparse
from pathlib import Path
import posixpath
import sys

import paramiko
from gamelib import DEFAULT_PI_HOST

FILES = [
    'es_state/ArcadeState.h',
    'es_state/patch_source.py',
    'es_state/install_state.py',
    'es_state/read_state.py',
    'es_state/read_catalog.py',
    'controller_broker.py',
    'install.py',
    'verify.py',
    'patch_es_input.py',
    'requirements.txt',
    'systemd/ai-arcade-controller.service',
    'retropie/AI Arcade Player 1.cfg',
    'retropie/AI Arcade Player 2.cfg',
]


def mkdir_p(sftp, path):
    parts = []
    while path not in ('', '/'):
        parts.append(path)
        path = posixpath.dirname(path)
    for item in reversed(parts):
        try:
            sftp.stat(item)
        except IOError:
            sftp.mkdir(item)


def run(ssh, command, check=True):
    print('remote>', command)
    transport = ssh.get_transport()
    channel = transport.open_session()
    channel.set_combine_stderr(True)
    channel.exec_command(command)
    # Drain merged output continuously, including long compiler output.
    stdout = channel.makefile('rb')
    for line in stdout:
        print(line.decode('utf-8', errors='replace'), end='', flush=True)
    code = channel.recv_exit_status()
    stdout.close()
    channel.close()
    if check and code != 0:
        raise RuntimeError('remote command failed with exit code %d' % code)
    return code


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(errors='backslashreplace')
    p = argparse.ArgumentParser(description='Install AI Arcade runtime on RetroPie')
    p.add_argument('--host', default=DEFAULT_PI_HOST)
    p.add_argument('--user', default='pi')
    p.add_argument('--key', default=str(Path.home() / '.ssh' / 'id_rsa'))
    p.add_argument('--port', type=int, default=22)
    p.add_argument('--timeout', type=float, default=30, help='Pi readiness retry window in seconds')
    es_options = p.add_mutually_exclusive_group()
    es_options.add_argument('--with-es-state', action='store_true', help='Build and activate structured ES observation')
    es_options.add_argument('--restore-es', action='store_true', help='Restore the saved original ES binary')
    args = p.parse_args()
    if not 0 <= args.timeout <= 600:
        p.error('--timeout must be between 0 and 600 seconds')

    repo = Path(__file__).resolve().parents[1]
    source = repo / 'pi'
    missing = [f for f in FILES if not (source / f).exists()]
    if missing:
        raise SystemExit('Missing repository files: ' + ', '.join(missing))

    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    print('Connecting to {}@{}...'.format(args.user, args.host))
    ssh.connect(args.host, port=args.port, username=args.user,
                key_filename=str(Path(args.key).expanduser()), timeout=10)

    remote_root = '/tmp/ai-arcade-install'
    try:
        sftp = ssh.open_sftp()
        try:
            mkdir_p(sftp, remote_root)
            for rel in FILES:
                remote = posixpath.join(remote_root, rel)
                mkdir_p(sftp, posixpath.dirname(remote))
                print('upload>', rel)
                sftp.put(str(source / rel), remote)
        finally:
            sftp.close()

        try:
            if args.restore_es:
                run(ssh, 'sudo /usr/bin/python3 {}/es_state/install_state.py --rollback'.format(remote_root))
                return 0
            run(ssh, 'sudo /usr/bin/python3 {0}/install.py --source {0} --timeout {1}'.format(
                remote_root, args.timeout))
            if args.with_es_state:
                run(ssh, 'sudo /usr/bin/python3 {}/es_state/install_state.py'.format(remote_root))
        except Exception:
            for command in (
                'sudo systemctl status ai-arcade-controller.service --no-pager --full',
                'sudo journalctl -u ai-arcade-controller.service -b -n 100 --no-pager',
                'tail -n 80 /opt/retropie/configs/all/emulationstation/es_log.txt',
            ):
                try:
                    run(ssh, command, check=False)
                except Exception as exc:
                    print('Could not collect diagnostics:', exc, file=sys.stderr)
            raise
    finally:
        ssh.close()

    print('\nDeployment and verification complete.')
    print('Broker endpoint: {}:8765'.format(args.host))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
