"""The mixel command: help, check --json/--fix/--strict, test, run, publish --dry-run, and the registry."""

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import ox1audio as ox

SRC = str(Path(ox.__file__).resolve().parents[1])


def mixel(*args, cwd, env=None):
    return subprocess.run([sys.executable, "-m", "ox1audio.cli", *args], capture_output=True, text=True, cwd=cwd, env={**os.environ, "PYTHONPATH": SRC, **(env or {})}, timeout=300)


class Scratch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def new_app(self, title="Make It Louder"):
        made = mixel("new", title, cwd=self.root)
        self.assertEqual(made.returncode, 0, made.stderr)
        return self.root / made.stdout.split("/")[0].removeprefix("Created ")


class HelpTest(Scratch):
    def test_help_names_mixel_and_only_the_safe_install(self):
        done = mixel("--help", cwd=self.root)
        self.assertEqual(done.returncode, 0)
        self.assertIn("mixel check", done.stdout)
        self.assertIn("uv tool install ox1audio", done.stdout)
        for wrong in ("uvx mixel", "npx mixel", "pip install mixel", "ox check"):
            self.assertNotIn(wrong, done.stdout)

    def test_a_wrong_command_names_the_fix_and_exits_2(self):
        done = mixel("chek", cwd=self.root)
        self.assertEqual(done.returncode, 2)
        self.assertIn("mixel chek is not a command.\nfix:  mixel check", done.stderr)

    def test_new_says_what_to_run_next(self):
        made = mixel("new", "Make It Louder", cwd=self.root)
        self.assertIn("Next\n  cd make-it-louder\n  mixel check", made.stdout)


class LicenseTest(Scratch):
    def test_new_apps_are_apache_unless_the_author_picks_another(self):
        app = self.new_app()
        self.assertIn("Apache License", (app / "LICENSE").read_text())
        self.assertEqual(json.loads((app / "app.json").read_text())["license"], "Apache-2.0")
        self.assertIn('license = "Apache-2.0"', (app / "pyproject.toml").read_text())
        made = mixel("new", "Other One", "--license", "MIT", cwd=self.root)
        self.assertEqual(made.returncode, 0, made.stderr)
        self.assertFalse((self.root / "other-one" / "LICENSE").exists())
        self.assertEqual(json.loads((self.root / "other-one" / "app.json").read_text())["license"], "MIT")
        self.assertEqual(mixel("new", "Bad", "--license", "Apache 2", cwd=self.root).returncode, 2)

    def test_check_refuses_a_license_that_is_not_spdx(self):
        app = self.new_app()
        data = json.loads((app / "app.json").read_text())
        data["license"] = "Apache 2"
        (app / "app.json").write_text(json.dumps(data))
        done = mixel("check", "--json", cwd=app)
        self.assertEqual([item["code"] for item in json.loads(done.stdout)["errors"]], ["manifest_license"])


class CheckTest(Scratch):
    def test_json_has_codes_and_fixes(self):
        app = self.new_app()
        data = json.loads((app / "app.json").read_text())
        del data["permissions"]["library"]
        (app / "app.json").write_text(json.dumps(data))
        done = mixel("check", "--json", cwd=app)
        self.assertEqual(done.returncode, 1)
        report = json.loads(done.stdout)
        self.assertFalse(report["ok"])
        self.assertEqual([item["code"] for item in report["errors"]], ["permission_undeclared"])
        self.assertTrue(report["errors"][0]["fix"])
        self.assertTrue(report["errors"][0]["doc"].startswith("https://docs.0x1audio.com/"))

    def test_fix_adds_the_permission_the_code_uses(self):
        app = self.new_app()
        data = json.loads((app / "app.json").read_text())
        del data["permissions"]["library"]
        (app / "app.json").write_text(json.dumps(data))
        done = mixel("check", "--fix", cwd=app)
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn("Fixed  permissions.library added", done.stdout)
        self.assertIn("library", json.loads((app / "app.json").read_text())["permissions"])

    def test_strict_fails_on_warnings(self):
        app = self.new_app()
        data = json.loads((app / "app.json").read_text())
        data["permissions"]["data"] = "Remember your settings on this computer."
        (app / "app.json").write_text(json.dumps(data))
        self.assertEqual(mixel("check", cwd=app).returncode, 0)
        strict = mixel("check", "--strict", cwd=app)
        self.assertEqual(strict.returncode, 1)
        self.assertIn("warn   permission_unused", strict.stdout)


