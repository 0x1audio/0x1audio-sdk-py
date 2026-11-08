"""A job runs in the background. The page asks for it, then reads status."""

from __future__ import annotations

import contextvars
import threading
from collections.abc import Callable

JOBS: list[Callable] = []
_jobs: dict[str, dict] = {}
_cancels: dict[str, threading.Event] = {}
_lock = threading.Lock()
_seq = 0


def job(fn: Callable) -> Callable:
    fn.__ox_job__ = True  # type: ignore[attr-defined]
    if fn not in JOBS:
        JOBS.append(fn)
    return fn


def jobs() -> list[Callable]:
    return list(JOBS)


def clear() -> None:
    JOBS.clear()


def handlers() -> dict[str, Callable]:
    found = {fn.__name__: _start(fn) for fn in JOBS}
    if found:
        found["status"] = status
        found["cancel"] = cancel
    return found


def status(call) -> dict:
    body = call.body if isinstance(call.body, dict) else {}
    ident = body.get("id")
    with _lock:
        current = _jobs.get(ident) if isinstance(ident, str) else None
        if current is None:
            raise ValueError("That job is gone.")
        report = {key: value for key, value in current.items() if key != "thread"}
    return report


def cancel(call) -> dict:
    body = call.body if isinstance(call.body, dict) else {}
    ident = body.get("id")
    event = _cancels.get(ident) if isinstance(ident, str) else None
    if event is not None:
        event.set()
    return {"ok": True}


def _start(fn: Callable) -> Callable:
    def handler(call):
        global _seq
        with _lock:
            _seq += 1
            ident = str(_seq)
            _jobs[ident] = {"done": False, "progress": 0, "label": "", "error": None, "result": None}
            _cancels[ident] = threading.Event()
            while len(_jobs) > 8:
                oldest = next(iter(_jobs))
                if oldest == ident:
                    break
                _jobs.pop(oldest, None)
                _cancels.pop(oldest, None)

        def work() -> None:
            emit = call.progress

            def report(fraction: float, label: str = "") -> None:
                _update(ident, progress=fraction, label=label)
                emit(fraction, label)

            call.progress = report  # type: ignore[method-assign]
            call.cancelled = _cancels[ident].is_set  # type: ignore[attr-defined]
            try:
                result = fn(call)
            except Exception as exc:
                _update(ident, done=True, error=str(exc))
                return
            _update(ident, done=True, progress=1, result=result, error=None)

        threading.Thread(target=contextvars.copy_context().run, args=(work,), name=f"ox1audio-{fn.__name__}", daemon=True).start()
        return {"id": ident}

    return handler


def _update(ident: str, **fields: object) -> None:
    with _lock:
        current = _jobs.get(ident)
        if current is not None:
            current.update(fields)
