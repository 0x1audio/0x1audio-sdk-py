"""A fake 0x1audio host for protocol tests: pipes in, pipes out, one JSON line at a time."""

import json
import os
import select
import threading

from ox1audio import _protocol
from ox1audio.action import actions


class Host:
    def __init__(self, registered=None):
        self.to_worker_r, self.to_worker_w = os.pipe()
        self.from_worker_r, self.from_worker_w = os.pipe()
        self.buffer = b""
        self.stdin = os.fdopen(self.to_worker_r, "rb", buffering=0)
        self.stdout = os.fdopen(self.from_worker_w, "wb", buffering=0)
        self.thread = threading.Thread(
            target=_protocol.serve,
            args=(registered if registered is not None else actions(),),
            kwargs={"stdin": self.stdin, "stdout": self.stdout},
            daemon=True,
        )
        self.thread.start()

    def send(self, message):
        os.write(self.to_worker_w, json.dumps(message).encode() + b"\n")

    def recv(self, timeout=5):
        while b"\n" not in self.buffer:
            ready, _, _ = select.select([self.from_worker_r], [], [], timeout)
            if not ready:
                raise TimeoutError(self.buffer.decode(errors="replace"))
            self.buffer += os.read(self.from_worker_r, 65536)
        line, self.buffer = self.buffer.split(b"\n", 1)
        return json.loads(line)

    def until(self, kind, ident=None, timeout=5):
        seen = []
        while True:
            message = self.recv(timeout)
            if message.get("type") == kind and (ident is None or message.get("id") == ident):
                return message, seen
            seen.append(message)

    def close(self):
        os.close(self.to_worker_w)
        self.thread.join(timeout=5)
        self.stdin.close()
        self.stdout.close()
        os.close(self.from_worker_r)