class TypeCheckingTest(Scratch):
    def test_type_checking_imports_are_not_dependencies(self):
        app = self.new_app()
        (app / "app.py").write_text("from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from somewhere_else import Thing\n" + (app / "app.py").read_text())
        done = mixel("check", "--strict", cwd=app)
        self.assertEqual(done.returncode, 0, done.stdout)


class TestAndRunTest(Scratch):
    def test_a_new_app_passes_mixel_test(self):
        app = self.new_app()
        done = mixel("test", cwd=app)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"^1 passed in [\d.]+ s\.$")

    def test_a_failing_test_shows_its_line_and_message(self):
        app = self.new_app()
        test = app / "tests" / "test_app.py"
        test.write_text(test.read_text().replace('"tone")', '"wrong")'))
        done = mixel("test", "--json", cwd=app)
        self.assertEqual(done.returncode, 1)
        result = json.loads(done.stdout)
        self.assertEqual(result["passed"], 0)
        self.assertEqual(result["failed"][0]["where"], "tests/test_app.py:14")
        self.assertIn("AssertionError: 'tone' != 'wrong'", result["failed"][0]["message"])

    def test_a_missing_package_says_how_to_install_it(self):
        app = self.new_app()
        (app / "tests" / "test_extra.py").write_text("import not_a_real_package_xyz\n")
        result = json.loads(mixel("test", "--json", cwd=app).stdout)
        missing = [item for item in result["failed"] if item.get("missing")]
        self.assertEqual(missing[0]["missing"], "not_a_real_package_xyz")
        self.assertIn("uv pip install -r pyproject.toml", missing[0]["fix"])

    def test_check_errors_stop_the_tests(self):
        app = self.new_app()
        (app / "app.json").write_text("{}")
        done = mixel("test", cwd=app)
        self.assertEqual(done.returncode, 1)
        self.assertIn("Fix them first", done.stdout)

    def test_run_one_action_on_a_file(self):
        app = self.new_app()
        done = mixel("run", "convert", "--file", "tests/tone.wav", "--set", "format=flac", "--json", cwd=app)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        result = json.loads(done.stdout)
        self.assertEqual(result["items"][0]["title"], "tone")
        self.assertTrue(result["items"][0]["path"].endswith(".flac"))
        self.assertGreater(result["progress_calls"], 0)

    def test_run_keeps_the_files_and_out_copies_them(self):
        app = self.new_app()
        out = self.root / "heard"
        done = mixel("run", "convert", "--file", "tests/tone.wav", "--set", "format=flac", "--out", str(out), cwd=app)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((out / "tone.flac").is_file())
        self.assertIn("The files stay where they are", done.stdout)
        wrong = mixel("run", "nope", "--file", "tests/tone.wav", cwd=app)
        self.assertIn("no_such_action", wrong.stdout)

    def test_check_and_test_load_the_app_with_its_venv(self):
        app = self.new_app()
        venv = app / ".venv"
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True)
        site = next(venv.glob("lib/python*/site-packages"))
        (site / "only_in_the_venv.py").write_text("VALUE = 1\n")
        (app / "app.py").write_text("import only_in_the_venv\n" + (app / "app.py").read_text())
        pyproject = app / "pyproject.toml"
        pyproject.write_text(pyproject.read_text().replace("dependencies = []", 'dependencies = ["only-in-the-venv"]'))
        locked = mixel("check", "--json", cwd=app)
        self.assertIn("lock_missing", [item["code"] for item in json.loads(locked.stdout)["errors"]])
        (app / "uv.lock").write_text("version = 1\n")
        done = mixel("check", cwd=app)
        self.assertEqual(done.returncode, 0, done.stdout)
        tested = mixel("test", cwd=app)
        self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)

    def test_fix_adds_a_missing_package_and_flags_todo_reasons(self):
        app = self.new_app()
        (app / "app.py").write_text("import yaml\n" + (app / "app.py").read_text())
        fixed = mixel("check", "--fix", cwd=app)
        self.assertIn("Fixed  pyproject.toml lists pyyaml now", fixed.stdout)
        self.assertIn('"pyyaml"', (app / "pyproject.toml").read_text())
        (app / "app.py").write_text((app / "app.py").read_text().replace("import yaml\n", ""))
        data = json.loads((app / "app.json").read_text())
        del data["permissions"]["library"]
        (app / "app.json").write_text(json.dumps(data))
        mixel("check", "--fix", cwd=app)
        self.assertTrue(json.loads((app / "app.json").read_text())["permissions"]["library"].startswith("TODO"))
        strict = mixel("check", "--strict", cwd=app)
        self.assertIn("The reason for library is still a TODO.", strict.stdout)

    def test_run_names_the_controls_when_input_is_missing(self):
        app = self.new_app()
        done = mixel("run", "convert", cwd=app)
        self.assertEqual(done.returncode, 1)
        self.assertIn("fix:  mixel run convert --file PATH --set format=VALUE", done.stdout)


