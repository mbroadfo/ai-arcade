"""The Observatory's line to the cabinet: pi/cabinet/cabinet.py over one kept SSH connection (tools/install_cabinet.py).

Every call returns the script's JSON, or raises CabinetError with what went wrong; the connection is made again when
it drops. Thread-safe: the status poller and the page's requests share it.
"""
import json
import shlex
import threading

import paramiko

SCRIPT = "python3 /home/pi/ai-arcade/cabinet/cabinet.py"


class CabinetError(RuntimeError):
    pass


class Cabinet:
    def __init__(self, host, user="pi"):
        self.host, self.user = host, user
        self.ssh = None
        self.lock = threading.Lock()

    def _connect(self):
        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
        ssh.connect(self.host, username=self.user, timeout=5)
        ssh.get_transport().set_keepalive(15)
        return ssh

    def call(self, *args, timeout=30):
        command = " ".join([SCRIPT] + [shlex.quote(a) for a in args])
        with self.lock:
            for attempt in (1, 2):
                try:
                    if self.ssh is None or not self.ssh.get_transport() or not self.ssh.get_transport().is_active():
                        self.ssh = self._connect()
                    _, out, err = self.ssh.exec_command(command, timeout=timeout)
                    text, problem = out.read().decode(), err.read().decode()
                    code = out.channel.recv_exit_status()
                    break
                except (OSError, paramiko.SSHException) as exc:
                    self.ssh = None
                    if attempt == 2:
                        raise CabinetError(f"cannot reach the cabinet at {self.host}: {exc}") from exc
        if code != 0:
            raise CabinetError(problem.strip() or text.strip() or f"cabinet.py {args[0]} failed ({code})")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise CabinetError(f"cabinet.py {args[0]}: unexpected output") from exc

    def status(self):
        return self.call("status", timeout=10)

    def catalog(self):
        return self.call("catalog", timeout=60)

    def launch(self, system, rom):
        return self.call("launch", system, rom)

    def stop(self):
        return self.call("stop")

    def clear(self):
        return self.call("clear")

    def menu(self):
        return self.call("menu")
