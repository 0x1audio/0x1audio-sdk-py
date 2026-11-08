"""ox new writes an app that passes ox check and its own test; ox check teaches."""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import ox1audio as ox

SRC = str(Path(ox.__file__).resolve().parents[1])
ENV = {**os.environ, "PYTHONPATH": SRC}


def ox_cli(*args, cwd):
    return subprocess.run([sys.executable, "-m", "ox1audio.cli", *args], capture_output=True, text=True, cwd=cwd, env=ENV, timeout=120)


class NewAndCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def new_app(self):
        made = ox_cli("new", "Make It Louder", cwd=self.root)
        self.assertEqual(made.returncode, 0, made.stderr)
        return self.root / "make-it-louder"

    def test_a_new_app_checks_clean_and_its_test_passes(self):
        app = self.new_app()
        manifest = json.loads((app / "app.json").read_text())
        self.assertEqual(manifest["sdk"], "^0.3")
        self.assertEqual((app / "AGENTS.md").read_text(), (Path(ox.__file__).with_name("AGENTS.md")).read_text())
        checked = ox_cli("check", cwd=app)
        self.assertEqual(checked.returncode, 0, checked.stdout)
        self.assertIn("No errors. 1 action: convert.", checked.stdout)
        tested = subprocess.run([sys.executable, "-m", "unittest"], capture_output=True, text=True, cwd=app, env=ENV, timeout=120)
        self.assertEqual(tested.returncode, 0, tested.stderr)
        self.assertIn("OK", tested.stderr)

    def check(self, app):
        done = ox_cli("check", cwd=app)
        return done.returncode, done.stdout

    def test_a_v0_manifest_is_explained(self):
        app = self.new_app()
        (app / "app.json").write_text(json.dumps({"displayName": "Old", "version": "0.1.0", "worker": {"runtime": "python", "entry": "app.py"}}))
        code, out = self.check(app)
        self.assertEqual(code, 1)
        self.assertIn('error  manifest_v0  app.json\n       app.json has no "$schema", so 0x1audio reads it as v0.', out)
        self.assertIn("fix:  add \"$schema\"", out)
        self.assertIn("docs: https://docs.0x1audio.com/app-json#v1", out)

    def test_a_missing_sdk_range_is_explained(self):
        app = self.new_app()
        manifest = json.loads((app / "app.json").read_text())
        del manifest["sdk"]
        (app / "app.json").write_text(json.dumps(manifest))
        code, out = self.check(app)
        self.assertEqual(code, 1)
        self.assertIn("error  sdk_missing  app.json › sdk", out)
        self.assertIn('fix:  "sdk": "^0.3"', out)

    def test_an_undeclared_permission_is_explained(self):
        app = self.new_app()
        manifest = json.loads((app / "app.json").read_text())
        del manifest["permissions"]["library"]
        (app / "app.json").write_text(json.dumps(manifest))
        code, out = self.check(app)
        self.assertEqual(code, 1)
        self.assertIn("error  permission_undeclared  app.json › permissions.library", out)
        self.assertIn("The code uses library (it returns or adds sounds), but app.json doesn't ask for it.", out)

    def test_a_wrong_type_hint_is_explained_with_its_line(self):
        app = self.new_app()
        (app / "app.py").write_text('import ox1audio as ox\n\n\n@ox.action("Louder")\ndef louder(files: list[str]):\n    return None\n')
        code, out = self.check(app)
        self.assertEqual(code, 1)
        self.assertRegex(out, r"error  app_failed_to_load  app.py:4\n       TypeError: louder\(\): the parameter \"files\" is a list, which is not a control.")
        self.assertIn('fix:  annotate it with a control, like files: ox.Files("audio")', out)


class AgentsTest(unittest.TestCase):
    """Every code block in AGENTS.md is true: the Python runs, the app.json checks clean."""

    def blocks(self, language):
        text = Path(ox.__file__).with_name("AGENTS.md").read_text()
        return re.findall(rf"```{language}\n(.*?)```", text, re.S)

    def test_the_example_action_and_its_test_run(self):
        action, test = self.blocks("python")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "app.py").write_text(action)
            (root / "tests").mkdir()
            (root / "tests" / "tone.wav").write_bytes(__import__("ox1audio.cli", fromlist=["tone"]).tone())
            (root / "test_agents.py").write_text(test)
            done = subprocess.run([sys.executable, "-m", "unittest", "test_agents"], capture_output=True, text=True, cwd=root, env=ENV, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_the_example_app_json_checks_clean(self):
        from ox1audio.manifest import check

        (manifest,) = self.blocks("json")
        action = self.blocks("python")[0]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "app.json").write_text(manifest)
            (root / "app.py").write_text(action)
            self.assertEqual([item.message for item in check(root).findings], [])

    def test_agents_md_stays_under_two_thousand_tokens(self):
        text = Path(ox.__file__).with_name("AGENTS.md").read_text()
        self.assertLess(len(text) / 4, 2000, "AGENTS.md is over the 2k token budget (bytes / 4)")


if __name__ == "__main__":
    unittest.main()
