import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

from ox1audio.cloud import AuthenticatedClient
from ox1audio.cloud.api.default import health, login, logout, session
from ox1audio.cloud.models.account import Account
from ox1audio.cloud.models.error import Error
from ox1audio.cloud.models.login_body import LoginBody


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.route()

    def do_POST(self):
        self.route()

    def route(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b""
        self.server.seen.append((self.command, self.path, self.headers.get("Authorization"), raw))
        status, body = self.server.routes.get(
            (self.command, self.path),
            (404, {"error": {"code": "missing", "message": "no route"}}),
        )
        data = b"" if body is None else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        return


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.routes = {
            ("GET", "/api/v1/health"): (200, {"status": "ok"}),
            ("GET", "/api/v1/auth/session"): (401, {"error": {"code": "unauthorized", "message": "sign in"}}),
            ("POST", "/api/v1/auth/login"): (
                200,
                {"id": "00000000-0000-4000-8000-000000000001", "email": "ada@example.com"},
            ),
            ("POST", "/api/v1/auth/logout"): (204, None),
        }
        self.httpd.seen = []
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.httpd.server_address
        self.client = AuthenticatedClient(base_url=f"http://{host}:{port}", token="secret")

    def tearDown(self):
        self.client.get_httpx_client().close()
        self.httpd.shutdown()
        self.httpd.server_close()

    def test_health_and_bearer_token(self):
        body = health.sync(client=self.client)
        self.assertEqual(getattr(body, "status", None), "ok")
        method, path, authorization, raw = self.httpd.seen[0]
        self.assertEqual((method, path, authorization, raw), ("GET", "/api/v1/health", "Bearer secret", b""))

    def test_login_posts_the_body(self):
        account = login.sync(client=self.client, body=LoginBody(email="ada@example.com", password="correct horse"))
        self.assertIsInstance(account, Account)
        self.assertEqual(account.email, "ada@example.com")
        _, path, _, raw = self.httpd.seen[-1]
        self.assertEqual(path, "/api/v1/auth/login")
        self.assertEqual(json.loads(raw), {"email": "ada@example.com", "password": "correct horse"})

    def test_error_carries_the_server_message(self):
        body = session.sync(client=self.client)
        self.assertIsInstance(body, Error)
        self.assertEqual(body.error.code, "unauthorized")
        self.assertEqual(body.error.message, "sign in")

    def test_logout_has_no_body(self):
        self.assertIsNone(logout.sync_detailed(client=self.client).parsed)
        method, path, _, raw = self.httpd.seen[-1]
        self.assertEqual((method, path, raw), ("POST", "/api/v1/auth/logout", b""))

    def test_unreachable_host(self):
        client = AuthenticatedClient(base_url="http://127.0.0.1:9", token="secret", timeout=httpx.Timeout(0.5))
        try:
            with self.assertRaises(httpx.ConnectError):
                health.sync(client=client)
        finally:
            client.get_httpx_client().close()


if __name__ == "__main__":
    unittest.main()
