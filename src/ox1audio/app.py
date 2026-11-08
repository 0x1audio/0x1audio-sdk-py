"""Start an app. Screens and jobs register themselves, then run() listens."""

from __future__ import annotations

from collections.abc import Callable

from ox1audio.jobs import handlers as job_handlers
from ox1audio.screen import describe, run_screen, screens
from ox1audio.worker import serve


def run(**extra: Callable) -> None:
    """Listen for calls until the desktop closes the app."""

    def describe_call(call):
        return describe()

    def wrap(fn: Callable) -> Callable:
        def handler(call):
            body = call.body if isinstance(call.body, dict) else {}
            return run_screen(fn, body, call.progress)

        return handler

    mapped: dict[str, Callable] = {}
    mapped.update(job_handlers())
    mapped.update({fn.__name__: wrap(fn) for fn in screens()})
    mapped.update(extra)
    mapped["__describe__"] = describe_call
    serve(mapped)
