"""GAB-79: mixel check refuses dangerous code however it is spelled, and every refusal names its fix."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import ox1audio as ox
from ox1audio.cli._safety import scan_source

SRC = str(Path(ox.__file__).resolve().parents[1])

# (snippet, the code it must get, a word the message must name)
REFUSED = [
    # running programs
    ("import subprocess", "banned_api", "subprocess"),
    ("import subprocess as sp\nsp.run(['ls'])", "banned_api", "subprocess"),
    ("from subprocess import run as go\ngo(['ls'])", "banned_api", "subprocess"),
    ("from subprocess import *", "banned_api", "subprocess"),
    ("import os\nos.system('ls')", "banned_api", "os.system"),
    ("import os as o\no.popen('ls')", "banned_api", "os.popen"),
    ("from os import system as s\ns('ls')", "banned_api", "os.system"),
    ("from os import execvp", "banned_api", "os.execvp"),
    ("import os\nos.posix_spawn('/bin/ls', [], {})", "banned_api", "os.posix_spawn"),
    ("import os\nrun = os.system\nrun('ls')", "banned_api", "os.system"),
    ("from os import *\nsystem('ls')", "banned_api", "from os import *"),
    ("import os\ngetattr(os, 'system')('ls')", "banned_api", "os.system"),
    ("import os\ngetattr(os, 'sys' + 'tem')('ls')", "banned_api", "os.system"),
    ("import os\ngetattr(os, f'{\"sys\"}tem')('ls')", "banned_api", "os.system"),
    ("import os\nname = input()\ngetattr(os, name)('ls')", "banned_api", "getattr on os"),
    ("import os\nos.__dict__['system']('ls')", "banned_api", "os.system"),
    ("import os\nvars(os)['system']('ls')", "banned_api", "os.system"),
    ("import sys\nsys.modules['subprocess'].run(['ls'])", "banned_api", "subprocess"),
    ("import sys\nsys.modules['os'].system('ls')", "banned_api", "os.system"),
    ("import operator, os\noperator.attrgetter('system')(os)('ls')", "banned_api", "attrgetter"),
    ("import asyncio\nasyncio.create_subprocess_exec('ls')", "banned_api", "asyncio.create_subprocess_exec"),
    ("import asyncio\nloop = asyncio.get_event_loop()\nloop.subprocess_exec(None, 'ls')", "banned_api", "subprocess_exec"),
    ("import pty", "banned_api", "pty"),
    ("import posix\nposix.system('ls')", "banned_api", "posix"),
    ("import pydub", "banned_api", "pydub"),
    ("import webbrowser", "banned_api", "webbrowser"),
    # native code and raw sockets
    ("import ctypes", "banned_api", "ctypes"),
    ("import ctypes.util", "banned_api", "ctypes"),
    ("from cffi import FFI", "banned_api", "cffi"),
    ("import socket", "banned_api", "socket"),
    ("from socket import create_connection", "banned_api", "socket"),
    ("import asyncio\nasyncio.open_connection('example.com', 80)", "banned_api", "asyncio.open_connection"),
    ("from http.server import HTTPServer", "banned_api", "http.server"),
    ("import requests", "banned_api", "requests"),
    ("import httpx", "banned_api", "httpx"),
    # code from strings
    ("eval('1 + 1')", "banned_api", "eval"),
    ("exec('x = 1')", "banned_api", "exec"),
    ("compile('x = 1', 'x', 'exec')", "banned_api", "compile"),
    ("e = eval\ne('1')", "banned_api", "eval"),
    ("eval = eval\neval('1')", "banned_api", "eval"),
    ("class Model:\n    def eval(self):\n        pass\neval('1')", "banned_api", "eval"),
    ("import builtins\nbuiltins.exec('x = 1')", "banned_api", "exec"),
    ("import builtins\ngetattr(builtins, 'ev' + 'al')('1')", "banned_api", "eval"),
    ("from builtins import exec as run\nrun('x = 1')", "banned_api", "exec"),
    ("__builtins__['eval']('1')", "banned_api", "__builtins__"),
    ("globals()['__builtins__'].eval('1')", "banned_api", "eval"),
    ("().__class__.__base__.__subclasses__()", "banned_api", "__subclasses__"),
    ("def f(): pass\nf.__globals__['os']", "banned_api", "__globals__"),
    ("import sys\nsys._getframe().f_globals", "banned_api", "f_globals"),
    ("import runpy\nrunpy.run_path('x.py')", "banned_api", "runpy"),
    ("import code", "banned_api", "code"),
    ("import marshal", "banned_api", "marshal"),
    # dynamic imports
    ("__import__('subprocess').run(['ls'])", "banned_api", "subprocess"),
    ("__import__('o' + 's').system('ls')", "banned_api", "os.system"),
    ("__import__('ssecorpbus'[::-1])", "banned_api", "subprocess"),
    ("name = input()\n__import__(name)", "banned_api", "__import__"),
    ("import importlib\nimportlib.import_module('subprocess')", "banned_api", "subprocess"),
    ("import importlib\nimportlib.import_module(input())", "banned_api", "importlib.import_module"),
    ("from importlib import import_module as load\nload('socket')", "banned_api", "socket"),
    ("from importlib import import_module as load\nload(input())", "banned_api", "importlib.import_module"),
    ("import importlib.util\nimportlib.util.spec_from_file_location('x', 'x.py')", "banned_api", "importlib.util"),
    ("import importlib\nimportlib.__import__('ctypes')", "banned_api", "ctypes"),
    # fixed paths outside the app
    ("open('/etc/passwd')", "path_outside", "/etc/passwd"),
    ("open(file='/etc/passwd')", "path_outside", "/etc/passwd"),
    ("open('/et' + 'c/passwd')", "path_outside", "/etc/passwd"),
    ("name = 'x'\nopen(f'/etc/{name}')", "path_outside", "/etc/"),
    ("import io\nio.open('/etc/passwd')", "path_outside", "/etc/passwd"),
    ("import os\nos.open('/etc/passwd', os.O_RDONLY)", "path_outside", "/etc/passwd"),
    ("import os\nos.listdir('/Users')", "path_outside", "/Users"),
    ("import os\nos.remove('/tmp/x')", "path_outside", "/tmp/x"),
    ("from pathlib import Path\nPath('/etc/passwd').read_text()", "path_outside", "/etc/passwd"),
    ("from pathlib import Path\n(Path('/etc') / 'passwd').read_text()", "path_outside", "/etc"),
    ("import pathlib\npathlib.Path('~/Music').expanduser()", "path_outside", "~/Music"),
    ("import shutil\nshutil.copy('a.wav', '/tmp/a.wav')", "path_outside", "/tmp/a.wav"),
    ("import shutil\nshutil.rmtree('C:\\\\Users')", "path_outside", "C:\\Users"),
    ("from pathlib import Path\nPath.home()", "path_outside", "home"),
    ("import os\nos.path.expanduser('~')", "path_outside", "home"),
    ("import os\nos.environ['HOME']", "path_outside", "HOME"),
    ("import os\nos.getenv('HOME')", "path_outside", "HOME"),
    ("import ox1audio as ox\nox.audio.read('/Users/me/song.wav')", "path_outside", "/Users/me/song.wav"),
    ("import soundfile\nsoundfile.read('/etc/x.wav')", "path_outside", "/etc/x.wav"),
    ("o = open\no('/etc/passwd')", "path_outside", "/etc/passwd"),
]

ALLOWED = [
    "import os\nos.path.join('a', 'b')",
    "import os\nos.makedirs(folder, exist_ok=True)",
    "import re\nre.compile('x')",
    "class Model:\n    def eval(self):\n        return self\nModel().eval()",
    "import torch\nmodel = object()\nmodel.eval()",
    "import sys\nsys.modules[__name__]",
    "import sys\nsys.path.insert(0, 'engine')",
    "from importlib import metadata\nmetadata.version('numpy')",
    "import importlib\nimportlib.import_module('json')",
    "open('presets.json')",
    "open(path)",
    "from pathlib import Path\nPath(__file__).parent / 'model.onnx'",
    "import os\nos.environ.get('OX1_DATA')",
    "import os\nos.getenv('OMP_NUM_THREADS')",
    "print('/v1/me')",
    "import ox1audio as ox\nox.cloud.get('/v1/me')",
    "open('/dev/null', 'w')",
    "import urllib.parse\nurllib.parse.quote('a b')",
    "import json\njson.loads('{}')",
    "x = getattr(obj, 'name', None)",
    "import os\ngetattr(os, 'sep')",
    "import shutil\nshutil.which('ls')",
]


class RefusedTest(unittest.TestCase):
    def test_each_evasion_is_refused_with_a_fix(self):
        for snippet, code, word in REFUSED:
            with self.subTest(snippet=snippet):
                findings = scan_source(snippet, "app.py").findings
                self.assertTrue(findings, "nothing was refused")
                hit = [item for item in findings if item.code == code]
                self.assertTrue(hit, [item.code for item in findings])
                self.assertTrue(any(word in item.message for item in hit), [item.message for item in hit])
                for item in findings:
                    self.assertEqual(item.severity, "error")
                    self.assertTrue(item.fix and len(item.fix) > 10, item)
                    self.assertTrue(item.where.startswith("app.py:"), item.where)
                    self.assertTrue(item.doc.startswith("https://docs.0x1audio.com/"), item.doc)

    def test_ordinary_code_is_not_refused(self):
        for snippet in ALLOWED:
            with self.subTest(snippet=snippet):
                self.assertEqual([(item.code, item.message) for item in scan_source(snippet, "app.py").findings], [])

    def test_the_apps_own_module_named_like_a_banned_one_is_fine(self):
        self.assertEqual(scan_source("import code\ncode.run()", "app.py", local={"code"}).findings, [])

    def test_network_use_needs_the_permission_not_a_ban(self):
        for snippet in ("import urllib.request\nurllib.request.urlopen('https://example.com/a')",
                        "from urllib import request\nrequest.urlopen('https://example.com/a')",
                        "from urllib.request import urlopen as get\nget('https://example.com/a')",
                        "import http.client",
                        "import torch\ntorch.hub.load_state_dict_from_url('https://example.com/m.th')"):
            with self.subTest(snippet=snippet):
                found = scan_source(snippet, "app.py")
                self.assertEqual(found.findings, [])
                self.assertTrue(found.network)


def mixel(*args, cwd):
    return subprocess.run([sys.executable, "-m", "ox1audio.cli", *args], capture_output=True, text=True, cwd=cwd, env={**os.environ, "PYTHONPATH": SRC}, timeout=300)


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        made = mixel("new", "Make It Louder", cwd=self.tmp.name)
        self.assertEqual(made.returncode, 0, made.stderr)
        self.app = Path(self.tmp.name) / "make-it-louder"

    def tearDown(self):
        self.tmp.cleanup()

    def prepend(self, code: str) -> None:
        path = self.app / "app.py"
        path.write_text(code + "\n" + path.read_text())

    def test_banned_api_is_an_error_without_strict(self):
        self.prepend("import subprocess")
        done = mixel("check", "--json", cwd=self.app)
        self.assertEqual(done.returncode, 1, done.stdout)
        report = json.loads(done.stdout)
        self.assertEqual([item["code"] for item in report["errors"]], ["banned_api"])

    def test_refused_code_is_never_run_to_list_its_actions(self):
        marker = Path(self.tmp.name) / "ran"
        self.prepend(f"open({str(marker)!r}, 'w').write('x')\nimport subprocess")
        done = mixel("check", "--json", cwd=self.app)
        self.assertEqual(done.returncode, 1)
        self.assertFalse(marker.exists(), "mixel check ran code it refuses")

    def test_requests_is_banned_and_never_added_to_pyproject(self):
        self.prepend("import requests")
        done = mixel("check", "--fix", "--json", cwd=self.app)
        report = json.loads(done.stdout)
        self.assertEqual([item["code"] for item in report["errors"]], ["banned_api"])
        self.assertIn("urllib.request", report["errors"][0]["fix"])
        self.assertNotIn("requests", (self.app / "pyproject.toml").read_text())

    def test_urlopen_without_network_is_undeclared_and_fix_writes_the_hosts(self):
        self.prepend("import urllib.request\nMODEL = 'https://github.com/me/models/releases/download/v1/m.onnx'\n"
                     "def fetch():\n    return urllib.request.urlopen(MODEL).read()")
        done = mixel("check", "--json", cwd=self.app)
        self.assertEqual(done.returncode, 1)
        error = json.loads(done.stdout)["errors"][0]
        self.assertEqual((error["code"], error["where"]), ("permission_undeclared", "app.json › permissions.network"))
        self.assertIn('"hosts": ["github.com"]', error["fix"])
        mixel("check", "--fix", cwd=self.app)
        network = json.loads((self.app / "app.json").read_text())["permissions"]["network"]
        self.assertEqual(network["hosts"], ["github.com"])
        self.assertTrue(network["why"].startswith("TODO"))
        strict = mixel("check", "--strict", "--json", cwd=self.app)
        self.assertIn("permission_reason", [item["code"] for item in json.loads(strict.stdout)["warnings"]])

    def test_a_compiled_binary_is_refused(self):
        (self.app / "helper.so").write_bytes(b"\x7fELF")
        done = mixel("check", "--json", cwd=self.app)
        self.assertEqual(done.returncode, 1)
        self.assertEqual(json.loads(done.stdout)["errors"][0]["where"], "helper.so")

    def test_tests_may_run_programs(self):
        (self.app / "tests" / "test_tools.py").write_text("import subprocess\n")
        self.assertEqual(mixel("check", "--strict", cwd=self.app).returncode, 0)


if __name__ == "__main__":
    unittest.main()
