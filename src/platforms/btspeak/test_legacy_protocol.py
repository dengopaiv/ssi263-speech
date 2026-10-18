"""Raw socket delivery and complete-chord routing, without physical hardware."""
import json
import os
import socket
import tempfile
import unittest

from legacy_protocol import Router, CaptureStream
from keymap import ChordKeyboard, SPACE


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.path = self.directory.name + '/raw.sock'
        self.server.bind(self.path)
        self.server.listen(2)
        self.router = Router()
        self.stream = CaptureStream(self.router, os.getuid(), os.getpid())
        self.client = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.client.settimeout(0.1)
        self.client.connect(self.path)

    def tearDown(self):
        self.stream.drop()
        self.client.close()
        self.server.close()
        self.directory.cleanup()

    def feed(self, code, value):
        self.router.feed((1, code, value))
        mode, frame = self.router.feed((0, 0, 0))
        if mode == 'capture':
            self.stream.frame(frame)
        self.stream.advance()
        return mode

    def receive(self):
        return json.loads(self.client.recv(512))

    def test_handshake_waits_for_host_chord_release(self):
        self.feed(57, 1)
        self.stream.accept(self.server)
        with self.assertRaises(TimeoutError):
            self.receive()
        self.assertEqual(self.feed(57, 0), 'pass')
        self.assertEqual(self.receive(), {'ready': True})
        self.feed(497, 1)
        self.assertEqual(self.receive(), {'key': 497, 'state': True})

    def test_raw_e_chord_reaches_original_keyboard(self):
        self.stream.accept(self.server)
        self.receive()
        keyboard = ChordKeyboard({57: SPACE, **{497+i: 1 << i for i in range(8)}})
        for code, value in ((57, 1), (497, 1), (501, 1), (497, 0), (501, 0), (57, 0)):
            self.feed(code, value)
            event = self.receive()
            action = keyboard.feed(event['key'], event['state'])
        self.assertEqual(action.chord, 0x51)  # firmware space + dots 1 and 5
        self.assertFalse(action.menu)

    def test_clean_release_ack_precedes_host_menu(self):
        self.stream.accept(self.server)
        self.receive()
        self.client.sendall(b'release')
        self.stream.readable()
        self.assertEqual(self.receive(), {'released': True})
        self.assertEqual(self.router.mode, 'pass')
        self.assertEqual(self.client.recv(512), b'')

    def test_disconnect_keeps_incomplete_chord_out_of_host(self):
        self.stream.accept(self.server)
        self.receive()
        self.feed(497, 1)
        self.client.close()
        self.stream.readable()
        self.assertEqual(self.router.mode, 'capture')
        self.assertEqual(self.feed(497, 0), 'capture')
        self.assertEqual(self.router.mode, 'pass')

    def test_second_client_cannot_steal_capture(self):
        self.stream.accept(self.server)
        self.receive()
        with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as other:
            other.settimeout(0.1)
            other.connect(self.path)
            self.stream.accept(self.server)
            self.assertEqual(other.recv(512), b'')
        self.feed(497, 1)
        self.assertEqual(self.receive()['key'], 497)

    def test_backpressure_disconnects_instead_of_blocking(self):
        self.stream.accept(self.server)
        self.receive()
        self.stream.client.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024)
        for _index in range(10000):
            if not self.stream.send({'key': 497, 'state': True}):
                break
        self.assertIsNone(self.stream.client)
        self.assertEqual(self.router.mode, 'pass')

if __name__ == "__main__":
    unittest.main()
