"""Recovery guards and hardware resource cleanup using simulated system calls."""

from contextlib import ExitStack
import inspect
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

import legacy_bridge as bridge


class ServeTests(unittest.TestCase):
    """Run the real serve body; only the system/device boundary is simulated."""

    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        directory = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        self.marker = directory / "restore"
        self.ready = directory / "ready"
        self.owner, self.uid = 1234, 1000
        self.owner_fd, self.physical, self.virtual = 101, 102, 103

        def replace(target, name, **kwargs):
            return stack.enter_context(patch.object(target, name, **kwargs))

        stack.enter_context(patch.dict(os.environ, {"INVOCATION_ID": "test"}))
        replace(bridge, "RESTORE", new=self.marker)
        replace(bridge, "READY", new=self.ready)
        replace(bridge, "SOCKET", new=directory / "keys.sock")
        replace(bridge.os, "geteuid", return_value=0)
        replace(bridge, "properties", return_value={"MainPID": str(os.getpid())})
        self.pidfd_open = replace(bridge.os, "pidfd_open", return_value=self.owner_fd)
        replace(bridge, "Path").return_value.stat.return_value = SimpleNamespace(st_uid=self.uid)
        replace(bridge.os, "readlink", return_value="/dev/tty2")
        replace(bridge, "preflight", return_value="/dev/input/fake")
        real_open, real_close = os.open, os.close
        self.close = Mock()

        def open_device(path, *args):
            if path == "/dev/input/fake":
                return self.physical
            self.assertEqual(path, self.marker)
            return real_open(path, *args)  # Keep the recovery marker a real file.

        def close(fd):
            if fd in (self.owner_fd, self.physical, self.virtual):
                self.close(fd)
            else:
                real_close(fd)

        replace(bridge.os, "open", side_effect=open_device)
        replace(bridge.os, "close", side_effect=close)

        def ioctl(fd, request, data, mutate=False):
            if request == 0x81004506:
                data[:len(b"4x3braille\0")] = b"4x3braille\0"

        replace(bridge.fcntl, "ioctl", side_effect=ioctl)
        replace(bridge, "key_bits", side_effect=lambda fd, request: bridge.KEYS if request == 0x80604521 else set())
        self.command = replace(bridge, "command")
        replace(bridge, "new_virtual", return_value=(self.virtual, "/dev/input/virtual"))
        replace(bridge, "wait_for_services")
        replace(bridge, "adopted", return_value=True)
        self.socket = replace(bridge.socket, "socket")
        replace(bridge.os, "chown")
        replace(bridge.os, "chmod")
        self.select = replace(bridge.select, "select")
        # Unexpected reads/signals fail safely instead of touching real file descriptors or processes.
        replace(bridge.os, "read", side_effect=AssertionError("Unexpected physical-device read"))
        replace(bridge.signal, "pidfd_send_signal", side_effect=AssertionError("Unexpected owner signal"))
        self.serve = bridge.serve
        mutation = os.environ.get("BLAZIE_BT_LEGACY_BREAK")
        if mutation:
            # Test-only controls: never add a switch disabling recovery to the shipped helper.
            source = inspect.getsource(bridge.serve)
            if mutation == "late-marker":
                before = '        RESTORE.touch(mode=0o600)\n        command("systemctl", "stop", PATH_UNIT, BRLTTY)'
                after = '        command("systemctl", "stop", PATH_UNIT, BRLTTY)\n        RESTORE.touch(mode=0o600)'
            elif mutation == "ignore-owner":
                before, after = "            if owner_fd in ready:", "            if False:"
            else:
                raise ValueError("Unknown legacy bridge control: " + mutation)
            if source.count(before) != 1:
                raise RuntimeError("Legacy bridge control no longer matches serve()")
            namespace = {}
            exec(compile(source.replace(before, after), "<legacy bridge control>", "exec"), bridge.__dict__, namespace)
            self.serve = namespace["serve"]

    def test_restore_marker_precedes_first_stop(self):
        class SimulatedCrash(Exception):
            pass

        def stop(*args):
            self.assertEqual(args, ("systemctl", "stop", bridge.PATH_UNIT, bridge.BRLTTY))
            self.assertTrue(self.marker.is_file(), "Recovery marker missing before BRLTTY stop")
            raise SimulatedCrash

        self.command.side_effect = stop
        self.select.return_value = ([], [], [])  # Owner alive at startup.
        with self.assertRaises(SimulatedCrash):
            self.serve(self.owner, self.uid, "test")
        self.command.assert_called_once()
        self.assertTrue(self.marker.is_file())  # Still available to ExecStopPost after the failure.
        self.assertEqual(self.close.call_args_list, [call(self.physical), call(self.owner_fd)])

    def test_owner_exit_returns_and_closes_resources(self):
        polls = 0

        def poll(readers, *args):
            nonlocal polls
            polls += 1
            self.assertIn(self.owner_fd, readers, "Owner pidfd is not monitored")
            if polls == 1:
                return [], [], []  # Startup owner check.
            self.assertEqual(polls, 2, "serve() kept polling after owner death")
            self.assertEqual(self.ready.read_text(), "test")  # Reached the live event loop.
            return [self.owner_fd], [], []

        self.select.side_effect = poll
        self.assertIsNone(self.serve(self.owner, self.uid, "test"))
        self.assertEqual(polls, 2)
        self.pidfd_open.assert_called_once_with(self.owner)
        self.assertEqual(self.close.call_args_list, [call(self.virtual), call(self.physical), call(self.owner_fd)])
        self.socket.return_value.__exit__.assert_called_once()


