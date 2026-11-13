"""mixel new writes an app that passes mixel check and its own test; mixel check teaches."""

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
        self.assertIn('error  manifest_v0  app.json\n       app.json has no "$schema", so Mixel reads it as v0.', out)
        self.assertIn("fix:  add \"$schema\"", out)
        self.assertIn("docs: https://docs.0x1audio.com/reference/app-json\n", out)

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


class ImportsTest(NewAndCheckTest):
    def test_a_package_the_code_imports_but_does_not_declare_is_an_error(self):
        app = self.new_app()
        (app / "app.py").write_text("import numpy\n" + (app / "app.py").read_text())
        code, out = self.check(app)
        self.assertEqual(code, 1)
        self.assertIn("error  dependency_missing  app.py:1\n       app.py imports numpy, but pyproject.toml doesn't list it, so Mixel won't install it.", out)
        self.assertIn('fix:  add "numpy" to pyproject.toml', out)

    def test_running_programs_is_flagged(self):
        app = self.new_app()
        (app / "app.py").write_text("import subprocess\n" + (app / "app.py").read_text())
        code, out = self.check(app)
        self.assertEqual(code, 1)
        self.assertIn("error  banned_api  app.py:1", out)


class ReadPlusNetworkTest(NewAndCheckTest):
    """An app that isn't one of Mixel's own can't ask to see the Library and reach the network together."""

    def ask(self, app, **more):
        manifest = json.loads((app / "app.json").read_text())
        manifest["permissions"].update(more)
        (app / "app.json").write_text(json.dumps(manifest))

    def codes(self, app):
        done = ox_cli("check", "--json", cwd=app)
        report = json.loads(done.stdout)
        return done.returncode, {item["code"]: item for item in report["errors"]}

    READ = {"library-read": "Show the songs in your Library, so you can choose one."}
    NETWORK = {"network": {"why": "Download the model once.", "hosts": ["example.com"]}}

    def test_library_read_with_network_fails_and_says_what_to_do(self):
        app = self.new_app()
        self.ask(app, **self.READ, **self.NETWORK)
        code, errors = self.codes(app)
        self.assertEqual(code, 1)
        found = errors["permission_pair"]
        self.assertEqual(found["where"], "app.json › permissions")
        self.assertIn("library-read and network can't be asked for together yet", found["message"])
        self.assertIn("a Files control lets people choose their sounds without library-read", found["fix"])
        self.assertEqual(found["doc"], "https://docs.0x1audio.com/permissions#library-read-and-network")
        _, out = self.check(app)
        self.assertIn("error  permission_pair  app.json › permissions", out)

    def test_either_one_alone_is_not_the_pair(self):
        for one in (self.READ, self.NETWORK):
            app = self.new_app()
            self.ask(app, **one)
            self.assertNotIn("permission_pair", self.codes(app)[1])
            self.tmp.cleanup()
            self.setUp()

    def test_only_a_0x1audio_checkout_is_one_of_mixels_own(self):
        app = self.new_app()
        self.ask(app, **self.READ, **self.NETWORK)
        config = app / ".git" / "config"
        base = config.read_text()
        for url, own in (
            ("https://github.com/0x1audio/0x1audio-uvr-app.git", True),
            ("git@github.com:0x1audio/0x1audio-uvr-app.git", True),
            ("https://github.com/0x1audio-fan/0x1audio-uvr-app.git", False),
            ("https://github.com/someone/0x1audio", False),
            ("https://example.com/0x1audio/app.git", False),
        ):
            config.write_text(base + f'[remote "origin"]\n\turl = {url}\n')
            self.assertEqual("permission_pair" not in self.codes(app)[1], own, url)


class FixWithoutNumpyTest(NewAndCheckTest):
    """ox.audio.read needs numpy. mixel check --fix lists it and installs it; when it can't install it, it says so."""

    def app_that_reads_samples(self):
        app = self.new_app()
        (app / "app.py").write_text(
            'import ox1audio as ox\n\n\n@ox.action("Convert")\ndef convert(files: ox.Files("audio")):\n'
            "    made = []\n    for path in files:\n        samples, rate = ox.audio.read(path)\n"
            '        out = ox.temp() / (path.stem + ".wav")\n        ox.audio.write(out, samples, rate)\n'
            "        made.append(ox.sound(out, title=path.stem))\n    return made\n"
        )
        return app

    def test_fix_without_numpy_or_uv_does_not_crash_and_says_what_is_left(self):
        from unittest import mock

        from ox1audio.cli import check

        app = self.app_that_reads_samples()
        with mock.patch.object(check, "_installed", return_value=False), mock.patch("shutil.which", return_value=None):
            report = check.run(app, fix=True)
            self.assertIn("pyproject.toml lists numpy now", report.fixed)
            self.assertIn('"numpy"', (app / "pyproject.toml").read_text())
            (left,) = [item for item in report.errors if item.code == "dependency_not_installed"]
            self.assertIn("numpy is in pyproject.toml but not installed", left.message)
            self.assertIn("uv sync", left.fix)
            # A second check says the same thing, instead of passing and leaving mixel run to fail.
            self.assertEqual([item.code for item in check.run(app).errors], ["dependency_not_installed", "lock_missing"])

    def test_fix_installs_numpy_when_it_can(self):
        from unittest import mock

        from ox1audio.cli import check

        app = self.app_that_reads_samples()
        ran = []

        def uv(command, **_):
            ran.append(command[1:])
            (app / "uv.lock").write_text("")
            return subprocess.CompletedProcess(command, 0, "", "")

        state = {"installed": False}
        real = subprocess.run
        with mock.patch.object(check, "_installed", side_effect=lambda *_: state["installed"]), mock.patch("shutil.which", return_value="/usr/bin/uv"), \
                mock.patch("subprocess.run", side_effect=lambda command, **kw: (state.update(installed=True), uv(command))[1] if command[0] == "/usr/bin/uv" else real(command, **kw)):
            report = check.run(app, fix=True)
        self.assertEqual(ran, [["sync", "--quiet"]])
        self.assertEqual([item.code for item in report.errors], [])
        self.assertIn("packages installed into .venv by uv sync", report.fixed)

    def test_listed_and_installed_numpy_is_quiet(self):
        from unittest import mock

        from ox1audio.cli import check

        app = self.app_that_reads_samples()
        (app / "pyproject.toml").write_text((app / "pyproject.toml").read_text().replace("dependencies = []", 'dependencies = ["numpy"]'))
        (app / "uv.lock").write_text("")
        with mock.patch.object(check, "_installed", return_value=True):
            self.assertEqual([item.code for item in check.run(app).errors], [])


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
        # Measured with tiktoken: 6304 bytes = 1768 cl100k tokens (0.28 tokens per byte), so 7000 bytes is about 1.96k.
        self.assertLess(len(text.encode()), 7000, "AGENTS.md is over the 2k token budget")


if __name__ == "__main__":
    unittest.main()
