"""One-time Pi setup: write the MAME controller profile (aiarcade.cfg) that standalone MAME uses in AI mode.

Maps the cabinet pad to COIN1, START1 and the joystick, and keeps a USB keyboard working alongside it: arrows move,
5 or Right Shift inserts a coin, 1 or Enter starts (MAME's own keys, plus RetroArch's). Safe to re-run. Does not touch
human mode.

    python tools/configure_mame_controller.py [--host ADDRESS]
"""
import argparse
import os

import paramiko
from gamelib import DEFAULT_PI_HOST

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--host", default=DEFAULT_PI_HOST)
parser.add_argument("--user", default="pi")
args = parser.parse_args()
HOST, USER = args.host, args.user
KEY = os.path.expanduser("~/.ssh/id_rsa")

# Tokens verified with tools/probe_mame_input.py: button 8 -> BUTTON9, button 9 -> BUTTON10.
CFG = """<?xml version="1.0"?>
<mameconfig version="10">
    <system name="default">
        <input>

            <port type="COIN1">
                <newseq type="standard">JOYCODE_1_BUTTON9 OR KEYCODE_5 OR KEYCODE_RSHIFT</newseq>
            </port>

            <port type="START1">
                <newseq type="standard">JOYCODE_1_BUTTON10 OR KEYCODE_1 OR KEYCODE_ENTER</newseq>
            </port>

            <port type="P1_JOYSTICK_UP">
                <newseq type="standard">JOYCODE_1_YAXIS_UP_SWITCH OR KEYCODE_UP</newseq>
            </port>

            <port type="P1_JOYSTICK_DOWN">
                <newseq type="standard">JOYCODE_1_YAXIS_DOWN_SWITCH OR KEYCODE_DOWN</newseq>
            </port>

            <port type="P1_JOYSTICK_LEFT">
                <newseq type="standard">JOYCODE_1_XAXIS_LEFT_SWITCH OR KEYCODE_LEFT</newseq>
            </port>

            <port type="P1_JOYSTICK_RIGHT">
                <newseq type="standard">JOYCODE_1_XAXIS_RIGHT_SWITCH OR KEYCODE_RIGHT</newseq>
            </port>

        </input>
    </system>
</mameconfig>
"""


ssh = paramiko.SSHClient()
ssh.load_system_host_keys()
ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
ssh.connect(HOST, username=USER, key_filename=KEY)

try:
    sftp = ssh.open_sftp()

    for path in (
        "/home/pi/.mame",
        "/home/pi/.mame/ctrlr",
    ):
        try:
            sftp.mkdir(path)
        except OSError:
            pass

    path = "/home/pi/.mame/ctrlr/aiarcade.cfg"

    with sftp.file(path, "w") as f:
        f.write(CFG)

    # A per-game cfg overrides the controller profile; drop the failed hand-written one.
    try:
        sftp.remove("/home/pi/.mame/cfg/pacman.cfg")
        print("Removed stale /home/pi/.mame/cfg/pacman.cfg")
    except OSError:
        pass

    sftp.close()
    print("Wrote:", path)

finally:
    ssh.close()