"""Frontend client and lifetime of the supervised legacy keyboard bridge."""

from gettext import gettext as _
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import time
from types import SimpleNamespace
import uuid

from legacy_bridge import READY, SOCKET, UNIT, properties

FLAG_EXCLUSIVE = 1
FLAG_WANT_RAW = 2
BTB_DOT1 = 497
BTB_SPACE = 57
BTB_L2, BTB_L3, BTB_R2, BTB_R3 = 257, 258, 260, 261


def helper_command() -> list[str]:
    # The same entry point works in the source tree and in the relocatable zipapp.
    return [sys.executable, "-B", str(Path(sys.argv[0]).resolve()), "--bt-keyboard"]


def privileged(command: list[str]) -> list[str]:
    return command if os.geteuid() == 0 else ["sudo", "-n", *command]


class Session:
    def __init__(self):
        self.token = uuid.uuid4().hex
        self.description = "Blazie keyboard " + self.token

    def __enter__(self):
        helper = helper_command()
        args = ["systemd-run", "--unit=" + UNIT, "--collect", "--description=" + self.description,
                "--property=Type=exec", "--property=RuntimeMaxSec=infinity", "--property=TimeoutStopSec=45s",
                "--property=KillMode=control-group", "--property=Restart=no",
                "--property=RuntimeDirectory=blazie-bt-keyboard", "--property=RuntimeDirectoryMode=0711",
                "--property=ExecStopPost=" + shlex.join([*helper, "recover"]),
                *helper, "run", "--owner", str(os.getpid()), "--uid", str(os.getuid()), "--token", self.token]
        try:
            result = subprocess.run(privileged(args), capture_output=True, text=True, timeout=15, check=False)
            if result.returncode:
                raise OSError(_("Could not start legacy keyboard access: {error}").format(error=result.stderr.strip()))
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                try:
                    if READY.read_text() == self.token:
                        return sys.modules[__name__]
                except FileNotFoundError:
                    pass
                if properties(UNIT).get("ActiveState") not in ("active", "activating"):
                    break
                time.sleep(.1)
            raise OSError(_("Legacy keyboard setup failed. Release all keys and retry; details are in the system journal "
                            "for blazie-bt-keyboard.service."))
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        # A concurrent launch must never stop another emulator's bridge.
        info = properties(UNIT)
        if info.get("Description") == self.description:
            subprocess.run(privileged(["systemctl", "stop", UNIT]), capture_output=True, text=True, timeout=55, check=True)

    def __exit__(self, *error):
        self.close()


class Connection:
    def __init__(self):
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        try:
            self.socket.settimeout(10)
            self.socket.connect(str(SOCKET))
            if self.receive() != {"ready": True}:
                raise OSError(_("Legacy keyboard capture was not ready."))
            self.socket.settimeout(None)
        except BaseException:
            self.socket.close()
            raise

    def receive(self) -> dict:
        data = self.socket.recv(512)
        if not data:
            raise OSError(_("The legacy keyboard bridge disconnected."))
        return json.loads(data)

    def fileno(self) -> int:
        return self.socket.fileno()

    def read_key(self):
        message = self.receive()
        return SimpleNamespace(key=message["key"], state=message["state"])

    def ack_consume(self) -> None:
        pass  # This protocol has only an exclusive consumer; no platform ACK is needed.

    def __enter__(self):
        return self

    def __exit__(self, *error):
        try:
            deadline = time.monotonic() + 3
            self.socket.settimeout(3)
            self.socket.sendall(b"release")
            while time.monotonic() < deadline:
                self.socket.settimeout(max(.001, deadline - time.monotonic()))
                if self.receive() == {"released": True}:
                    return
            raise OSError(_("Legacy keyboard release timed out."))
        except OSError:
            if error[0] is None:
                raise
        finally:
            self.socket.close()


def connect(flags: int) -> Connection:
    if flags != FLAG_EXCLUSIVE | FLAG_WANT_RAW:
        raise ValueError("Only exclusive raw capture is supported")
    return Connection()
