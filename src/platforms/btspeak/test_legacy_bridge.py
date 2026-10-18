"""Recovery guards and hardware resource cleanup using simulated system calls."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import legacy_bridge as bridge


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


if __name__ == "__main__":
    unittest.main()
