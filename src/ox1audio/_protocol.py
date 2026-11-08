"""The worker side of protocol 1. Internal: apps never import this.

NDJSON on stdin and stdout, one JSON object per line. Stdout carries only the
protocol; ``print`` goes to stderr. Host call ids (``id``) and worker request
ids (``rid``) are separate spaces. The message shapes live in one place, the
``Message`` docstring below, so GAB-37 can generate them from a contract.

Worker -> host
    {"type": "ready", "protocol": 1, "sdk": "0.3.0", "actions": [ActionSpec], "permissions": ["files"]}
    {"type": "fatal", "error": Error}                         the app could not load; the worker exits
    {"type": "progress", "id": 7, "fraction": 0.4 | null, "label": "Separating vocals"}
    {"type": "event", "id": 7, "name": "partial", "body": ...}  ox.emit; the host forwards it to the page that made call 7
    {"type": "result", "id": 7, "body": ...}
    {"type": "error", "id": 7, "error": Error}
    {"type": "library", "rid": 3, "op": "add", "kind", "path", "title", "metadata"}
    {"type": "cloud", "rid": 4, "method", "path", "body"}

Host -> worker
    {"type": "call", "id": 7, "action": "convert", "input": {...}}
    {"type": "cancel", "id": 7}
    {"type": "library-result", "rid": 3, "status": 200, "body": {...}}
    {"type": "cloud-result", "rid": 4, "status": 200, "body": {...}}
    {"type": "shutdown"}

Error = {"code": "bad_input" | "problem" | "cancelled" | "crashed", "message": str, "hint"?: str, "detail"?: str,
         "kept"?: [Item]}   kept: on "cancelled", what the action finished before Stop (already in the Library)
ActionSpec = {"name", "title", "input": JSON Schema (object), "timeout": seconds}
"""

from __future__ import annotations

import contextvars
import json
import queue
import sys
import threading
import traceback
from collections.abc import Iterable
from typing import BinaryIO

from ox1audio import __version__, _contract
from ox1audio.action import Action, BadInput, Cancelled, Problem, call, stopped_message
from ox1audio.runtime import link_var

PROTOCOL = _contract.PROTOCOL


class Link:
    def __init__(self, stdin: BinaryIO, stdout: BinaryIO) -> None:
        self._stdin = stdin
        self._stdout = stdout
        self._write_lock = threading.Lock()
        self._lock = threading.Lock()
        self._next = 1
        self._pending: dict[int, queue.Queue[dict]] = {}
        self._incoming: queue.Queue[dict | None] = queue.Queue()
        self.reader = threading.Thread(target=self._read, name="ox1audio-link", daemon=True)
        self.reader.start()

    def next_message(self) -> dict | None:
        return self._incoming.get()

    def send(self, message: dict) -> None:
        data = json.dumps(message, separators=(",", ":"), allow_nan=False).encode() + b"\n"
        with self._write_lock:
            self._stdout.write(data)
            self._stdout.flush()

    def request(self, message: dict) -> dict:
        """Ask the host for something (library, cloud) and wait for its answer."""
        with self._lock:
            rid = self._next
            self._next += 1
            box: queue.Queue[dict] = queue.Queue(maxsize=1)
            self._pending[rid] = box
        self.send({**message, "rid": rid})
        answer = box.get()
        with self._lock:
            self._pending.pop(rid, None)
        if answer.get("type") == "closed":
            raise ConnectionError("0x1audio closed the app.")
        return answer

    def library(self, payload: dict) -> object:
        answer = self.request({"type": "library", **payload})
        status = int(answer.get("status") or 500)
        body = answer.get("body")
        if status >= 400:
            text = body.get("message") if isinstance(body, dict) else ""
            raise Problem(text or "Could not add that to the Library.")
        return body

    def _read(self) -> None:
        while True:
            line = self._stdin.readline()
            if line == b"":
                self._incoming.put(None)
                with self._lock:
                    boxes = list(self._pending.values())
                for box in boxes:
                    box.put({"type": "closed"})
                return
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                print("The app ignored a line from 0x1audio that was not JSON.", file=sys.stderr)
                continue
            if not isinstance(message, dict):
                continue
            rid = message.get("rid")
            if message.get("type") in {"library-result", "cloud-result"} and isinstance(rid, int):
                with self._lock:
                    box = self._pending.get(rid)
                if box is not None:
                    box.put(message)
                continue
            self._incoming.put(message)