class FakeRegistry(BaseHTTPRequestHandler):
    seen: list = []
    polls = 0

    def log_message(self, *args):
        pass

    def reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)) or b"{}")
        FakeRegistry.seen.append((self.path, body, self.headers.get("authorization")))
        if self.path == "/api/v1/cli/login":
            return self.reply(200, {"device_code": "dev-1", "user_code": "CALM-RIVER-42", "verification_url": "http://example.test/cli", "interval": 1, "expires_in": 30})
        if self.path == "/api/v1/cli/login/poll":
            FakeRegistry.polls += 1
            if FakeRegistry.polls < 2:
                return self.reply(400, {"error": {"code": "authorization_pending", "message": "Waiting."}})
            return self.reply(200, {"token": "tok-123", "account": {"email": "ada@example.com"}})
        if self.path == "/api/v1/registry/submissions":
            if self.headers.get("authorization") != "Bearer tok-123":
                return self.reply(401, {"error": {"code": "unauthorized", "message": "Sign in."}})
            if body.get("commit") == "bad":
                return self.reply(422, {"error": {"code": "manifest_version", "message": "version must be greater than 0.1.0.", "doc_url": "https://docs.0x1audio.com/errors/manifest_version"}})
            return self.reply(201, {"id": "s1", "status": "in_review", "url": "http://example.test/developers/make-it-louder"})
        self.reply(404, {})

    def do_GET(self):
        if self.path.startswith("/api/v1/registry/submissions?app="):
            return self.reply(200, {"submissions": [{"id": "s1", "version": "0.1.0", "status": "in_review", "created": "2026-11-08T10:12:00Z",
                                                      "checks": [{"name": "mixel check --strict", "ok": True}],
                                                      "notes": [{"author": "reviewer", "body": "Please say why the app needs network.", "created": "2026-11-08T14:30:00Z"}]}]})
        self.reply(404, {})


