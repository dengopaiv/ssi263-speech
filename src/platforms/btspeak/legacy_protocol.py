"""Chord-boundary routing and a single exclusive consumer for the legacy keypad."""

import json
import socket
import struct

KEYS = {57, *range(497, 505)}


class Router:
    def __init__(self):
        self.mode = "pass"
        self.pending = None
        self.held: set[int] = set()
        self.frame: list[tuple[int, int, int]] = []

    def request(self, mode: str) -> None:
        if mode not in ("pass", "capture"):
            raise ValueError("Unknown input mode")
        self.pending = mode if mode != self.mode else None
        self._switch()

    def _switch(self) -> None:
        if self.pending and not self.held and not self.frame:
            self.mode, self.pending = self.pending, None

    def feed(self, event: tuple[int, int, int]):
        kind, code, value = event
        if kind == 0 and code == 3:
            raise OSError("Lost input events (SYN_DROPPED)")
        if kind == 1 and code in KEYS:
            self.frame.append(event)
            if value == 1:
                self.held.add(code)
            elif value == 0:
                self.held.discard(code)
            if len(self.frame) > 256:
                raise OSError("Input frame exceeded its size limit")
        elif kind == 0 and code == 0:
            frame = self.frame + [(0, 0, 0)] if self.frame else []
            mode = self.mode
            self.frame = []
            self._switch()
            return mode, frame
        return None


class CaptureStream:
    def __init__(self, router: Router, uid: int, pid: int):
        self.router = router
        self.uid = uid
        self.pid = pid
        self.client = None
        self.started = False
        self.releasing = False
        self.used = False

    def accept(self, server) -> None:
        client, _address = server.accept()
        client.setblocking(False)
        pid, uid, _gid = struct.unpack("3i", client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if (pid, uid) != (self.pid, self.uid) or self.client is not None or self.router.mode != "pass" or self.router.pending:
            client.close()
            return
        self.client = client
        self.started = self.releasing = False
        self.used = True
        self.router.request("capture")
        self.advance()

    def send(self, message: dict) -> bool:
        if self.client is None:
            return False
        try:
            packet = json.dumps(message).encode("ascii")
            if self.client.send(packet) != len(packet):
                raise OSError("Incomplete key packet")
            return True
        except OSError:
            # A slow or disconnected consumer loses the connection, never individual keys silently.
            self.drop()
            return False

    def advance(self) -> None:
        if self.client is None:
            return
        if self.releasing:
            if self.router.mode == "pass" and self.router.pending is None:
                self.send({"released": True})
                self.drop()
        elif not self.started and self.router.mode == "capture" and not self.router.held:
            self.started = self.send({"ready": True})

    def frame(self, events) -> None:
        if self.started and not self.releasing:
            for kind, code, value in events:
                if kind == 1 and value in (0, 1):
                    if not self.send({"key": code, "state": bool(value)}):
                        break

    def readable(self) -> None:
        try:
            request = self.client.recv(64)
        except BlockingIOError:
            return
        except OSError:
            request = b""
        if request == b"release":
            self.releasing = True
            self.router.request("pass")
            self.advance()
        else:
            self.drop()

    def drop(self) -> None:
        if self.client is not None:
            self.client.close()
        self.client = None
        self.started = self.releasing = False
        self.router.request("pass")
