import argparse
import paramiko


def run(ssh, command):
    _, out, err = ssh.exec_command(command, timeout=20)
    stdout = out.read().decode()
    stderr = err.read().decode()
    code = out.channel.recv_exit_status()

    if code != 0:
        raise RuntimeError(stderr or stdout)

    return stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.10.155")
    parser.add_argument("--user", default="pi")
    parser.add_argument("--key", default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())

    connect_args = {
        "hostname": args.host,
        "username": args.user,
        "timeout": 10,
    }

    if args.key:
        connect_args["key_filename"] = args.key

    ssh.connect(**connect_args)

    try:
        run(
            ssh,
            "pkill -9 -x mame || true"
        )

        command = (
            "nohup mame pacman "
            "-rompath /home/pi/RetroPie/roms/arcade "
            "-sound none "
            "-video accel "
            "-nowindow "
            "-skip_gameinfo "
            "-joystick "
            "-joystickprovider sdl "
            "-ctrlrpath /home/pi/.mame/ctrlr -ctrlr aiarcade "        )

        if args.verbose:
            command += "-verbose "

        command += "> /tmp/ai-arcade-mame.log 2>&1 < /dev/null &"

        run(ssh, command)

        print("MAME restarted.")
        print("Log: /tmp/ai-arcade-mame.log")

    finally:
        ssh.close()


if __name__ == "__main__":
    main()