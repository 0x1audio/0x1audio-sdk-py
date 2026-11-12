"""Every example in examples/ runs, as a developer would run it, against a stand-in Mixel.
examples/smoke.py runs the same files against the real one."""

import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fake_mixel import FakeMixel

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def run(file: str, *args: str, **env: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(EXAMPLES / file), *args], capture_output=True, text=True, timeout=120, env={**os.environ, **env})


@unittest.skipIf(sys.platform == "win32", "the stand-in Mixel listens on a Unix socket")
class ExamplesTest(unittest.TestCase):
    def test_library_search_and_crate_with_the_switch_on(self):
        with FakeMixel() as fake:
            library = run("library.py", MIXEL_DATA_DIR=str(fake.data_dir))
            self.assertEqual(library.returncode, 0, library.stderr)
            self.assertTrue(library.stdout.startswith("4 sounds\n  snare            2\n"), library.stdout)
            search = run("search.py", "snare", "--avoid", "clap", MIXEL_DATA_DIR=str(fake.data_dir))
            self.assertEqual(search.returncode, 0, search.stderr)
            self.assertRegex(search.stdout, r"s1    Snare Tape 04\.wav .* named: named snare")
            self.assertIn("Like Snare Tape 04.wav: ", search.stdout)
            self.assertRegex(search.stdout, r'For a model \(\d+ bytes\): \{"answerable": true, "columns"')
            crate = run("crate.py", "snare", MIXEL_DATA_DIR=str(fake.data_dir))
            self.assertEqual(crate.returncode, 0, crate.stderr)
            self.assertIn("Proposed a crate of 2 sounds", crate.stdout)
            self.assertEqual({call["caller"] for call in fake.calls}, {"sdk example"})

    def test_search_without_the_sound_model_still_finds_by_words(self):
        with FakeMixel(no_model=True) as fake:
            search = run("search.py", "snare", MIXEL_DATA_DIR=str(fake.data_dir))
        self.assertEqual(search.returncode, 0, search.stderr)
        self.assertIn("Like Snare Tape 04.wav: Mixel can't compare sounds yet: the sound model is off or still indexing.", search.stdout)

    def test_with_mixel_closed_an_example_says_what_to_do(self):
        with tempfile.TemporaryDirectory() as empty:
            closed = run("search.py", "snare", MIXEL_DATA_DIR=empty)
        self.assertEqual(closed.returncode, 1)
        self.assertEqual(closed.stdout, "")
        self.assertEqual(closed.stderr, "Mixel isn't open, or it doesn't let assistants search the Library.\nfix: open Mixel and turn on Settings › Your assistant › Let an assistant search your Library\n")

    def test_run_app_runs_an_action_then_opens_the_app_in_developer_mode(self):
        with tempfile.TemporaryDirectory() as empty:
            alone = run("run_app.py", MIXEL_DATA_DIR=empty)
        self.assertEqual(alone.returncode, 0, alone.stderr)
        self.assertIn("Made tone (sound): tone.flac", alone.stdout)
        self.assertIn("Not opened in Mixel: Mixel isn't open with developer mode on.", alone.stdout)
        with FakeMixel(developer=True) as fake:
            opened = run("run_app.py", MIXEL_DATA_DIR=str(fake.data_dir))
        self.assertEqual(opened.returncode, 0, opened.stderr)
        self.assertIn("Opened make-it-flac 0.1.0 in Mixel 0.1.17.\n[info] Started the worker.\n[log] mono: 1 file\nClosed it.\n", opened.stdout)

    def test_cloud_reaches_the_cloud_named_by_mixel_api(self):
        class Health(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", "15")
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Health)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as home:
                cloud = run("cloud.py", MIXEL_API=f"http://127.0.0.1:{server.server_address[1]}", MIXEL_TOKEN="", XDG_CONFIG_HOME=home, APPDATA=home)
            self.assertEqual(cloud.returncode, 0, cloud.stderr)
            self.assertEqual(cloud.stdout, "cloud: ok\n")
        finally:
            server.shutdown()
            server.server_close()


class VersionTest(unittest.TestCase):
    def test_pyproject_the_package_and_the_newest_changelog_entry_agree(self):
        import re
        import tomllib

        import ox1audio

        root = Path(__file__).resolve().parents[1]
        version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
        self.assertEqual(ox1audio.__version__, version)
        newest = re.search(r"^## (\d+\.\d+\.\d+)\b", (root / "CHANGELOG.md").read_text(), re.M)
        self.assertEqual(newest and newest.group(1), version, "add a CHANGELOG.md entry for this version")


if __name__ == "__main__":
    unittest.main()