class RegistryTest(Scratch):
    def setUp(self):
        super().setUp()
        FakeRegistry.seen, FakeRegistry.polls = [], 0
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeRegistry)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.env = {"MIXEL_API": f"http://127.0.0.1:{self.server.server_port}", "XDG_CONFIG_HOME": str(self.root / "config"), "MIXEL_TOKEN": ""}

    def tearDown(self):
        self.server.shutdown()
        super().tearDown()

    def git_app(self):
        app = self.new_app()
        remote = self.root / "remote.git"
        run = lambda *args, cwd=app: subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)  # noqa: E731
        run("init", "-q", "--bare", str(remote), cwd=self.root)
        run("init", "-q", "-b", "main")
        run("-c", "user.email=a@b.c", "-c", "user.name=A", "commit", "-q", "--allow-empty", "-m", "start")
        run("add", "-A")
        run("-c", "user.email=a@b.c", "-c", "user.name=A", "commit", "-q", "-m", "app")
        run("remote", "add", "origin", str(remote))
        run("push", "-q", "origin", "main")
        run("remote", "set-url", "origin", "https://github.com/ada/make-it-louder.git")
        return app

    def test_login_saves_a_private_token_and_status_shows_notes(self):
        done = mixel("login", "--non-interactive", cwd=self.root, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("CALM-RIVER-42", done.stdout)
        self.assertIn("Signed in as ada@example.com", done.stdout)
        file = self.root / "config" / "mixel" / "credentials.json"
        self.assertEqual(oct(file.stat().st_mode & 0o777), "0o600")
        app = self.new_app()
        status = mixel("status", cwd=app, env=self.env)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("0.1.0    in review", status.stdout)
        self.assertIn('note     "Please say why the app needs network."', status.stdout)

    def test_publish_needs_a_clean_pushed_tree_and_sign_in(self):
        app = self.git_app()
        dry = mixel("publish", "--dry-run", cwd=app, env={**self.env, "MIXEL_TOKEN": "tok-123"})
        self.assertEqual(dry.returncode, 0, dry.stdout + dry.stderr)
        self.assertIn("pushed to github.com/ada/make-it-louder", dry.stdout)
        unsigned = mixel("publish", "--dry-run", cwd=app, env=self.env)
        self.assertEqual(unsigned.returncode, 1)
        self.assertIn("Sign-in    no  not signed in\n           fix:  mixel login", unsigned.stdout)
        signed_out = mixel("publish", cwd=app, env=self.env)
        self.assertEqual(signed_out.returncode, 3)
        self.assertIn("You're not signed in.\nfix:  mixel login", signed_out.stderr)
        sent = mixel("publish", cwd=app, env={**self.env, "MIXEL_TOKEN": "tok-123"})
        self.assertEqual(sent.returncode, 0, sent.stderr)
        self.assertIn("Submitted  make-it-louder 0.1.0 for review.", sent.stdout)
        path, body, _ = FakeRegistry.seen[-1]
        self.assertEqual((path, body["repository"], len(body["commit"])), ("/api/v1/registry/submissions", "github.com/ada/make-it-louder", 40))
        (app / "app.py").write_text((app / "app.py").read_text() + "\n")
        dirty = mixel("publish", "--dry-run", cwd=app, env=self.env)
        self.assertEqual(dirty.returncode, 1)
        self.assertIn("There are changes that aren't committed (app.py)", dirty.stdout)
        self.assertIn("not signed in", dirty.stdout, "every gate is listed, not just the first")

    def test_dry_run_lists_every_gate_with_plain_git_words(self):
        app = self.new_app()
        subprocess.run(["rm", "-rf", str(app / ".git")], check=True)
        (app / "app.py").write_text("import subprocess\n" + (app / "app.py").read_text())
        done = mixel("publish", "--dry-run", "--json", cwd=app, env=self.env)
        self.assertEqual(done.returncode, 1)
        gates = {gate["gate"]: gate for gate in json.loads(done.stdout)["gates"]}
        self.assertEqual([gates[name]["ok"] for name in ("check", "git", "sign-in")], [False, False, False])
        self.assertEqual(gates["git"]["detail"], "This folder isn't a git repository yet. Reviewers read the app on GitHub.")
        self.assertNotIn("fatal", done.stdout)

    def test_an_unreachable_registry_exits_4_with_the_fix(self):
        app = self.new_app()
        done = mixel("status", cwd=app, env={**self.env, "MIXEL_API": "http://127.0.0.1:9", "MIXEL_TOKEN": "x"})
        self.assertEqual(done.returncode, 4)
        self.assertIn("Couldn't reach Mixel at http://127.0.0.1:9", done.stderr)


if __name__ == "__main__":
    unittest.main()
