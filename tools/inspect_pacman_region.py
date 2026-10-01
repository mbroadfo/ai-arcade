#!/usr/bin/env python3
import argparse
import os
import paramiko


def read_remote(ssh, name):
    _, out, err = ssh.exec_command(f"sudo cat /tmp/{name}.bin", timeout=30)
    data = out.read()
    if out.channel.recv_exit_status():
        raise RuntimeError(err.read().decode())
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("first")
    parser.add_argument("second")
    parser.add_argument("--start", type=lambda x: int(x, 0), default=0x003B7000)
    parser.add_argument("--size", type=lambda x: int(x, 0), default=0x800)
    parser.add_argument("--host", default="192.168.10.155")
    parser.add_argument("--user", default="pi")
    parser.add_argument("--key", default=os.path.expanduser("~/.ssh/id_rsa"))
    args = parser.parse_args()

    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(
        args.host,
        username=args.user,
        key_filename=args.key,
        timeout=10
    )

    try:
        a = read_remote(ssh, args.first)
        b = read_remote(ssh, args.second)

        end = args.start + args.size

        print(f"Region 0x{args.start:08x}-0x{end-1:08x}")
        print()

        count = 0

        for offset in range(args.start, end):
            if a[offset] != b[offset]:
                print(
                    f"0x{offset:08x}  "
                    f"0x{a[offset]:02x} -> 0x{b[offset]:02x}"
                )
                count += 1

        print()
        print(f"changed bytes: {count}")

    finally:
        ssh.close()


if __name__ == "__main__":
    main()