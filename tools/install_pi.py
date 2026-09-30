#!/usr/bin/env python3
"""Deploy and install the AI Arcade Pi runtime over SSH."""
import argparse
from pathlib import Path
import posixpath
import sys

import paramiko

FILES = [
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
    stdin, stdout, stderr = ssh.exec_command(command)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    code = stdout.channel.recv_exit_status()
    if out:
        print(out, end='' if out.endswith('\n') else '\n')
    if err:
        print(err, end='' if err.endswith('\n') else '\n', file=sys.stderr)
    if check and code != 0:
        raise RuntimeError('remote command failed with exit code %d' % code)
    return code


def main():
    p = argparse.ArgumentParser(description='Install AI Arcade runtime on RetroPie')
    p.add_argument('--host', default='192.168.10.155')
    p.add_argument('--user', default='pi')
    p.add_argument('--key', default=str(Path.home() / '.ssh' / 'id_rsa'))
    p.add_argument('--port', type=int, default=22)
    p.add_argument('--timeout', type=float, default=30, help='Pi readiness retry window in seconds')
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
            run(ssh, 'sudo /usr/bin/python3 {0}/install.py --source {0} --timeout {1}'.format(
                remote_root, args.timeout))
        except Exception:
            for command in (
                'sudo systemctl status ai-arcade-controller.service --no-pager --full',
                'sudo journalctl -u ai-arcade-controller.service -b -n 100 --no-pager',
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
