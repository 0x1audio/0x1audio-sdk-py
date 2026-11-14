"""GAB-79: what the fresh-eyes dogfood and the tutorial found, each kept fixed."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import ox1audio as ox

SRC = str(Path(ox.__file__).resolve().parents[1])


def mixel(*args, cwd):
    env = {key: value for key, value in os.environ.items() if key != "OX1_DATA"}
    return subprocess.run([sys.executable, "-m", "ox1audio.cli", *args], capture_output=True, text=True, cwd=cwd, env={**env, "PYTHONPATH": SRC}, timeout=300)


class DogfoodTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        made = mixel("new", "Loop Maker", cwd=self.tmp.name)
        self.assertEqual(made.returncode, 0, made.stderr)
        self.app = Path(self.tmp.name) / "loop-maker"

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, *flags):
        return json.loads(mixel("check", "--json", *flags, cwd=self.app).stdout)

    def manifest(self, change):
        data = json.loads((self.app / "app.json").read_text())
        change(data)
        (self.app / "app.json").write_text(json.dumps(data))

    def test_template_words_left_in_a_rewritten_app_fail_strict(self):
        (self.app / "app.py").write_text((self.app / "app.py").read_text().replace('@ox.action("Convert")\ndef convert', '@ox.action("Make a loop")\ndef loop'))
        (self.app / "tests" / "test_app.py").write_text("")
        report = self.check("--strict")
        self.assertFalse(report["ok"])
        self.assertEqual(sorted(item["where"] for item in report["warnings"] if item["code"] == "template_words"), ["app.json › permissions.library", "app.json › summary"])
        self.manifest(lambda data: data.update(summary="Repeat a part of a song into a loop.", permissions={**data["permissions"], "library": "Add the loops to your Library."}))
        self.assertTrue(self.check("--strict")["ok"])

    def test_the_template_itself_is_not_flagged(self):
        self.assertTrue(self.check("--strict")["ok"])

    def test_an_unknown_permission_is_unknown_not_also_unused(self):
        self.manifest(lambda data: data["permissions"].update(mic="Listen to your voice while you hum."))
        codes = [item["code"] for item in self.check()["errors"] + self.check()["warnings"]]
        self.assertIn("permission_unknown", codes)
        self.assertNotIn("permission_unused", codes)

    def test_ox_audio_read_needs_numpy_listed(self):
        (self.app / "app.py").write_text((self.app / "app.py").read_text() + "\n\ndef peak(path):\n    samples, rate = ox.audio.read(path)\n    return float(abs(samples).max())\n")
        error = next(item for item in self.check()["errors"] if item["code"] == "dependency_missing")
        self.assertIn("ox.audio.read works on numpy arrays", error["message"])
        self.assertIn('add "numpy"', error["fix"])

    def test_packages_without_uv_lock_are_refused_like_the_registry_does(self):
        pyproject = self.app / "pyproject.toml"
        pyproject.write_text(pyproject.read_text().replace("dependencies = []", 'dependencies = ["numpy"]'))
        error = next(item for item in self.check()["errors"] if item["code"] == "lock_missing")
        self.assertEqual(error["fix"], "uv lock, then commit uv.lock (mixel check --fix runs it)")

    def test_mixel_run_and_ox_test_have_a_data_folder(self):
        (self.app / "app.py").write_text('import ox1audio as ox\n\n\n@ox.action("Remember")\ndef remember(name: str = "a"):\n    ox.data.write("notes/" + name + ".txt", "hi")\n    return ox.data.list("notes")\n')
        self.manifest(lambda data: data.update(permissions={"data": "Remember your notes on this computer."}))
        (self.app / "tests" / "test_app.py").write_text(
            "import unittest\n\nimport ox1audio as ox\nimport app\n\n\nclass T(unittest.TestCase):\n"
            "    def test_data(self):\n        ox.test(app.remember, name='a')\n        self.assertEqual(ox.test(app.remember, name='b')['result'], ['a.txt', 'b.txt'])\n")
        ran = mixel("run", "remember", "--json", cwd=self.app)
        self.assertEqual(json.loads(ran.stdout)["result"], ["a.txt"], ran.stdout + ran.stderr)
        again = mixel("run", "remember", "--set", "name=b", "--json", cwd=self.app)
        self.assertEqual(json.loads(again.stdout)["result"], ["b.txt"], "each mixel run starts with an empty data folder")
        tested = mixel("test", cwd=self.app)
        self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)

    def test_a_crash_prints_its_fix_once(self):
        (self.app / "app.py").write_text('import ox1audio as ox\n\n\n@ox.action("Boom")\ndef boom():\n    raise RuntimeError("Bad thing.\\nfix:  do the right thing\\ndocs: https://docs.0x1audio.com/actions")\n')
        done = mixel("run", "boom", cwd=self.app)
        error = done.stdout.split("error  crashed", 1)[1]  # the log above it is the traceback, as raised
        self.assertEqual(error.count("fix:"), 1, done.stdout)
        self.assertIn("fix:  do the right thing", done.stdout)

    def test_new_makes_a_repository_that_ignores_run_output(self):
        self.assertTrue((self.app / ".git").is_dir())
        self.assertIn("out/", (self.app / ".gitignore").read_text())



class PageScaffoldTest(unittest.TestCase):
    def test_new_page_writes_a_vite_page_mixel_can_open(self):
        with tempfile.TemporaryDirectory() as root:
            made = mixel("new", "Loop Maker", "--page", cwd=root)
            self.assertEqual(made.returncode, 0, made.stderr)
            self.assertIn("npm install && npm run build", made.stdout)
            app = Path(root) / "loop-maker"
            self.assertEqual(json.loads((app / "app.json").read_text())["page"], "dist/index.html")
            package = json.loads((app / "package.json").read_text())
            self.assertEqual(package["license"], "Apache-2.0")
            # Both come from npm by name and range, never from a folder beside the SDK.
            self.assertEqual(package["dependencies"]["@ox1audio/sdk"], "^0.3.1")
            self.assertEqual(package["dependencies"]["@ox1audio/design-system"], "^0.1.0")
            self.assertIn("react", package["dependencies"])
            self.assertIn('@import "@ox1audio/design-system/theme.css";', (app / "src" / "index.css").read_text())
            self.assertNotIn("@0x1audio/", "".join(path.read_text() for path in app.rglob("*") if path.is_file() and path.suffix in {".ts", ".tsx", ".css", ".json", ".md"}))
            self.assertIn('base: "./"', (app / "vite.config.ts").read_text())
            self.assertIn('dedupe: ["react", "react-dom"]', (app / "vite.config.ts").read_text())
            self.assertIn('<ActionForm action="convert" />', (app / "src" / "App.tsx").read_text())
            report = json.loads(mixel("check", "--json", cwd=app).stdout)
            self.assertEqual([(item["code"], item["fix"]) for item in report["errors"]], [("manifest_page", "build the page (npm run build)")])
            (app / "dist").mkdir()
            (app / "dist" / "index.html").write_text("<!doctype html>")
            self.assertTrue(json.loads(mixel("check", "--json", "--strict", cwd=app).stdout)["ok"])

    def test_an_unknown_option_names_the_ones_there_are(self):
        with tempfile.TemporaryDirectory() as root:
            done = mixel("new", "X", "--pages", cwd=root)
            self.assertEqual(done.returncode, 2)
            self.assertIn("--page", done.stderr)


if __name__ == "__main__":
    unittest.main()
