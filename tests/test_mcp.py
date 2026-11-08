"""GAB-41: mixel mcp, a local MCP server over stdio."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import ox1audio as ox
from ox1audio.mcp import Server

SRC = str(Path(ox.__file__).resolve().parents[1])


class Session:
    """A real client session: mixel mcp in a subprocess, JSON-RPC lines both ways."""

    def __init__(self, *flags):
        self.process = subprocess.Popen([sys.executable, "-m", "ox1audio.cli", "mcp", *flags], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env={**os.environ, "PYTHONPATH": SRC})
        self.next = 0

    def ask(self, method, params=None):
        self.next += 1
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.next, "method": method, "params": params or {}}) + "\n")
        self.process.stdin.flush()
        reply = json.loads(self.process.stdout.readline())
        assert reply["id"] == self.next, reply
        return reply

    def tool(self, tool_name, **args):
        return self.ask("tools/call", {"name": tool_name, "arguments": args})["result"]

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=10)
        self.process.stdout.close()
        self.process.stderr.close()


class McpTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.session = Session()

    def tearDown(self):
        self.session.close()
        self.tmp.cleanup()

    def test_handshake_and_a_stable_tool_list(self):
        init = self.session.ask("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}})["result"]
        self.assertEqual(init["protocolVersion"], "2025-06-18")
        self.assertEqual(init["serverInfo"]["name"], "mixel")
        self.session.process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        names = [tool["name"] for tool in self.session.ask("tools/list")["result"]["tools"]]
        self.assertEqual(names, ["start", "docs_search", "docs_read", "app_new", "app_check", "app_describe", "app_run", "app_test", "ui_components", "app_status", "library_search"])
        self.assertEqual(names, [tool["name"] for tool in self.session.ask("tools/list")["result"]["tools"]])

    def test_an_agent_builds_checks_runs_and_tests_an_app(self):
        start = self.session.tool("start")
        self.assertIn("ox.progress", start["structuredContent"]["rules"])
        made = self.session.tool("app_new", parent=str(self.root), name="Make It Louder")["structuredContent"]
        app = made["dir"]
        self.assertIn("app.json", made["files"])
        checked = self.session.tool("app_check", dir=app)["structuredContent"]
        self.assertEqual((checked["ok"], checked["actions"]), (True, ["convert"]))
        described = self.session.tool("app_describe", dir=app)["structuredContent"]
        self.assertEqual(described["actions"][0]["input"]["properties"]["format"]["enum"], ["wav", "flac", "mp3"])
        ran = self.session.tool("app_run", dir=app, action="convert", files=[str(Path(app) / "tests" / "tone.wav")], input={"format": "flac"})
        self.assertFalse(ran["isError"])
        self.assertTrue(ran["structuredContent"]["items"][0]["path"].endswith(".flac"))
        tested = self.session.tool("app_test", dir=app)["structuredContent"]
        self.assertEqual((tested["ok"], tested["passed"]), (True, 1))

    def test_a_broken_app_comes_back_as_codes_and_fixes(self):
        app = self.session.tool("app_new", parent=str(self.root), name="Broken")["structuredContent"]["dir"]
        data = json.loads((Path(app) / "app.json").read_text())
        del data["permissions"]["library"]
        (Path(app) / "app.json").write_text(json.dumps(data))
        checked = self.session.tool("app_check", dir=app)["structuredContent"]
        self.assertFalse(checked["ok"])
        self.assertEqual(checked["errors"][0]["code"], "permission_undeclared")
        self.assertTrue(checked["errors"][0]["fix"])
        fixed = self.session.tool("app_check", dir=app, fix=True)["structuredContent"]
        self.assertTrue(fixed["ok"])
        bad = self.session.tool("app_check", dir="relative/path")
        self.assertTrue(bad["isError"])
        self.assertIn('"fix"', bad["content"][0]["text"])

    def test_docs_are_searchable_and_readable(self):
        found = self.session.tool("docs_search", q="stop cancelled kept")["structuredContent"]["results"]
        self.assertTrue(found)
        page = self.session.tool("docs_read", slug=found[0]["slug"])["structuredContent"]
        self.assertTrue(page["markdown"])
        missing = self.session.tool("docs_read", slug="nope")
        self.assertTrue(missing["isError"])
        self.assertIn("use one of", missing["content"][0]["text"])

    def test_resources(self):
        listed = [item["uri"] for item in self.session.ask("resources/list")["result"]["resources"]]
        self.assertIn("mixel://agents.md", listed)
        agents = self.session.ask("resources/read", {"uri": "mixel://agents.md"})["result"]["contents"][0]["text"]
        self.assertIn("mixel check", agents)
        error = self.session.ask("resources/read", {"uri": "mixel://errors/permission_undeclared"})["result"]["contents"][0]["text"]
        self.assertIn("fix:", error)
        schema = json.loads(self.session.ask("resources/read", {"uri": "mixel://schema/app/v1.json"})["result"]["contents"][0]["text"])
        self.assertEqual(schema["$id"], "https://0x1audio.com/schema/app/v1.json")
        self.assertEqual(self.session.ask("resources/read", {"uri": "mixel://nope"})["error"]["code"], -32002)

    def test_ui_components_lists_what_a_page_may_use(self):
        everything = self.session.tool("ui_components")["structuredContent"]
        names = [item["name"] for item in everything["components"]]
        self.assertIn("ActionForm", names)
        self.assertIn("muted-foreground", everything["tokens"]["colour"])
        found = self.session.tool("ui_components", q="progress loading")["structuredContent"]["components"]
        self.assertIn(found[0]["name"], {"Progress", "Skeleton"})

    def test_ui_components_describe_the_exported_waveform_not_a_private_one(self):
        index = self.session.tool("ui_components", q="waveform")["structuredContent"]
        wave = next(item for item in index["components"] if item["name"] == "Waveform")
        self.assertEqual(wave["props"], "label: string, detail?: string, wave?: Wave | null, empty: string, className?: string")
        self.assertNotIn("peaks", wave["props"])
        self.assertIn("waveformFrom(source: Blob | Uint8Array, bars = 120): Promise<Wave>", index["helpers"])
        self.assertEqual(index["types"]["Wave"], "{ peaks: number[]; seconds: number }")

    def test_library_search_is_a_read_only_stub_until_gab_112(self):
        result = self.session.tool("library_search", query="dry vocal chop in D minor")["structuredContent"]
        self.assertEqual((result["available"], result["results"]), (False, []))
        self.assertIn("Settings", result["fix"])


class ModesTest(unittest.TestCase):
    def test_read_only_and_publish_feature(self):
        read_only = [tool["name"] for tool in Server(read_only=True).dispatch("tools/list", {})["tools"]]
        self.assertEqual(read_only, ["start", "docs_search", "docs_read", "app_describe", "ui_components", "app_status", "library_search"])
        self.assertNotIn("app_publish", [tool["name"] for tool in Server().dispatch("tools/list", {})["tools"]])
        publish = [tool for tool in Server(features={"publish"}).dispatch("tools/list", {})["tools"] if tool["name"] == "app_publish"][0]
        self.assertTrue(publish["annotations"]["destructiveHint"])
        self.assertEqual(Server(read_only=True).handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "app_new", "arguments": {}}})["error"]["code"], -32602)

    def test_tool_definitions_stay_small(self):
        text = json.dumps(Server().dispatch("tools/list", {}), separators=(",", ":"))
        # JSON runs about 0.23 tokens a byte (cl100k; 1260 tokens measured at 5472 bytes): 6000 bytes is about 1.4k.
        self.assertLess(len(text.encode()), 6000, "MCP tool definitions are over their 1.4k token budget")


if __name__ == "__main__":
    unittest.main()
