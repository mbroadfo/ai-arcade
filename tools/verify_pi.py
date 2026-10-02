#!/usr/bin/env python3
"""Run the installed AI Arcade verifier on the RetroPie Pi over SSH."""
import argparse
from pathlib import Path
import sys

import paramiko
from gamelib import DEFAULT_PI_HOST


def main():
    p = argparse.ArgumentParser(description='Verify AI Arcade Pi installation')
    p.add_argument('--host', default=DEFAULT_PI_HOST)
    p.add_argument('--user', default='pi')
    p.add_argument('--key', default=str(Path.home() / '.ssh' / 'id_rsa'))
    p.add_argument('--port', type=int, default=22)
    p.add_argument('--timeout', type=float, default=30, help='Pi readiness retry window in seconds')
    args = p.parse_args()
    if not 0 <= args.timeout <= 600:
        p.error('--timeout must be between 0 and 600 seconds')

    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(args.host, port=args.port, username=args.user,
                key_filename=str(Path(args.key).expanduser()), timeout=10)
    try:
        _, stdout, stderr = ssh.exec_command(
            'sudo /usr/bin/python3 /opt/ai-arcade/verify.py --timeout {}'.format(args.timeout))
        out = stdout.read().decode('utf-8', errors='replace')
        err = stderr.read().decode('utf-8', errors='replace')
        code = stdout.channel.recv_exit_status()
    finally:
        ssh.close()

    if out:
        print(out, end='' if out.endswith('\n') else '\n')
    if err:
        print(err, end='' if err.endswith('\n') else '\n', file=sys.stderr)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
