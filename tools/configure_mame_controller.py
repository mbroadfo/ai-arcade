import os
import paramiko

HOST = "192.168.10.155"
USER = "pi"
KEY = os.path.expanduser("~/.ssh/id_rsa")

CFG = """<?xml version="1.0"?>
<mameconfig version="10">
    <system name="default">
        <input>

            <mapdevice device="AIArcadePlayer1" controller="JOYCODE_1" />

            <port type="COIN1">
                <newseq type="standard">JOYCODE_1_SELECT</newseq>
            </port>

            <port type="START1">
                <newseq type="standard">JOYCODE_1_START</newseq>
            </port>

            <port type="P1_JOYSTICK_UP">
                <newseq type="standard">JOYCODE_1_YAXIS_UP_SWITCH</newseq>
            </port>

            <port type="P1_JOYSTICK_DOWN">
                <newseq type="standard">JOYCODE_1_YAXIS_DOWN_SWITCH</newseq>
            </port>

            <port type="P1_JOYSTICK_LEFT">
                <newseq type="standard">JOYCODE_1_XAXIS_LEFT_SWITCH</newseq>
            </port>

            <port type="P1_JOYSTICK_RIGHT">
                <newseq type="standard">JOYCODE_1_XAXIS_RIGHT_SWITCH</newseq>
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

    sftp.close()
    print("Wrote:", path)

finally:
    ssh.close()