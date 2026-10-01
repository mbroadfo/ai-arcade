#!/usr/bin/env python3
import argparse
import os
import sys

import paramiko


WINDOW = 0x400


def read_remote_file(ssh, path):
    command = f"sudo cat {path}"
    _, stdout, stderr = ssh.exec_command(command, timeout=30)

    data = stdout.read()
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()

    if code != 0:
        raise RuntimeError(err or f"failed to read {path}")

    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("first")
    parser.add_argument("second")
    parser.add_argument("--host", default="192.168.10.155")
    parser.add_argument("--user", default="pi")
    parser.add_argument(
        "--key",
        default=os.path.expanduser("~/.ssh/id_rsa"),
    )
    parser.add_argument("--top", type=int, default=30)
    args = parser.parse_args()

    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())

    try:
        ssh.connect(
            args.host,
            username=args.user,
            key_filename=args.key,
            timeout=10,
        )

        a = read_remote_file(ssh, f"/tmp/{args.first}.bin")
        b = read_remote_file(ssh, f"/tmp/{args.second}.bin")

        if len(a) != len(b):
            raise RuntimeError("snapshot sizes differ")

        candidates = []

        for start in range(0, len(a) - WINDOW + 1, WINDOW):
            changed = sum(
                1 for x, y in zip(
                    a[start:start + WINDOW],
                    b[start:start + WINDOW]
                )
                if x != y
            )

            if changed:
                candidates.append((changed, start))

        candidates.sort()

        print(f"snapshot size: {len(a)} bytes")
        print(f"top quiet 1KB regions with changes:")
        print()

        for changed, start in candidates[:args.top]:
            print(
                f"offset 0x{start:08x} "
                f"changed={changed:4d}/{WINDOW}"
            )

        return 0

    except (
        OSError,
        RuntimeError,
        paramiko.SSHException,
    ) as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1

    finally:
        ssh.close()


if __name__ == "__main__":
    raise SystemExit(main())