import asyncio
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from ox1audio.api import connect
from ox1audio.cloud import AuthenticatedClient, Client
from ox1audio.cloud.api.default import app_catalog, cli_login, create_submission, health, me, revoke_cli_token
from ox1audio.cloud.models import CliLoginBody, RevokeCliTokenBody, SubmissionBody
from ox1audio.errors import MixelApiError, MixelError, MixelTimeoutError, MixelUnavailableError

ROOT = Path(__file__).resolve().parents[1]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.route()

    def do_POST(self):
        self.route()

    def route(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b""
        self.server.seen.append((self.command, self.path, self.headers.get("Authorization"), raw))
        answers = self.server.routes.get((self.command, self.path.split("?")[0]), [(404, {"error": {"code": "not_found", "message": "no route"}}, {})])
        status, body, headers = answers.pop(0) if len(answers) > 1 else answers[0]
        if self.server.delay:
            time.sleep(self.server.delay)
        data = b"" if body is None else json.dumps(body).encode()
        try:
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            for name, value in headers.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass  # the client gave up first (the timeout test)

    def log_message(self, fmt, *args):
        return


class CloudTest(unittest.TestCase):
    def setUp(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.httpd.routes = {}
        self.httpd.seen = []
        self.httpd.delay = 0
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        host, port = self.httpd.server_address
        self.url = f"http://{host}:{port}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def route(self, method, path, *answers):
        self.httpd.routes[(method, path)] = [answer if len(answer) == 3 else (*answer, {}) for answer in answers]

    def test_calls_return_their_models_and_send_the_token_and_body(self):
        self.route("GET", "/api/v1/health", (200, {"status": "ok"}))
        self.route("POST", "/api/v1/cli/login", (200, {"device_code": "d", "user_code": "CALM-RIVER-42", "verification_url": "https://cloud.0x1audio.com/cli", "interval": 5, "expires_in": 600}))
        self.route("POST", "/api/v1/account/cli-tokens/revoke", (204, None))
        cloud = connect("mxl_secret", base_url=self.url)
        self.assertIsInstance(cloud, AuthenticatedClient)
        self.assertEqual(health.sync(client=cloud).status, "ok")
        method, path, authorization, raw = self.httpd.seen[0]
        self.assertEqual((method, path, authorization, raw), ("GET", "/api/v1/health", "Bearer mxl_secret", b""))
        device = cli_login.sync(client=cloud, body=CliLoginBody(client="my script"))
        self.assertEqual(device.user_code, "CALM-RIVER-42")
        self.assertEqual(json.loads(self.httpd.seen[-1][3]), {"client": "my script"})
        self.assertEqual(revoke_cli_token.sync_detailed(client=cloud, body=RevokeCliTokenBody(id="t1")).status_code, 204)

    def test_the_token_comes_from_mixel_token_or_mixel_login_and_none_is_signed_out(self):
        self.route("GET", "/api/v1/health", (200, {"status": "ok"}))
        with mock.patch.dict("os.environ", {"MIXEL_API": self.url, "MIXEL_TOKEN": "mxl_from_env"}):
            health.sync(client=connect())
        self.assertEqual(self.httpd.seen[-1][2], "Bearer mxl_from_env")
        with mock.patch("ox1audio.cli.registry.token", return_value=None):
            signed_out = connect(base_url=self.url)
        self.assertIsInstance(signed_out, Client)
        health.sync(client=signed_out)
        self.assertIsNone(self.httpd.seen[-1][2])

    def test_an_error_status_raises_a_mixel_api_error_with_every_problem(self):
        self.route("GET", "/api/v1/me", (401, {"error": {"code": "unauthenticated", "message": "Sign in to continue."}}))
        self.route("POST", "/api/v1/registry/submissions", (400, {
            "error": {"code": "manifest_invalid", "message": "app.json has 2 problems.", "fix": "mixel check", "doc_url": "https://docs.0x1audio.com/errors#manifest_invalid"},
            "errors": [{"code": "manifest_summary", "message": "summary is missing."}, {"code": "sdk_missing", "message": "app.json has no sdk range.", "param": "sdk"}],
        }))
        cloud = connect("mxl_secret", base_url=self.url)
        with self.assertRaises(MixelApiError) as denied:
            me.sync(client=cloud)
        self.assertIsInstance(denied.exception, MixelError)
        self.assertEqual((denied.exception.status, denied.exception.code, denied.exception.message), (401, "unauthenticated", "Sign in to continue."))
        self.assertEqual(denied.exception.to_dict(), {"code": "unauthenticated", "message": "Sign in to continue.", "status": 401})
        with self.assertRaises(MixelApiError) as refused:
            create_submission.sync(client=cloud, body=SubmissionBody(repository="ada/app", commit="0" * 40))
        self.assertEqual(refused.exception.fix, "mixel check")
        self.assertEqual(refused.exception.doc_url, "https://docs.0x1audio.com/errors#manifest_invalid")
        self.assertEqual([problem["code"] for problem in refused.exception.errors], ["manifest_summary", "sdk_missing"])
        self.assertEqual(len([seen for seen in self.httpd.seen if seen[0] == "POST"]), 1, "a POST is never sent twice")

    def test_a_get_is_retried_after_503_and_429_honouring_retry_after_a_post_is_not(self):
        self.route("GET", "/api/v1/health", (503, {"error": {"code": "unavailable", "message": "A dependency is quiet."}}),
                   (429, {"error": {"code": "rate_limited", "message": "Slow down."}}, {"retry-after": "0"}), (200, {"status": "ok"}))
        self.route("POST", "/api/v1/cli/login", (503, {"error": {"code": "unavailable", "message": "A dependency is quiet."}}))
        cloud = connect("mxl_secret", base_url=self.url)
        self.assertEqual(health.sync(client=cloud).status, "ok")
        self.assertEqual(len(self.httpd.seen), 3)
        with self.assertRaises(MixelApiError) as failed:
            cli_login.sync(client=cloud, body=CliLoginBody())
        self.assertEqual(failed.exception.status, 503)
        self.assertEqual(len(self.httpd.seen), 4)

    def test_a_429_that_asks_for_a_long_wait_comes_back_at_once(self):
        self.route("GET", "/api/v1/registry/catalog", (429, {"error": {"code": "rate_limited", "message": "Slow down."}}, {"retry-after": "120"}))
        started = time.monotonic()
        with self.assertRaises(MixelApiError) as failed:
            app_catalog.sync(client=connect("mxl_secret", base_url=self.url))
        self.assertEqual(failed.exception.code, "rate_limited")
        self.assertEqual(len(self.httpd.seen), 1)
        self.assertLess(time.monotonic() - started, 10, "it didn't wait out the 120 s")

    def test_a_slow_cloud_is_a_timeout_after_the_retries(self):
        self.route("GET", "/api/v1/health", (200, {"status": "ok"}))
        self.httpd.delay = 0.4
        with self.assertRaises(MixelTimeoutError) as failed:
            health.sync(client=connect("mxl_secret", base_url=self.url, timeout=0.05, retries=1))
        self.assertEqual(failed.exception.code, "timeout")
        time.sleep(0.5)
        self.assertEqual(len(self.httpd.seen), 2)

    def test_an_unreachable_cloud_is_unavailable_with_code_network(self):
        with self.assertRaises(MixelUnavailableError) as failed:
            health.sync(client=connect("mxl_secret", base_url="http://127.0.0.1:9", retries=1))
        self.assertEqual(failed.exception.code, "network")
        self.assertIn("MIXEL_API", failed.exception.fix)

    def test_asyncio_behaves_the_same(self):
        self.route("GET", "/api/v1/health", (503, {"error": {"code": "unavailable", "message": "A dependency is quiet."}}), (200, {"status": "ok"}))
        self.route("GET", "/api/v1/me", (403, {"error": {"code": "waitlisted", "message": "You're on the waitlist."}}))
        cloud = connect("mxl_secret", base_url=self.url)

        async def both():
            ok = await health.asyncio(client=cloud)
            with self.assertRaises(MixelApiError) as failed:
                await me.asyncio(client=cloud)
            return ok, failed.exception

        ok, failed = asyncio.run(both())
        self.assertEqual(ok.status, "ok")
        self.assertEqual(failed.code, "waitlisted")


class SpecTest(unittest.TestCase):
    def test_openapi_json_is_the_public_list_and_matches_sdk_ts(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("openapi_script", ROOT / "scripts" / "openapi.py")
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        document = json.loads((ROOT / "openapi.json").read_text())
        operations = sorted(op["operationId"] for item in document["paths"].values() for op in item.values() if isinstance(op, dict) and "operationId" in op)
        self.assertEqual(operations, sorted(script.PUBLIC))
        self.assertNotRegex(json.dumps(document["paths"]), r"/review/|/admin/|billing|webhook")
        # The same cut as sdk-ts, byte for byte, when it's checked out beside this repo.
        twin = ROOT.parent / "0x1audio-sdk-ts" / "openapi.json"
        if twin.is_file() and json.loads(twin.read_text()).get("info", {}).get("title") == "Mixel API":
            self.assertEqual(twin.read_text(), (ROOT / "openapi.json").read_text())

    def test_the_cut_drops_private_routes_and_internal_pointers(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("openapi_script", ROOT / "scripts" / "openapi.py")
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        source = {"openapi": "3.1.0", "info": {"title": "x", "version": "1"}, "paths": {}, "components": {"schemas": {
            "Health": {"type": "object", "description": "Ok (launch.md 1.4) now"}, "Secret": {"type": "object"}}}}
        for name in script.PUBLIC:
            source["paths"][f"/api/v1/{name}"] = {"get": {"operationId": name, "responses": {"200": {"description": "x", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Health"}}}}}}}
        source["paths"]["/api/v1/admin/members"] = {"get": {"operationId": "adminMember", "responses": {"200": {"description": "x", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Secret"}}}}}}}
        cut = script.cut(source)
        self.assertNotIn("/api/v1/admin/members", cut["paths"])
        self.assertEqual(list(cut["components"]["schemas"]), ["Health"])
        self.assertEqual(cut["components"]["schemas"]["Health"]["description"], "Ok now")
        self.assertEqual(script.changes(cut, {**cut, "paths": {}}), [f"removed  operation {name} (GET /api/v1/{name})" for name in script.PUBLIC])


if __name__ == "__main__":
    unittest.main()
