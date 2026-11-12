"""A stand-in for a running Mixel, for tests: its Library socket (agent/mixel.sock, or on Windows
agent/endpoint.json with a port and token) and its dev socket (dev.json), answering in the shapes the
desktop's electron/agent/tools.ts and electron/apps/dev.ts send. The real thing is checked by
examples/smoke.py with Mixel open.

    with FakeMixel() as fake:
        Mixel(data_dir=fake.data_dir).overview()

Run it on its own to point the examples at it: python tests/fake_mixel.py (prints the folder).
"""

from __future__ import annotations

import json
import os
import shutil
import socketserver
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

COLUMNS = ["id", "title", "type", "key", "bpm", "length", "tier", "reason"]
SOUNDS = [
    ["s1", "Snare Tape 04.wav", "one-shot", None, None, 0.1, "named", "named snare"],
    ["s2", "Snare tight.wav", "one-shot", None, None, 0.1, "named", "named snare"],
    ["s3", "Clap 04.wav", "one-shot", None, None, 0.1, "named", "named clap"],
    ["s4", "Dusty Loop 92.wav", "loop", "F minor", 92, 8, "sounds_like", "sounds like dusty"],
]
TOKEN = "t" * 43


def answer(call: dict, crates: bool, model: bool = True, page_size: int = 10) -> tuple[bool, dict]:
    def refuse(code: str, message: str, fix: str = "") -> tuple[bool, dict]:
        return False, {"error": {"code": code, "message": message, **({"fix": fix} if fix else {})}}

    args = call.get("args") or {}
    tool = call.get("tool")
    if tool == "library_overview":
        return True, {"sounds": 4, "concepts": {"snare": 2, "clap": 1, "loop": 1}}
    if tool == "library_search":
        filters = args.get("filters") or {}
        if "like" in args:
            if not model:
                return refuse("not_ready", "Mixel can't compare sounds yet: the sound model is off or still indexing.", "search with words instead, or ask the person to check Mixel")
            if not any(sound[0] == args["like"] for sound in SOUNDS):
                return refuse("unknown_id", f"{args['like']} isn't an id from a library_search result.", "search again and use the ids it returns")
            return True, {"answerable": True, "columns": COLUMNS, "results": [s for s in SOUNDS if s[0] != args["like"] and s[2] == "one-shot"][:2]}
        want = str(args.get("want") or "").lower()
        if not want and not filters.get("type"):
            return refuse("bad_input", "want is what to find, in a few plain words.", 'library_search {"want": "dusty snare", "avoid": ["clap"]}')
        avoid = [str(word).lower() for word in args.get("avoid") or []]
        found = [s for s in SOUNDS
                 if (not filters.get("type") or s[2] == filters["type"])
                 and all(word in s[1].lower() or word in s[7] for word in want.split())
                 and not any(word in s[1].lower() for word in avoid)]
        if not found:
            return True, {"answerable": False, "nearest": {"snare": 2, "clap": 1}}
        start = int(args.get("offset") or 0)
        page = found[start:start + page_size]
        more = len(found) - start - len(page)
        return True, {"answerable": True, "columns": COLUMNS, "results": page, **({"more": more, "next": start + len(page)} if more > 0 else {})}
    if tool == "propose_crate":
        if not crates:
            return refuse("crates_off", "Proposing crates is off in this Mixel, so nothing was made.", "the person turns it on in Mixel › Settings › Your assistant; tell them what you found instead")
        ids = list(args.get("ids") or [])
        known = [i for i in ids if any(s[0] == i for s in SOUNDS)]
        if not known:
            return refuse("unknown_id", "None of those ids came from a library_search result.", "search again and use the ids it returns")
        return True, {"ok": True, "sounds": len(known), **({"unknown": len(ids) - len(known)} if len(ids) > len(known) else {})}
    return refuse("unknown_tool", "Mixel has three tools: library_overview, library_search and propose_crate.")


