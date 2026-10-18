"""Prefer the platform keyboard server; recognize the supported older keypad before falling back."""

from contextlib import nullcontext
from gettext import gettext as _
import importlib
import os
from pathlib import Path
import subprocess

SOCKET = Path("/run/BTSpeak/keyboard-socket")


def native_service_present() -> bool:
    # A stale socket or a configured but stopped server is not a legacy device.
    if os.path.lexists(SOCKET) or any(path.exists() for path in (
        Path("/BTSpeak/Services/kb_driver"), Path("/BTSpeak/Systemd/kb-driver.service"),
    )):
        return True
    result = subprocess.run(["systemctl", "show", "kb-driver.service", "--property=LoadState", "--value"],
                            capture_output=True, text=True, timeout=3, check=True)
    return result.stdout.strip() != "not-found"


def native_client(runtime):
    client = getattr(runtime, "kb_client", None)
    if client is not None:
        return client
    try:
        return importlib.import_module("BTSpeak.kb_client")
    except ModuleNotFoundError as exc:
        if exc.name != "BTSpeak.kb_client":
            raise
        return None


def legacy_available() -> bool:
    """Read-only probe shared with the standard Linux launcher's device detection."""
    try:
        from legacy_bridge import preflight
        if native_service_present():
            return False
        preflight()
        return True
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def select_keyboard(runtime):
    client = native_client(runtime)
    if client is not None and client.server_available():
        return nullcontext(client)
    if native_service_present():
        raise OSError(_("The device keyboard service is installed but unavailable. Restore it before starting the emulator."))
    from legacy_bridge import preflight
    from legacy_keyboard import Session
    preflight()
    return Session()