class BridgeTests(unittest.TestCase):
    def test_direct_helper_invocation_cannot_change_services(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(bridge, "command") as command:
            with self.assertRaises(OSError):
                bridge.recover()
            with self.assertRaises(OSError):
                bridge.serve(123, 1000, "test")
        command.assert_not_called()

    def test_preflight_failure_without_handoff_does_not_restart_services(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(bridge, "RESTORE", Path(directory) / "restore"), \
                patch.dict(os.environ, {"INVOCATION_ID": "test"}), patch.object(bridge.os, "geteuid", return_value=0), \
                patch.object(bridge, "command") as command:
            bridge.recover()
        command.assert_not_called()

    def test_recovery_starts_path_even_if_stop_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "restore"
            marker.touch()
            with patch.object(bridge, "RESTORE", marker), patch.dict(os.environ, {"INVOCATION_ID": "test"}), \
                    patch.object(bridge.os, "geteuid", return_value=0), \
                    patch.object(bridge, "command", side_effect=[OSError("stop failed"), ""]) as command:
                with self.assertRaises(OSError):
                    bridge.recover()
            self.assertEqual(command.call_args_list[-1].args, ("systemctl", "start", bridge.PATH_UNIT))
            self.assertTrue(marker.exists())

    def test_successful_recovery_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "restore"
            marker.touch()
            with patch.object(bridge, "RESTORE", marker), patch.dict(os.environ, {"INVOCATION_ID": "test"}), \
                    patch.object(bridge.os, "geteuid", return_value=0), \
                    patch.object(bridge, "command") as command, patch.object(bridge, "wait_for_services"):
                bridge.recover()
                bridge.recover()
            self.assertEqual(command.call_count, 2)
            self.assertFalse(marker.exists())

    def test_virtual_device_is_destroyed_if_setup_fails(self):
        with patch.object(bridge.os, "open", return_value=8), patch.object(bridge.os, "close") as close, \
                patch.object(bridge.fcntl, "ioctl", side_effect=[0, OSError("setup failed")]):
            with self.assertRaises(OSError):
                bridge.new_virtual(7)
        close.assert_called_once_with(8)

    def test_incomplete_event_frame_and_overflow_fail_explicitly(self):
        from legacy_protocol import Router
        with self.assertRaises(OSError):
            Router().feed((0, 3, 0))
        with patch.object(bridge.os, "write", return_value=1):
            with self.assertRaises(OSError):
                bridge.emit(3, [(1, 497, 1), (0, 0, 0)])


def control_main() -> int:
    """Gate marks for assertions; unexpected errors retain their traceback and are rejected."""
    class Result(unittest.TestResult):
        def addSuccess(self, test):
            super().addSuccess(test)
            print("ok " + test._testMethodName)

        def addFailure(self, test, error):
            super().addFailure(test, error)
            print("FAIL " + test._testMethodName + ": " + str(error[1]))

        def addError(self, test, error):
            super().addError(test, error)
            print(self.errors[-1][1])

    result = Result()
    unittest.defaultTestLoader.loadTestsFromTestCase(ServeTests).run(result)
    failures = len(result.failures) + len(result.errors)
    print("legacy serve: {0} of {1} FAILED".format(failures, result.testsRun) if failures else "legacy serve: all passed")
    return int(not result.wasSuccessful())


if __name__ == "__main__":
    if sys.argv[1:] == ["--control"]:
        raise SystemExit(control_main())
    unittest.main()
