import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

import ox1audio as ox
from ox1audio.action import clear

from hosting import Host


class ProtocolTest(unittest.TestCase):
    def setUp(self):
        clear()

    def test_ready_lists_the_actions_first(self):
        @ox.action("Say hello")
        def hello(name: ox.Text(placeholder="Your name")):
            return f"Hello, {name or 'world'}"

        host = Host()
        try:
            ready = host.recv()
            self.assertEqual(ready["type"], "ready")
            self.assertEqual(ready["protocol"], 1)
            self.assertEqual(ready["sdk"], ox.__version__)
            self.assertEqual(ready["actions"][0]["name"], "hello")
            self.assertEqual(ready["actions"][0]["input"]["properties"]["name"]["x-ox"]["placeholder"], "Your name")
            host.send({"type": "call", "id": 7, "action": "hello", "input": {"name": "Ada"}})
            result, _ = host.until("result", 7)
            self.assertEqual(result["body"], "Hello, Ada")
        finally:
            host.close()

    def test_progress_is_tagged_with_its_call(self):
        @ox.action("Count")
        def count(steps: int = 3):
            for step in range(steps):
                ox.progress(step / steps, f"Step {step + 1}")
            return steps

        host = Host()
        try:
            host.recv()
            host.send({"type": "call", "id": 4, "action": "count", "input": {"steps": 2}})
            result, seen = host.until("result", 4)
            self.assertEqual(result["body"], 2)
            self.assertEqual(seen, [
                {"type": "progress", "id": 4, "fraction": 0.0, "label": "Step 1"},
                {"type": "progress", "id": 4, "fraction": 0.5, "label": "Step 2"},
            ])
        finally:
            host.close()

    def test_cancel_stops_the_call_at_the_next_progress(self):
        started = threading.Event()
        cleaned = threading.Event()

        @ox.action("Wait")
        def wait():
            started.set()
            try:
                while True:
                    ox.progress(None, "Waiting")
                    time.sleep(0.01)
            except ox.Cancelled:
                cleaned.set()
                raise

        host = Host()
        try:
            host.recv()
            host.send({"type": "call", "id": 9, "action": "wait", "input": {}})
            self.assertTrue(started.wait(2))
            host.send({"type": "cancel", "id": 9})
            error, _ = host.until("error", 9)
            self.assertEqual(error["error"], {"code": "cancelled", "message": "Stopped."})
            self.assertTrue(cleaned.is_set())
        finally:
            host.close()

    def test_errors_have_codes(self):
        @ox.action("Fail")
        def fail(kind: ox.Choice("problem", "crash")):
            if kind == "problem":
                raise ox.Problem("That file has no audio.", hint="Try a WAV.")
            raise KeyError("boom")

        host = Host()
        try:
            host.recv()
            host.send({"type": "call", "id": 1, "action": "fail", "input": {"kind": "problem"}})
            self.assertEqual(host.until("error", 1)[0]["error"], {"code": "problem", "message": "That file has no audio.", "hint": "Try a WAV."})
            host.send({"type": "call", "id": 2, "action": "fail", "input": {"kind": "crash"}})
            crashed = host.until("error", 2)[0]["error"]
            self.assertEqual(crashed["code"], "crashed")
            self.assertEqual(crashed["detail"], "KeyError: 'boom'")
            host.send({"type": "call", "id": 3, "action": "fail", "input": {"kind": "other"}})
            self.assertEqual(host.until("error", 3)[0]["error"]["code"], "bad_input")
            host.send({"type": "call", "id": 4, "action": "nope", "input": {}})
            self.assertEqual(host.until("error", 4)[0]["error"]["code"], "bad_input")
        finally:
            host.close()

    def test_library_requests_use_their_own_ids(self):
        folder = tempfile.TemporaryDirectory()
        song = Path(folder.name) / "song.wav"
        song.write_bytes(b"riff")

        @ox.action("Keep")
        def keep(files: ox.Files("audio")):
            return ox.sound(files[0], title="Kept")

        host = Host()
        try:
            host.recv()
            host.send({"type": "call", "id": 1, "action": "keep", "input": {"files": [str(song)]}})
            request, _ = host.until("library")
            self.assertEqual((request["op"], request["kind"], request["title"], request["path"]), ("add", "sound", "Kept", str(song)))
            self.assertNotIn("id", request)
            host.send({"type": "library-result", "rid": request["rid"], "status": 200, "body": {"id": "abc", "title": "Kept", "kind": "sound"}})
            result, _ = host.until("result", 1)
            self.assertEqual(result["body"], {"items": [{"id": "abc", "title": "Kept", "kind": "sound", "path": str(song)}]})
        finally:
            host.close()
            folder.cleanup()

    def test_shutdown_ends_the_loop(self):
        @ox.action("Idle")
        def idle():
            return None

        host = Host()
        host.recv()
        host.send({"type": "shutdown"})
        host.thread.join(timeout=2)
        self.assertFalse(host.thread.is_alive())
        host.close()


class EntryTest(unittest.TestCase):
    """Mixel starts every app as `python -m ox1audio <entry>`."""

    def run_entry(self, source, lines=()):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        entry = Path(folder.name) / "app.py"
        entry.write_text(source)
        src = str(Path(ox.__file__).resolve().parents[1])
        stdin = "".join(json.dumps(line) + "\n" for line in lines)
        done = subprocess.run([sys.executable, "-m", "ox1audio", str(entry)], input=stdin, capture_output=True, text=True, timeout=30, cwd=folder.name, env={"PYTHONPATH": src, "PATH": "/usr/bin:/bin"})
        return [json.loads(line) for line in done.stdout.splitlines() if line.strip()], done

    def test_an_app_loads_and_answers(self):
        out, done = self.run_entry(
            'import ox1audio as ox\n\n@ox.action("Hello")\ndef hello(name: str = "world"):\n    print("logs go to stderr")\n    return f"Hello, {name}"\n',
            [{"type": "call", "id": 1, "action": "hello", "input": {}}],
        )
        self.assertEqual(out[0]["type"], "ready")
        self.assertEqual(out[1], {"type": "result", "id": 1, "body": "Hello, world"})
        self.assertIn("logs go to stderr", done.stderr)

    def test_an_app_that_cannot_load_says_why(self):
        out, done = self.run_entry('import ox1audio as ox\nfrom ox1audio import job\n')
        self.assertEqual(done.returncode, 1)
        self.assertEqual(out[0]["type"], "fatal")
        self.assertEqual(out[0]["error"]["message"], "app.py could not start.")
        self.assertIn("RemovedError at app.py:2: @ox.job is gone", out[0]["error"]["detail"])

    def test_an_app_without_actions_says_so(self):
        out, _ = self.run_entry("x = 1\n")
        self.assertEqual(out[0]["error"]["message"], "app.py has no actions.")


if __name__ == "__main__":
    unittest.main()
