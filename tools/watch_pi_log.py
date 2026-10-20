"""Stream the Pi's kernel log to a local file until the connection drops, so the last lines survive if the Pi crashes or
reboots (its journal is not kept across boots). Read-only.

    python tools/watch_pi_log.py OUT.txt [--host ADDRESS]
"""
import argparse
import sys
import time

import paramiko

from gamelib import DEFAULT_PI_HOST


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--host", default=DEFAULT_PI_HOST)
    args = parser.parse_args()
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.connect(args.host, username="pi", timeout=10)
    transport = ssh.get_transport()
    transport.set_keepalive(2)
    _, out, _ = ssh.exec_command("sudo dmesg -w --time-format iso 2>&1; echo STREAM-ENDED", timeout=0)
    with open(args.out, "w", encoding="utf-8", buffering=1) as f:
        f.write(f"# started {time.strftime('%H:%M:%S')}\n")
        try:
            for line in out:
                f.write(line)
        except Exception as exc:  # the connection dropped: the Pi went away
            f.write(f"# stream lost {time.strftime('%H:%M:%S')}: {exc}\n")
        else:
            f.write(f"# stream closed {time.strftime('%H:%M:%S')}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
