"""Supervised evdev/uinput handoff for the speech-only 4x3braille keypad."""

import argparse
from contextlib import ExitStack
import fcntl
from gettext import gettext as _
import os
from pathlib import Path
import select
import signal
import socket
import struct
import subprocess
import time

from legacy_protocol import CaptureStream, KEYS, Router

UNIT = "blazie-bt-keyboard.service"
DIRECTORY = Path("/run/blazie-bt-keyboard")
SOCKET = DIRECTORY / "keys.sock"
READY = DIRECTORY / "ready"
RESTORE = DIRECTORY / "restore"
PATH_UNIT = "brltty@btspeak.path"
BRLTTY = "brltty@-etc-brltty_btspeak.conf.service"
SPEECH = "brltty-external-speech.service"
EVENT = struct.Struct("@llHHi")
GRAB = 0x40044590


def command(*args: str, timeout: int = 8) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout).stdout.strip()


def properties(unit: str) -> dict[str, str]:
    fields = "ActiveState,MainPID,RefuseManualStart,RefuseManualStop,Requires,Triggers,Description"
    output = command("systemctl", "show", "--property=" + fields, unit)
    return dict(line.split("=", 1) for line in output.splitlines() if "=" in line)


def preflight() -> Path:
    from keyboard_backend import native_service_present
    if native_service_present():
        raise OSError(_("The native keyboard server is present; refusing a legacy keyboard handoff."))
    devices = []
    for node in Path("/sys/class/input").glob("event*"):
        if (node / "device/name").read_text().strip() == "4x3braille":
            devices.append(Path("/dev/input") / node.name)
    if (len(devices) != 1 or not Path("/dev/uinput").is_char_device() or
            not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal")):
        raise OSError(_("No supported legacy BT Speak keyboard setup was found."))
    states = {unit: properties(unit) for unit in (PATH_UNIT, BRLTTY, SPEECH)}
    if any(info.get("ActiveState") != "active" for info in states.values()):
        raise OSError(_("The BT Speak keyboard and speech services must be running before starting the emulator."))
    path = states[PATH_UNIT]
    if (path.get("RefuseManualStart") != "no" or
            any(states[unit].get("RefuseManualStop") != "no" for unit in (PATH_UNIT, BRLTTY)) or
            BRLTTY not in path.get("Requires", "").split() or BRLTTY not in path.get("Triggers", "").split()):
        raise OSError(_("The installed BRLTTY services do not support this keyboard handoff."))
    return devices[0]


def wait_for_services() -> None:
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if all(properties(unit).get("ActiveState") == "active" for unit in (PATH_UNIT, BRLTTY, SPEECH)):
            return
        time.sleep(.1)
    raise OSError(_("BT Speak keyboard service restoration did not finish."))


def recover() -> None:
    if os.geteuid() != 0 or not os.environ.get("INVOCATION_ID"):
        raise OSError("Keyboard recovery requires the systemd supervisor")
    if not RESTORE.exists():
        return
    try:
        command("systemctl", "stop", PATH_UNIT, BRLTTY)
    finally:
        # The instance refuses manual starts; its path unit owns restarting it.
        command("systemctl", "start", PATH_UNIT)
    wait_for_services()
    RESTORE.unlink()


def key_bits(fd: int, request: int) -> set[int]:
    data = bytearray(96)
    fcntl.ioctl(fd, request, data, True)
    return {code for code in range(len(data) * 8) if data[code // 8] & (1 << (code % 8))}


def new_virtual(physical: int) -> tuple[int, str]:
    identity = bytearray(8)
    fcntl.ioctl(physical, 0x80084502, identity, True)  # EVIOCGID
    fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        fcntl.ioctl(fd, 0x40045564, 1)  # UI_SET_EVBIT(EV_KEY)
        for key in KEYS:
            fcntl.ioctl(fd, 0x40045565, key)  # UI_SET_KEYBIT
        setup = struct.pack("@HHHH80sI", *struct.unpack("@HHHH", identity), b"Blazie emulator keypad", 0)
        fcntl.ioctl(fd, 0x405C5503, setup)  # UI_DEV_SETUP
        fcntl.ioctl(fd, 0x5501)  # UI_DEV_CREATE; closing fd destroys the device
        name = bytearray(64)
        fcntl.ioctl(fd, 0x8040552C, name, True)  # UI_GET_SYSNAME
        sysname = bytes(name).split(b"\0", 1)[0].decode("ascii")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            for node in (Path("/sys/devices/virtual/input") / sysname).glob("event*"):
                event = Path("/dev/input") / node.name
                if event.exists():
                    return fd, str(event)
            time.sleep(.05)
        raise OSError("Virtual keypad did not appear")
    except BaseException:
        os.close(fd)
        raise


def adopted(event_path: str) -> bool:
    pid = properties(BRLTTY).get("MainPID", "0")
    for entry in (Path("/proc") / pid / "fd").glob("*"):
        try:
            if os.readlink(entry) == event_path:
                return True
        except OSError:
            pass
    return False


def emit(fd: int, frame) -> None:
    packet = b"".join(EVENT.pack(0, 0, *event) for event in frame)
    if packet and os.write(fd, packet) != len(packet):
        raise OSError("Incomplete virtual-keypad write")


def returned_to_editor(tty: str) -> bool:
    if not tty.startswith("/dev/tty") or not tty[8:].isdigit() or tty == "/dev/tty1":
        return False
    with open("/dev/tty0", "rb", buffering=0) as console:
        data = bytearray(6)
        fcntl.ioctl(console, 0x5603, data, True)  # VT_GETSTATE
        return struct.unpack("HHH", data)[0] == 1


def serve(owner: int, uid: int, token: str) -> None:
    if os.geteuid() != 0 or not os.environ.get("INVOCATION_ID") or properties(UNIT).get("MainPID") != str(os.getpid()):
        raise OSError("Keyboard bridge requires its systemd supervisor")
    with ExitStack() as stack:
        owner_fd = os.pidfd_open(owner)
        stack.callback(os.close, owner_fd)
        if select.select([owner_fd], [], [], 0)[0] or Path("/proc", str(owner)).stat().st_uid != uid:
            raise OSError("Emulator owner is no longer available")
        tty = os.readlink(Path("/proc", str(owner), "fd/0"))
        device = preflight()
        physical = os.open(device, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        stack.callback(os.close, physical)
        name = bytearray(256)
        fcntl.ioctl(physical, 0x81004506, name, True)  # EVIOCGNAME
        if bytes(name).split(b"\0", 1)[0] != b"4x3braille" or key_bits(physical, 0x80604521) != KEYS:
            raise OSError("The physical keypad does not match the supported layout")
        if key_bits(physical, 0x80604518):  # EVIOCGKEY
            raise OSError(_("Release all keypad keys before starting the emulator."))
        # ExecStopPost must restore even if this process dies in the following handoff.
        RESTORE.touch(mode=0o600)
        command("systemctl", "stop", PATH_UNIT, BRLTTY)
        fcntl.ioctl(physical, GRAB, 1)
        if key_bits(physical, 0x80604518):
            raise OSError(_("A key was pressed during setup. Release the keys and try again."))
        virtual, event_path = new_virtual(physical)
        stack.callback(os.close, virtual)
        command("systemctl", "start", PATH_UNIT)
        wait_for_services()
        deadline = time.monotonic() + 3
        while not adopted(event_path):
            if time.monotonic() >= deadline:
                raise OSError("BRLTTY did not open the emulator keypad")
            time.sleep(.1)
        server = stack.enter_context(socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET))
        server.bind(str(SOCKET))
        os.chown(SOCKET, uid, -1)
        os.chmod(SOCKET, 0o600)
        server.listen(1)
        router = Router()
        stream = CaptureStream(router, uid, owner)
        stack.callback(stream.drop)
        READY.write_text(token)
        signalled = False
        while True:
            readers = [owner_fd, physical, server]
            if stream.client is not None:
                readers.append(stream.client)
            ready, _writable, _failed = select.select(readers, [], [], .1)
            if owner_fd in ready:
                return
            if stream.client is not None and stream.client in ready:
                stream.readable()
            if server in ready:
                stream.accept(server)
            if physical in ready:
                data = os.read(physical, EVENT.size * 64)
                if not data:
                    raise OSError("Physical keypad disconnected")
                for _sec, _usec, kind, code, value in EVENT.iter_unpack(data):
                    routed = router.feed((kind, code, value))
                    if routed is not None:
                        mode, frame = routed
                        if mode == "pass":
                            emit(virtual, frame)
                        else:
                            stream.frame(frame)
                        stream.advance()
            if stream.used and router.mode == "pass" and not signalled and returned_to_editor(tty):
                # Older deep-escape helpers can return to VT1 without terminating apps on other VTs.
                # Signal through the pidfd so PID reuse can never target an unrelated process.
                signal.pidfd_send_signal(owner_fd, signal.SIGTERM)
                signalled = True


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "recover"))
    parser.add_argument("--owner", type=int)
    parser.add_argument("--uid", type=int)
    parser.add_argument("--token")
    args = parser.parse_args(argv)
    if args.action == "recover":
        recover()
    else:
        if args.owner is None or args.uid is None or not args.token:
            parser.error("Missing bridge owner")
        serve(args.owner, args.uid, args.token)
    return 0