class FakeMixel:
    def __init__(self, *, windows: bool = False, drop: int = 0, delay: float = 0.0, crates: bool = True, developer: bool = False,
                 no_model: bool = False, quiet_log: bool = False, page: int = 10) -> None:
        self.windows, self.drop, self.delay, self.crates, self.developer = windows, drop, delay, crates, developer
        # no_model: "like this sound" is refused with not_ready. quiet_log: the log sends nothing, not even headers.
        self.no_model, self.quiet_log, self.page = no_model, quiet_log, page
        self.calls: list[dict] = []
        self.dev_calls: list[tuple[str, str, object]] = []
        self.data_dir = Path(tempfile.mkdtemp(prefix="fake-mixel-"))
        self._servers: list = []

    def __enter__(self) -> FakeMixel:
        agent = self.data_dir / "agent"
        agent.mkdir(mode=0o700)
        fake = self

        class Library(socketserver.StreamRequestHandler):
            def handle(self) -> None:
                line = self.rfile.readline()
                if not line:
                    return
                if fake.drop > 0:
                    fake.drop -= 1
                    return
                call = json.loads(line)
                fake.calls.append({"caller": call.get("caller"), "tool": call.get("tool"), "args": call.get("args"), **({"token": call.get("token")} if fake.windows else {})})
                if fake.delay:
                    time.sleep(fake.delay)
                if fake.windows and call.get("token") != TOKEN:
                    return
                ok, body = answer(call, fake.crates, not fake.no_model, fake.page)
                try:
                    self.wfile.write((json.dumps({"id": call.get("id"), "ok": ok, "text": json.dumps(body)}) + "\n").encode())
                except OSError:
                    pass

        if self.windows:
            server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Library)
            (agent / "endpoint.json").write_text(json.dumps({"port": server.server_address[1], "token": TOKEN}))
        else:
            server = socketserver.ThreadingUnixStreamServer(str(agent / "mixel.sock"), Library)
        server.daemon_threads = True
        self._serve(server)
        if self.developer:
            self._serve(self._dev_server())
        return self

    def _serve(self, server) -> None:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self._servers.append(server)

    def _dev_server(self) -> ThreadingHTTPServer:
        fake = self
        opened = [0]

        class Dev(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:
                pass

            def _send(self, status: int, body: dict) -> None:
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _route(self) -> None:
                length = int(self.headers.get("content-length") or 0)
                body = json.loads(self.rfile.read(length)) if length else None
                fake.dev_calls.append((self.command, self.path, body))
                if self.headers.get("authorization") != f"Bearer {TOKEN}":
                    return self._send(401, {"error": {"code": "unauthorized", "message": "This request doesn't carry the dev socket's token."}})
                parts = [part for part in self.path.split("/") if part]
                if self.command == "GET" and self.path == "/v1/status":
                    return self._send(200, {"mixel": "0.1.17", "sdk": "0.3.4", "protocol": 1})
                if self.command == "POST" and self.path == "/v1/apps":
                    folder = str((body or {}).get("dir") or "")
                    if not os.path.isabs(folder):
                        return self._send(400, {"error": {"code": "bad_input", "message": "dir is the app folder's absolute path.", "fix": "pass the full path"}})
                    opened[0] += 1
                    return self._send(200, {"id": f"dev-{opened[0]}", "displayName": Path(folder).name, "version": "0.1.0"})
                if parts[:2] == ["v1", "apps"] and len(parts) >= 3:
                    if self.command == "POST" and parts[3:] == ["reload"]:
                        return self._send(200, {"ok": True})
                    if self.command == "DELETE" and len(parts) == 3:
                        return self._send(200, {"ok": True})
                    if self.command == "GET" and parts[3:] == ["log"]:
                        if fake.quiet_log:
                            time.sleep(3)
                            return None
                        self.send_response(200)
                        self.send_header("content-type", "application/x-ndjson")
                        self.end_headers()
                        for line in ({"type": "info", "text": "Started the worker."}, {"type": "log", "text": "mono: 1 file"}, {"type": "closed"}):
                            self.wfile.write((json.dumps(line) + "\n").encode())
                        return None
                return self._send(404, {"error": {"code": "not_found", "message": f"{self.command} {self.path} is not part of the dev socket."}})

            do_GET = do_POST = do_DELETE = _route

        server = ThreadingHTTPServer(("127.0.0.1", 0), Dev)
        server.daemon_threads = True
        dev = self.data_dir / "dev.json"
        dev.write_text(json.dumps({"port": server.server_address[1], "token": TOKEN}))
        dev.chmod(0o600)
        return server

    def __exit__(self, *exc) -> None:
        for server in self._servers:
            server.shutdown()
            server.server_close()
        shutil.rmtree(self.data_dir, ignore_errors=True)


if __name__ == "__main__":
    with FakeMixel(developer="--developer" in sys.argv) as running:
        print(running.data_dir, flush=True)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
