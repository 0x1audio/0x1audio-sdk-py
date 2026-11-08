"""Every path that 0.3 removed is refused with what to do instead."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import ox1audio as ox
from ox1audio.action import clear


class RemovedTest(unittest.TestCase):
    def setUp(self):
        clear()

    def assertTeaches(self, error, *parts):
        message = str(error)
        for part in parts:
            self.assertIn(part, message)
        self.assertIn("\nfix:  ", message)
        self.assertIn("\ndocs: https://docs.0x1audio.com/", message)

    def test_screen_is_now_action(self):
        with self.assertRaises(ImportError) as caught:
            ox.screen("Hello")
        self.assertTeaches(caught.exception, '@ox.screen("Title") is now @ox.action("Title").')

    def test_job_is_gone(self):
        with self.assertRaises(ImportError) as caught:
            from ox1audio import job  # noqa: F401
        self.assertTeaches(caught.exception, "@ox.job is gone")

    def test_serve_is_gone(self):
        with self.assertRaises(ImportError) as caught:
            ox.serve({"hello": lambda call: None})
        self.assertTeaches(caught.exception, "ox.serve is gone")

    def test_the_call_object_is_gone(self):
        with self.assertRaises(ImportError) as caught:
            from ox1audio import Call  # noqa: F401
        self.assertTeaches(caught.exception, "The call object is gone")

    def test_a_call_parameter_is_refused(self):
        with self.assertRaises(TypeError) as caught:
            @ox.action("Start")
            def start(call):
                return call.body
        self.assertTeaches(caught.exception, "start(call): actions take typed parameters, not a call object.")

    def test_yielding_progress_is_refused(self):
        with self.assertRaises(TypeError) as caught:
            @ox.action("Convert")
            def convert(files: ox.Files):
                yield ox.progress(1, "Done")
        self.assertTeaches(caught.exception, "convert() yields.")

    def test_exercise_is_now_test(self):
        with self.assertRaises(ImportError) as caught:
            ox.exercise(lambda: None)
        self.assertTeaches(caught.exception, "ox.exercise is now ox.test.")

    def test_eject_is_gone(self):
        with tempfile.TemporaryDirectory() as folder:
            done = subprocess.run([sys.executable, "-m", "ox1audio.cli", "eject"], capture_output=True, text=True, cwd=folder, env={"PYTHONPATH": str(Path(ox.__file__).resolve().parents[1])})
        self.assertEqual(done.returncode, 2)
        self.assertTeaches(done.stderr, "ox eject is gone")


if __name__ == "__main__":
    unittest.main()