def ready(registered: Iterable[Action]) -> dict:
    listed = list(registered)
    needed: set[str] = set()
    for act in listed:
        needed |= act.permissions()
    order = _contract.PERMISSIONS
    return {
        "type": "ready",
        "protocol": PROTOCOL,
        "sdk": __version__,
        "actions": [act.spec() for act in listed],
        "permissions": [code for code in order if code in needed],
    }


def serve(registered: Iterable[Action], *, stdin: BinaryIO | None = None, stdout: BinaryIO | None = None) -> None:
    """Announce the actions, then run calls until the host closes the pipe or says shutdown."""
    out = stdout or sys.stdout.buffer
    if stdout is None:
        sys.stdout = sys.stderr
    link = Link(stdin or sys.stdin.buffer, out)
    link_var.set(link)
    by_name = {act.name: act for act in registered}
    cancels: dict[int, threading.Event] = {}
    link.send(ready(by_name.values()))
    workers: list[threading.Thread] = []
    while True:
        message = link.next_message()
        if message is None or message.get("type") == "shutdown":
            # Shutdown stops what is running; at end of input, calls get the same few seconds to finish.
            if message is not None:
                for event in list(cancels.values()):
                    event.set()
            for thread in workers:
                thread.join(timeout=3)
            # Let the reader see the end of input before Python shuts down; a daemon thread
            # still inside readline() at shutdown makes Python abort with a fatal error.
            link.reader.join(timeout=0.5)
            return
        kind = message.get("type")
        ident = message.get("id")
        if kind == "cancel" and isinstance(ident, int):
            event = cancels.get(ident)
            if event is not None:
                event.set()
            continue
        if kind != "call" or not isinstance(ident, int):
            continue
        name = message.get("action")
        act = by_name.get(name) if isinstance(name, str) else None
        if act is None:
            link.send(_error(ident, "bad_input", f"This app has no action called {name}.", f"Its actions are: {', '.join(by_name) or 'none'}."))
            continue
        cancels[ident] = threading.Event()
        thread = threading.Thread(
            target=contextvars.copy_context().run,
            args=(_run, link, act, ident, message.get("input"), cancels),
            name=f"ox1audio-{act.name}-{ident}",
            daemon=True,
        )
        thread.start()
        workers = [item for item in workers if item.is_alive()] + [thread]


def _run(link: Link, act: Action, ident: int, given: object, cancels: dict[int, threading.Event]) -> None:
    cancel = cancels[ident]

    def report(fraction: float | None, label: str) -> None:
        link.send({"type": "progress", "id": ident, "fraction": fraction, "label": label})

    def send(name: str, body: object) -> None:
        link.send({"type": "event", "id": ident, "name": name, "body": body})

    try:
        body = call(act, given, ident=ident, cancel=cancel, report=report, send=send)
        line = {"type": "result", "id": ident, "body": body}
        if len(json.dumps(line, allow_nan=False)) > 1 << 20:
            line = _error(ident, "crashed", "The result is too large to send.", detail=f"{act.name}() returned more than 1 MiB. Write large data to a file and return its path.")
            print(line["error"]["detail"], file=sys.stderr)
    except Cancelled as stop:
        line = _error(ident, "cancelled", stopped_message(stop.kept))
        if stop.kept:
            line["error"]["kept"] = stop.kept
    except Problem as problem:
        line = _error(ident, "problem", problem.message, problem.hint)
    except BadInput as bad:
        line = _error(ident, "bad_input", str(bad))
    except Exception as exc:
        if cancel.is_set():
            line = _error(ident, "cancelled", "Stopped.")
        else:
            traceback.print_exc(file=sys.stderr)
            line = _error(ident, "crashed", "The app ran into a problem.", detail=f"{type(exc).__name__}: {exc}")
    finally:
        cancels.pop(ident, None)
    try:
        link.send(line)
    except (BrokenPipeError, ValueError, OSError):
        pass


def _error(ident: int, code: str, message: str, hint: str | None = None, detail: str | None = None) -> dict:
    error: dict = {"code": code, "message": message}
    if hint:
        error["hint"] = hint
    if detail:
        error["detail"] = detail
    return {"type": "error", "id": ident, "error": error}


def fatal(message: str, detail: str = "", *, stdout: BinaryIO | None = None) -> None:
    out = stdout or sys.__stdout__.buffer
    error = {"code": "crashed", "message": message}
    if detail:
        error["detail"] = detail
    out.write(json.dumps({"type": "fatal", "error": error}).encode() + b"\n")
    out.flush()
