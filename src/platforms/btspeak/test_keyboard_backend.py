"""Backend selection and ownership without opening the device keyboard."""

from contextlib import nullcontext
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import keyboard_backend as backend
import legacy_keyboard as legacy
from bt_runtime import Dialogs, optional_keywords


class BackendTests(unittest.TestCase):
    def test_native_server_wins_without_legacy_probe(self):
        client = SimpleNamespace(server_available=lambda: True)
        with patch.object(backend, "native_service_present") as present, patch("legacy_bridge.preflight") as preflight:
            with backend.select_keyboard(SimpleNamespace(kb_client=client)) as selected:
                self.assertIs(selected, client)
        present.assert_not_called()
        preflight.assert_not_called()

    def test_configured_but_unavailable_server_never_falls_back(self):
        client = SimpleNamespace(server_available=lambda: False)
        with patch.object(backend, "native_service_present", return_value=True), patch("legacy_keyboard.Session") as session:
            with self.assertRaisesRegex(OSError, "installed but unavailable"):
                backend.select_keyboard(SimpleNamespace(kb_client=client))
        session.assert_not_called()

    def test_legacy_requires_successful_preflight_and_missing_native_service(self):
        with patch.object(backend, "native_client", return_value=None), \
                patch.object(backend, "native_service_present", return_value=False), \
                patch("legacy_bridge.preflight", side_effect=OSError("unsupported")), patch("legacy_keyboard.Session") as session:
            with self.assertRaisesRegex(OSError, "unsupported"):
                backend.select_keyboard(object())
            session.assert_not_called()
        with patch.object(backend, "native_client", return_value=None), \
                patch.object(backend, "native_service_present", return_value=False), \
                patch("legacy_bridge.preflight") as preflight, patch("legacy_keyboard.Session", return_value="legacy"):
            self.assertEqual(backend.select_keyboard(object()), "legacy")
            preflight.assert_called_once()

    def test_missing_library_is_allowed_but_broken_import_is_not(self):
        for name, allowed in (("BTSpeak.kb_client", True), ("dependency", False)):
            with patch.object(backend.importlib, "import_module", side_effect=ModuleNotFoundError(name=name)):
                if allowed:
                    self.assertIsNone(backend.native_client(object()))
                else:
                    with self.assertRaises(ModuleNotFoundError):
                        backend.native_client(object())

    def test_busy_native_capture_is_not_retried_with_legacy(self):
        client = SimpleNamespace(server_available=lambda: True, connect=Mock(side_effect=OSError("busy")))
        with patch("legacy_keyboard.Session") as session:
            with backend.select_keyboard(SimpleNamespace(kb_client=client)) as selected:
                with self.assertRaisesRegex(OSError, "busy"):
                    selected.connect(3)
        session.assert_not_called()

    def test_probe_reports_false_on_unknown_setup_without_starting_helper(self):
        with patch.object(backend, "native_service_present", return_value=False), \
                patch("legacy_bridge.preflight", side_effect=OSError("unsupported")), patch("legacy_keyboard.Session") as session:
            self.assertFalse(backend.legacy_available())
        session.assert_not_called()

    def test_cleanup_never_stops_a_different_sessions_unit(self):
        session = legacy.Session()
        with patch.object(legacy, "properties", return_value={"Description": "another launch"}), \
                patch.object(legacy.subprocess, "run") as run:
            session.close()
        run.assert_not_called()

    def test_failed_concurrent_launch_leaves_existing_bridge_running(self):
        session = legacy.Session()
        with patch.object(legacy, "properties", return_value={"Description": "another launch"}), \
                patch.object(legacy.subprocess, "run", return_value=SimpleNamespace(returncode=1, stderr="Unit exists")) as run:
            with self.assertRaisesRegex(OSError, "Unit exists"):
                session.__enter__()
        self.assertEqual(run.call_count, 1)

    def test_release_send_is_bounded_and_closes_socket_on_timeout(self):
        connection = object.__new__(legacy.Connection)
        connection.socket = Mock()
        connection.socket.sendall.side_effect = TimeoutError("slow consumer")
        with self.assertRaises(TimeoutError):
            connection.__exit__(None, None, None)
        self.assertEqual(connection.socket.method_calls[0].args, (3,))
        self.assertEqual(connection.socket.method_calls[0][0], "settimeout")
        connection.socket.close.assert_called_once()

    def test_supervisor_keeps_recovery_without_session_time_limit(self):
        with tempfile.TemporaryDirectory(prefix="bridge path ") as directory:
            ready = Path(directory) / "ready"
            session = legacy.Session()
            ready.write_text(session.token)
            with patch.object(legacy, "READY", ready), patch.object(legacy.os, "geteuid", return_value=1000), \
                    patch.object(sys, "argv", [str(Path(directory) / "blazie_emu_bt")]), \
                    patch.object(legacy.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
                self.assertIs(session.__enter__(), legacy)
            args = run.call_args.args[0]
            self.assertEqual(args[:3], ["sudo", "-n", "systemd-run"])
            self.assertIn("--property=RuntimeMaxSec=infinity", args)
            self.assertIn("--property=TimeoutStopSec=45s", args)
            self.assertTrue(any("--bt-keyboard recover" in arg for arg in args))
            self.assertIn(str(Path(directory) / "blazie_emu_bt"), args)

    def test_old_dialog_arguments_are_adapted_without_hiding_errors(self):
        calls = []
        def choice(choices, prompt="", default=None):
            calls.append((choices, prompt, default))
            return None
        native = SimpleNamespace(request_choice=choice)
        host = SimpleNamespace(say=Mock())
        ui = Dialogs(native, host)
        self.assertFalse(ui.shared_screen)
        ui.request_choice({"a": "A"}, prompt="Choose", default="a", stdscr=object())
        self.assertEqual(calls, [({"a": "A"}, "Choose", "a")])
        with self.assertRaises(TypeError):
            ui.request_choice({}, typo=True)
        with ui.activity("Loading", stdscr=object()):
            pass
        host.say.assert_called_once_with("Loading", immediate=True, wait=True)

    def test_activity_preserves_native_context_and_old_speech_omits_as_ui(self):
        native = SimpleNamespace(activity=lambda message: nullcontext(message))
        with Dialogs(native, object()).activity("Loading", stdscr=object()):
            pass
        def say(message, immediate=False, wait=False):
            return message, immediate, wait
        self.assertEqual(optional_keywords(say, "as_ui")("Hi", immediate=True, wait=True, as_ui=True), ("Hi", True, True))


if __name__ == "__main__":
    unittest.main()
