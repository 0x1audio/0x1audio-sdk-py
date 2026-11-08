"""An app worker speaks this protocol on stdin and stdout, one JSON object per line.

The app's own page is HTML and JavaScript. It can use the design system, or any other
page it ships. The page asks the host to run a call. The host speaks to this worker
and keeps the session.

The host asks the worker to do something:

    {"id": 1, "type": "call", "name": "transcribe", "body": {}}

The worker answers:

    {"id": 1, "type": "result", "body": {}}
    {"id": 1, "type": "error", "message": "..."}

The worker can emit a line with no id while a call is running:

    {"type": "event", "name": "partial", "body": {}}

Cloud calls from api.v1 go back to the host, which holds the session:

    {"id": 2, "type": "cloud", "method": "GET", "path": "/api/v1/health", "body": null}
    {"id": 2, "type": "cloud-result", "status": 200, "body": {"status": "ok"}}

Stdout is the protocol. A worker prints logs on stderr.
"""

import contextvars
import json
import queue
import sys
import threading
import traceback
from collections.abc import Callable, Mapping
from typing import BinaryIO

import httpx

from ox1audio.cloud import Client
from ox1audio.runtime import link_var, sink_var


class Call:
    def __init__(self, client: Client, body: object, emit: Callable[[str, object], None]) -> None:
        self.client = client
        self.body = body
        self.cloud = Cloud(client)
        self._emit = emit

    def emit(self, name: str, body: object = None) -> None:
        self._emit(name, body)

    def progress(self, fraction: float, label: str = "") -> None:
        self._emit("progress", {"fraction": fraction, "label": label})


class Link:
    def __init__(self, stdin: BinaryIO, stdout: BinaryIO) -> None:
        self._stdin = stdin
        self._stdout = stdout
        self._write_lock = threading.Lock()
        self._lock = threading.Lock()
        self._next = 1
        self._pending: dict[int, queue.Queue[dict]] = {}
        self._incoming: queue.Queue[dict | None] = queue.Queue()
        threading.Thread(target=self._read, name="ox1audio-worker", daemon=True).start()

    def next_call(self) -> dict | None:
        return self._incoming.get()

    def library(self, body: dict) -> object:
        ident = self._reserve()
        self._write({"id": ident, "type": "library", **body})
        message = self._wait(ident)
        if message.get("type") == "error":
            raise ConnectionError(message.get("message") or "host closed the pipe")
        status = int(message.get("status") or 500)
        if status >= 400:
            payload = message.get("body")
            text = payload.get("message") if isinstance(payload, dict) else ""
            raise RuntimeError(text or "Could not update the Library.")
        return message.get("body")

    def cloud(self, method: str, path: str, body: object) -> dict:
        ident = self._reserve()
        self._write({"id": ident, "type": "cloud", "method": method, "path": path, "body": body})
        message = self._wait(ident)
        if message.get("type") == "error":
            raise ConnectionError(message.get("message") or "host closed the pipe")
        return message

    def reply(self, ident: int, body: object) -> None:
        self._write({"id": ident, "type": "result", "body": body})

    def fail(self, ident: int, message: str) -> None:
        self._write({"id": ident, "type": "error", "message": message})

    def event(self, name: str, body: object) -> None:
        self._write({"type": "event", "name": name, "body": body})

    def _reserve(self) -> int:
        with self._lock:
            ident = self._next
            self._next += 1
            self._pending[ident] = queue.Queue(maxsize=1)
            return ident

    def _wait(self, ident: int) -> dict:
        with self._lock:
            box = self._pending[ident]
        message = box.get()
        with self._lock:
            self._pending.pop(ident, None)
        return message

    def _write(self, message: dict) -> None:
        data = json.dumps(message, separators=(",", ":")).encode() + b"\n"
        with self._write_lock:
            self._stdout.write(data)
            self._stdout.flush()

    def _read(self) -> None:
        while True:
            line = self._stdin.readline()
            if line == b"":
                self._incoming.put(None)
                with self._lock:
                    boxes = list(self._pending.values())
                for box in boxes:
                    box.put({"type": "error", "message": "host closed the pipe"})
                return
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                print("worker ignored a line that was not JSON", file=sys.stderr)
                continue
            if not isinstance(message, dict):
                continue
            ident = message.get("id")
            if message.get("type") in {"cloud-result", "library-result"} and isinstance(ident, int):
                with self._lock:
                    box = self._pending.get(ident)
                if box is not None:
                    box.put(message)
                    continue
            self._incoming.put(message)


class _Pipe(httpx.BaseTransport):
    def __init__(self, link: Link) -> None:
        self._link = link

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        raw = request.content
        body = json.loads(raw) if raw else None
        message = self._link.cloud(request.method, request.url.path, body)
        status = int(message["status"])
        payload = message.get("body")
        if payload is None:
            return httpx.Response(status)
        return httpx.Response(status, json=payload)


def serve(
    handlers: Mapping[str, Callable[[Call], object]],
    *,
    stdin: BinaryIO | None = None,
    stdout: BinaryIO | None = None,
) -> None:
    """Read calls from the host until it closes the pipe."""
    out = stdout or sys.stdout.buffer
    if stdout is None:
        sys.stdout = sys.stderr
    link = Link(stdin or sys.stdin.buffer, out)
    link_var.set(link)
    sink_var.set(link.library)
    http = httpx.Client(base_url="http://cloud.local", transport=_Pipe(link))
    client = Client(base_url="http://cloud.local").set_httpx_client(http)
    while True:
        message = link.next_call()
        if message is None:
            http.close()
            return
        if message.get("type") != "call" or not isinstance(message.get("id"), int):
            continue
        threading.Thread(
            target=contextvars.copy_context().run,
            args=(_dispatch, handlers, client, link, message),
            name=f"ox1audio-{message.get('name', 'call')}",
            daemon=True,
        ).start()


def _dispatch(handlers: Mapping[str, Callable[[Call], object]], client: Client, link: Link, message: dict) -> None:
    name = message.get("name")
    handler = handlers.get(name) if isinstance(name, str) else None
    if handler is None:
        link.fail(message["id"], f"unknown call {name}")
        return

    def emit(event: str, body: object) -> None:
        link.event(event, body)

    try:
        body = handler(Call(client, message.get("body"), emit))
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        link.fail(message["id"], str(exc))
        return
    link.reply(message["id"], body)


class Cloud:
    """The signed-in cloud session. The desktop holds the token."""

    def __init__(self, client: Client) -> None:
        self.client = client

    def health(self) -> object:
        from ox1audio.cloud.api.default import health

        body = health.sync(client=self.client)
        return getattr(body, "status", None)
