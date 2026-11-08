"""GAB-37: one contract. Every generated file matches it, budgets hold, and the rules reach mixel check."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ox1audio import _contract
from ox1audio.manifest import check

ROOT = Path(__file__).resolve().parents[1]


class ContractTest(unittest.TestCase):
    def test_every_generated_file_is_up_to_date(self):
        done = subprocess.run([sys.executable, str(ROOT / "contract" / "generate.py"), "--check"], capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_the_rules_come_from_the_schema(self):
        schema = json.loads((ROOT / "contract" / "app.schema.json").read_text())
        self.assertEqual(_contract.FIELDS, list(schema["properties"]))
        self.assertEqual(_contract.SCHEMA, schema["$id"])
        self.assertEqual(sorted(_contract.PERMISSIONS), sorted(schema["properties"]["permissions"]["properties"]))

    def test_every_check_code_in_the_code_is_documented(self):
        import re

        used = set()
        for path in (ROOT / "src" / "ox1audio").rglob("*.py"):
            used |= set(re.findall(r'(?:Finding\(|bad\()\s*"([a-z_]+)"', path.read_text()))
        self.assertTrue(used)
        self.assertEqual(sorted(used - set(_contract.ERRORS)), [], "add these to contract/errors.json")

    def test_window_and_tags_are_checked_like_the_desktop_does(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "app.py").write_text("")
            base = {"$schema": _contract.SCHEMA, "name": "my-app", "displayName": "My App", "version": "0.1.0", "sdk": "^0.3", "entry": "app.py"}
            (root / "app.json").write_text(json.dumps({**base, "window": {"width": 90}, "tags": ["two words"]}))
            codes = [(item.code, item.where) for item in check(root).findings]
            self.assertIn(("manifest_window", "app.json › window.width"), codes)
            self.assertIn(("manifest_tags", "app.json › tags"), codes)
            (root / "app.json").write_text(json.dumps({**base, "window": {"width": 900, "height": 640}, "tags": ["convert"]}))
            self.assertEqual(check(root).findings, [])


if __name__ == "__main__":
    unittest.main()
