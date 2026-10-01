import argparse
import os

import paramiko


PACMAN_CFG = """<?xml version="1.0"?>
<mameconfig version="10">
    <system name="pacman">
        <input>
            <port tag=":IN0" type="P1_JOYSTICK_UP" mask="1" defvalue="1">
                <newseq type="standard">
                    JOYCODE_1_YAXIS_UP_SWITCH
                </newseq>
            </port>

            <port tag=":IN0" type="P1_JOYSTICK_LEFT" mask="2" defvalue="2">
                <newseq type="standard">
                    JOYCODE_1_XAXIS_LEFT_SWITCH
                </newseq>
            </port>

            <port tag=":IN0" type="P1_JOYSTICK_RIGHT" mask="4" defvalue="4">
                <newseq type="standard">
                    JOYCODE_1_XAXIS_RIGHT_SWITCH
                </newseq>
            </port>

            <port tag=":IN0" type="P1_JOYSTICK_DOWN" mask="8" defvalue="8">
                <newseq type="standard">
                    JOYCODE_1_YAXIS_DOWN_SWITCH
                </newseq>
            </port>

            <port tag=":IN1" type="COIN1" mask="32" defvalue="32">
                <newseq type="standard">
                    JOYCODE_1_BUTTON9
                </newseq>
            </port>

            <port tag=":IN1" type="START1" mask="64" defvalue="64">
                <newseq type="standard">
                    JOYCODE_1_BUTTON10
                </newseq>
            </port>
        </input>
    </system>
</mameconfig>
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.10.155")
    parser.add_argument("--user", default="pi")
    parser.add_argument(
        "--key",
        default=os.path.expanduser("~/.ssh/id_rsa")
    )
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
        sftp = ssh.open_sftp()

        try:
            sftp.mkdir("/home/pi/.mame")
        except OSError:
            pass

        try:
            sftp.mkdir("/home/pi/.mame/cfg")
        except OSError:
            pass

        path = "/home/pi/.mame/cfg/pacman.cfg"

        with sftp.file(path, "w") as f:
            f.write(PACMAN_CFG)

        sftp.close()

        print("Wrote:", path)

    finally:
        ssh.close()


if __name__ == "__main__":
    main()