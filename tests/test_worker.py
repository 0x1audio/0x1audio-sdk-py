import json
import os
import select
import tempfile
import threading
import unittest

from ox1audio import serve
from ox1audio.cloud.api.default import health


class Host:
    def __init__(self):
        self.to_worker_r, self.to_worker_w = os.pipe()
        self.from_worker_r, self.from_worker_w = os.pipe()
        self.buffer = b""

    def stdin(self):
        return os.fdopen(self.to_worker_r, "rb", buffering=0)

    def stdout(self):
        return os.fdopen(self.from_worker_w, "wb", buffering=0)

    def send(self, message):
        os.write(self.to_worker_w, json.dumps(message).encode() + b"\n")

    def recv(self, timeout=2):
        while b"\n" not in self.buffer:
            ready, _, _ = select.select([self.from_worker_r], [], [], timeout)
            if not ready:
                raise TimeoutError(self.buffer.decode(errors="replace"))
            self.buffer += os.read(self.from_worker_r, 4096)
        line, self.buffer = self.buffer.split(b"\n", 1)
        return json.loads(line)

    def close(self):
        os.close(self.to_worker_w)


def transcribe(call):
    body = health.sync(client=call.client)
    call.emit("partial", {"text": body.status if body is not None else ""})
    return {"text": "hello"}


class WorkerTest(unittest.TestCase):
    def start(self, handlers):
        self.host = Host()
        self.stdin = self.host.stdin()
        self.stdout = self.host.stdout()
        self.thread = threading.Thread(
            target=serve,
            args=(handlers,),
            kwargs={"stdin": self.stdin, "stdout": self.stdout},
            daemon=True,
        )
        self.thread.start()

    def stop(self):
        self.host.close()
        self.thread.join(timeout=2)
        self.stdin.close()
        self.stdout.close()
        os.close(self.host.from_worker_r)

    def test_call_event_and_cloud_round_trip(self):
        self.start({"transcribe": transcribe})
        try:
            host = self.host
            host.send({"id": 7, "type": "call", "name": "transcribe", "body": {}})

            cloud = host.recv()
            self.assertEqual(cloud["type"], "cloud")
            self.assertEqual(cloud["method"], "GET")
            self.assertEqual(cloud["path"], "/api/v1/health")
            self.assertIsNone(cloud["body"])
            host.send({"id": cloud["id"], "type": "cloud-result", "status": 200, "body": {"status": "ok"}})

            event = host.recv()
            self.assertEqual(event, {"type": "event", "name": "partial", "body": {"text": "ok"}})
            result = host.recv()
            self.assertEqual(result, {"id": 7, "type": "result", "body": {"text": "hello"}})
        finally:
            self.stop()
        self.assertFalse(self.thread.is_alive())

    def test_library_export_from_the_call_thread(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.write(b"audio")
        handle.close()

        def export(call):
            from ox1audio.library import add

            return add("other", handle.name, "Note")

        self.start({"export": export})
        try:
            self.host.send({"id": 3, "type": "call", "name": "export", "body": {}})
            library = self.host.recv()
            self.assertEqual(library["type"], "library")
            self.assertEqual(library["op"], "add")
            self.assertEqual(library["title"], "Note")
            self.host.send({"id": library["id"], "type": "library-result", "status": 200, "body": {"id": "1", "title": "Note", "kind": "other"}})
            result = self.host.recv()
            self.assertEqual(result["type"], "result")
            self.assertEqual(result["body"]["title"], "Note")
        finally:
            self.stop()
            os.unlink(handle.name)

    def test_unknown_call(self):
        self.start({})
        try:
            self.host.send({"id": 1, "type": "call", "name": "missing", "body": None})
            self.assertEqual(self.host.recv()["type"], "error")
        finally:
            self.stop()


if __name__ == "__main__":
    unittest.main()
