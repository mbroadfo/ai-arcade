#!/usr/bin/env python3
import argparse
import os
import sys

import paramiko


START = 0x6F08F000
END = 0x6FD03000


REMOTE_SCRIPT = r'''
import os
import sys

pid_text = os.popen("pgrep -n retroarch").read().strip()
if not pid_text:
    raise SystemExit("retroarch not running")

pid = int(pid_text)
start = {start}
end = {end}
size = end - start
outfile = {outfile!r}

with open(f"/proc/{{pid}}/mem", "rb", buffering=0) as src:
    src.seek(start)
    data = src.read(size)

with open(outfile, "wb") as dst:
    dst.write(data)

print(f"captured {{len(data)}} bytes from PID {{pid}} to {{outfile}}")
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("name", help="snapshot name, e.g. pac-a")
    parser.add_argument("--host", default="192.168.10.155")
    parser.add_argument("--user", default="pi")
    parser.add_argument(
        "--key",
        default=os.path.expanduser("~/.ssh/id_rsa"),
    )
    args = parser.parse_args()

    outfile = f"/tmp/{args.name}.bin"

    script = REMOTE_SCRIPT.format(
        start=START,
        end=END,
        outfile=outfile,
    )

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

        command = "sudo python3 - <<'PY'\n" + script + "\nPY\n"

        stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
        del stdin

        out = stdout.read().decode()
        err = stderr.read().decode()
        code = stdout.channel.recv_exit_status()

        if out:
            print(out, end="")
        if err:
            print(err, file=sys.stderr, end="")

        return code

    finally:
        ssh.close()


if __name__ == "__main__":
    raise SystemExit(main())