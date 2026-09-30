#!/usr/bin/env python3
"""Retrieve structured live EmulationStation state over SSH."""
import argparse
from pathlib import Path
import sys
import paramiko
import json


def fetch(ssh):
    _, stdout, stderr = ssh.exec_command('/usr/bin/python3 /opt/ai-arcade/es-state/read_state.py', timeout=15)
    output = stdout.read().decode('utf-8')
    error = stderr.read().decode('utf-8')
    code = stdout.channel.recv_exit_status()
    if code:
        raise RuntimeError(output.strip() or error.strip())
    return json.loads(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='192.168.10.155')
    parser.add_argument('--user', default='pi')
    parser.add_argument('--key', default=str(Path.home() / '.ssh' / 'id_rsa'))
    parser.add_argument('--port', type=int, default=22)
    args = parser.parse_args()
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        ssh.connect(args.host, port=args.port, username=args.user,
                    key_filename=str(Path(args.key).expanduser()), timeout=10)
        print(json.dumps(fetch(ssh), indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, paramiko.SSHException) as exc:
        print('ERROR:', exc, file=sys.stderr)
        return 1
    finally:
        ssh.close()


if __name__ == '__main__':
    sys.exit(main())
