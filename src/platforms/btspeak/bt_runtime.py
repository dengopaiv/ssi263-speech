"""Small adapters for installed BT runtimes with older dialog signatures."""

from contextlib import contextmanager
from functools import wraps
import inspect


def accepts(function, keyword: str) -> bool:
    parameters = inspect.signature(function).parameters
    return keyword in parameters or any(p.kind == p.VAR_KEYWORD for p in parameters.values())


def optional_keywords(function, *keywords: str):
    omitted = {name for name in keywords if not accepts(function, name)}

    @wraps(function)
    def call(*args, **kwargs):
        return function(*args, **{name: value for name, value in kwargs.items() if name not in omitted})
    return call


class Dialogs:
    def __init__(self, native, host):
        self.native = native
        self.host = host
        self.shared_screen = accepts(native.request_choice, "stdscr") if hasattr(native, "request_choice") else True
        for name in ("show_message", "request_choice", "request_input", "request_confirmation"):
            if hasattr(native, name):
                setattr(self, name, optional_keywords(getattr(native, name), "stdscr"))

    def __getattr__(self, name):
        return getattr(self.native, name)

    @contextmanager
    def activity(self, message: str, *, stdscr=None):
        if hasattr(self.native, "activity"):
            with optional_keywords(self.native.activity, "stdscr")(message, stdscr=stdscr):
                yield
        else:
            self.host.say(message, immediate=True, wait=True)
            yield


def say(host, message: str) -> None:
    optional_keywords(host.say, "as_ui")(message, immediate=True, wait=True, as_ui=True)
