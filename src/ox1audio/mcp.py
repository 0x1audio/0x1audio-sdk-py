"""mixel mcp: a local MCP server for coding agents, over stdio (GAB-41).

    mixel mcp                     the core tools
    mixel mcp --read-only         only tools that change nothing
    mixel mcp --features publish  also app_publish (it defaults to a dry run)

No network, no account: it reads and writes app folders through the same code as the
CLI. Tool results are compact JSON (diagnostics with codes and fixes, not docs), and
long docs are resources: mixel://agents.md, mixel://docs/{slug}, mixel://errors/{code},
mixel://schema/app/v1.json. Tool order never changes, so prompt caches keep hitting.
"""

from __future__ import annotations

import contextlib
import json
import re
import sys
from pathlib import Path

from ox1audio import __version__, _contract

PROTOCOLS = ("2026-07-28", "2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
DOCS = Path(__file__).resolve().parent / "docs"

INSTRUCTIONS = (
    "Builds Mixel apps: typed Python actions (import ox1audio as ox) that Mixel runs on the person's computer. "
    "Call start first. Fix every app_check error with its fix line before app_test. Never publish or widen permissions unless the person asks."
)

_dir = {"type": "string", "description": "The app's folder, absolute"}


def _obj(properties: dict, required: list[str] | None = None) -> dict:
    found: dict = {"type": "object", "properties": properties}
    if required:
        found["required"] = required
    return found


# {code, where, message, fix, doc}
_finding = {"type": "object"}

# name, description, input schema, output schema, annotations, read-only
TOOLS: list[tuple[str, str, dict, dict, dict]] = [
    ("start", "Start here: the rules in short, and what to call next.", _obj({}),
     _obj({"sdk": {"type": "string"}, "rules": {"type": "string"}, "agents_md": {"type": "string"}, "next": {"type": "array", "items": {"type": "string"}}}),
     {"readOnlyHint": True, "openWorldHint": False}),
    ("docs_search", "Find docs sections by words. Returns slugs and short snippets.", _obj({"q": {"type": "string"}, "k": {"type": "integer", "minimum": 1, "maximum": 5}}, ["q"]),
     _obj({"results": {"type": "array", "items": _obj({"slug": {"type": "string"}, "section": {"type": "string"}, "snippet": {"type": "string"}})}}),
     {"readOnlyHint": True, "openWorldHint": False}),
    ("docs_read", "Read one docs page, or one section of it.", _obj({"slug": {"type": "string"}, "section": {"type": "string"}}, ["slug"]),
     _obj({"slug": {"type": "string"}, "markdown": {"type": "string"}, "truncated": {"type": "boolean"}}),
     {"readOnlyHint": True, "openWorldHint": False}),
    ("app_new", "Create an app folder that checks clean, with a test. Refuses a folder that has files.",
     _obj({"parent": {"type": "string", "description": "Folder to create the app in, absolute"}, "name": {"type": "string", "description": "Display name, like Make It Louder"}}, ["parent", "name"]),
     _obj({"dir": {"type": "string"}, "files": {"type": "array", "items": {"type": "string"}}, "next": {"type": "string"}}),
     {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}),
    ("app_check", "The gate Mixel and reviewers apply. Errors carry a code and a one-line fix. fix=true adds missing permissions.",
     _obj({"dir": _dir, "fix": {"type": "boolean"}, "strict": {"type": "boolean"}}, ["dir"]),
     _obj({"ok": {"type": "boolean"}, "errors": {"type": "array", "items": _finding}, "warnings": {"type": "array", "items": _finding}, "actions": {"type": "array", "items": {"type": "string"}}}),
     {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}),
    ("app_describe", "What Mixel will see: each action's input schema, and the permissions.", _obj({"dir": _dir}, ["dir"]),
     _obj({"actions": {"type": "array", "items": {"type": "object"}}, "permissions": {"type": "object"}, "page": {"type": ["string", "null"]}}),
     {"readOnlyHint": True, "openWorldHint": False}),
    ("app_run", "Run one action on real files, the way Mixel would. Returns the result, Library items and a log tail.",
     _obj({"dir": _dir, "action": {"type": "string"}, "input": {"type": "object"}, "files": {"type": "array", "items": {"type": "string"}, "description": "Absolute paths for the Files control"}}, ["dir", "action"]),
     _obj({"ok": {"type": "boolean"}, "result": {}, "items": {"type": "array"}, "progress_calls": {"type": "integer"}, "error": {"type": "object"}, "log_tail": {"type": "array", "items": {"type": "string"}}}),
     {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}),
    ("app_test", "Check, then run tests/. Returns failures only, each with file:line.", _obj({"dir": _dir, "k": {"type": "string", "description": "Part of a test name"}}, ["dir"]),
     _obj({"ok": {"type": "boolean"}, "passed": {"type": "integer"}, "failed": {"type": "array"}, "errors": {"type": "array"}}),
     {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}),
    ("app_status", "Review state and reviewer notes for the app's submissions. Needs mixel login.", _obj({"dir": _dir}, ["dir"]),
     _obj({"app": {"type": "string"}, "submissions": {"type": "array"}}),
     {"readOnlyHint": True, "openWorldHint": True}),
    ("library_search", "Search the person's own Library in plain words. Off unless the person turns it on in Mixel.",
     _obj({"query": {"type": "string"}, "k": {"type": "integer", "minimum": 1, "maximum": 20}, "kind": {"type": "string", "enum": ["sound", "midi", "other"]}}, ["query"]),
     _obj({"available": {"type": "boolean"}, "results": {"type": "array", "items": _obj({"id": {"type": "string"}, "title": {"type": "string"}, "kind": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}, "why": {"type": "string"}})}, "reason": {"type": "string"}, "fix": {"type": "string"}}),
     {"readOnlyHint": True, "openWorldHint": False}),
]

PUBLISH = ("app_publish", "Submit the app's pushed commit for review. dry_run defaults to true; only publish when the person asks.",
           _obj({"dir": _dir, "dry_run": {"type": "boolean", "default": True}}, ["dir"]),
           _obj({"ok": {"type": "boolean"}, "dry_run": {"type": "boolean"}, "app": {"type": "string"}, "version": {"type": "string"}, "commit": {"type": "string"}, "error": {"type": "object"}}),
           {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True})


class ToolError(Exception):
    def __init__(self, code: str, message: str, fix: str = "") -> None:
        super().__init__(message)
        self.body = {"code": code, "message": message, **({"fix": fix} if fix else {})}


def _folder(args: dict) -> Path:
    raw = args.get("dir")
    if not isinstance(raw, str) or not Path(raw).is_absolute():
        raise ToolError("bad_input", "dir is the app folder's absolute path.", "pass the full path, like /Users/ada/my-app")
    folder = Path(raw)
    if not folder.is_dir():
        raise ToolError("bad_input", f"{raw} is not a folder.", "app_new creates an app")
    return folder


# --- tools ------------------------------------------------------------------------------------


def start(args: dict) -> dict:
    return {
        "sdk": __version__,
        "rules": (DOCS / "digest.md").read_text(),
        "agents_md": "mixel://agents.md",
        "next": ["app_new (no app yet)", "app_check (an app exists)", "docs_search (unsure about an API)"],
    }


def _sections() -> list[tuple[str, str, str]]:
    found = []
    for path in sorted(DOCS.glob("*.md")):
        if path.stem == "digest":
            continue
        title, body = path.stem, []
        for line in path.read_text().splitlines():
            if line.startswith("#"):
                if body:
                    found.append((path.stem, title, "\n".join(body).strip()))
                title, body = line.lstrip("# ").strip(), []
            else:
                body.append(line)
        if body:
            found.append((path.stem, title, "\n".join(body).strip()))
    return found


def docs_search(args: dict) -> dict:
    words = [word for word in re.findall(r"[a-z0-9_.]+", str(args.get("q", "")).lower()) if len(word) > 1]
    if not words:
        raise ToolError("bad_input", "q needs at least one word.", 'docs_search {"q": "progress stop"}')
    k = min(5, max(1, int(args.get("k") or 3)))
    scored = []
    for slug, section, body in _sections():
        text = f"{section}\n{body}".lower()
        score = sum(text.count(word) + 3 * section.lower().count(word) for word in words)
        if score:
            first = min((text.find(word) for word in words if word in text), default=0)
            snippet = re.sub(r"\s+", " ", body[max(0, first - 60): first + 140]).strip()
            scored.append((score, slug, section, snippet))
    scored.sort(key=lambda item: -item[0])
    return {"results": [{"slug": slug, "section": section, "snippet": snippet[:200]} for _, slug, section, snippet in scored[:k]]}


def docs_read(args: dict) -> dict:
    slug = str(args.get("slug", ""))
    path = DOCS / f"{slug}.md"
    if not re.fullmatch(r"[a-z0-9-]+", slug) or not path.is_file() or slug == "digest":
        names = ", ".join(sorted(p.stem for p in DOCS.glob("*.md") if p.stem != "digest"))
        raise ToolError("no_such_topic", f"There is no docs page called {slug}.", f"use one of: {names}")
    text = path.read_text()
    section = args.get("section")
    if section:
        parts = [body for s, title, body in _sections() if s == slug and title.lower() == str(section).lower()]
        if not parts:
            titles = ", ".join(title for s, title, _ in _sections() if s == slug)
            raise ToolError("no_such_topic", f"{slug} has no section called {section}.", f"sections: {titles}")
        text = f"## {section}\n\n{parts[0]}"
    return {"slug": slug, "markdown": text[:4000], "truncated": len(text) > 4000}


def app_new(args: dict) -> dict:
    from ox1audio.cli import new as scaffold
    from ox1audio.cli.out import Stop

    parent, name = args.get("parent"), str(args.get("name", "")).strip()
    if not isinstance(parent, str) or not Path(parent).is_absolute() or not Path(parent).is_dir():
        raise ToolError("bad_input", "parent is an existing folder's absolute path.", "pass the folder the app goes in")
    if not name:
        raise ToolError("bad_input", "name is the app's display name.", 'app_new {"name": "Make It Louder"}')
    target = Path(parent) / scaffold.slug(name)
    try:
        scaffold.new(target, name)
    except Stop as error:
        raise ToolError(error.error or "folder_not_empty", error.message, error.fix) from None
    files = sorted(str(path.relative_to(target)) for path in target.rglob("*") if path.is_file())
    return {"dir": str(target), "files": files, "next": "edit app.py and app.json, then app_check"}


def app_check(args: dict) -> dict:
    from ox1audio.cli import check

    report = check.run(_folder(args), fix=bool(args.get("fix")))
    return report.json(strict=bool(args.get("strict")))


def app_describe(args: dict) -> dict:
    from ox1audio.cli import check

    folder = _folder(args)
    report = check.run(folder)
    if report.errors and not report.actions:
        raise ToolError(report.errors[0].code, report.errors[0].message, report.errors[0].fix)
    data = report.data
    return {"actions": [item.spec() for item in report.actions], "permissions": data.get("permissions", {}), "page": data.get("page")}


def app_run(args: dict) -> dict:
    from ox1audio.cli import running

    action = args.get("action")
    if not isinstance(action, str) or not action:
        raise ToolError("bad_input", "action is the function's name.", "app_describe lists them")
    files = [str(item) for item in args.get("files") or []]
    if any(not Path(item).is_absolute() for item in files):
        raise ToolError("bad_input", "files are absolute paths.", "pass full paths")
    result = running.run(_folder(args), action, dict(args.get("input") or {}), files)
    result["log_tail"] = result.get("log_tail", [])[-40:]
    if not result.get("ok"):
        result.pop("events", None)
    return result


def app_test(args: dict) -> dict:
    from ox1audio.cli import testing

    result = testing.run(_folder(args), args.get("k") or None)
    if result.get("ok"):
        result.pop("log_tail", None)
    return result


def app_status(args: dict) -> dict:
    from ox1audio.cli.out import Stop
    from ox1audio.cli.registry import call
    from ox1audio.manifest import check as manifest

    name = manifest(_folder(args)).data.get("name")
    if not isinstance(name, str):
        raise ToolError("manifest_missing", "There is no app.json with a name in dir.", "app_check shows why")
    try:
        status, answer = call("GET", f"/api/v1/registry/submissions?app={name}", what="review status")
    except Stop as error:
        raise ToolError(error.error or "network", error.message, error.fix) from None
    if status >= 400:
        problem = answer.get("error") or {}
        raise ToolError(problem.get("code", "registry_error"), problem.get("message", "The registry refused."), problem.get("fix", ""))
    return {"app": name, "submissions": answer.get("submissions", [])[:10]}


def library_search(args: dict) -> dict:
    """The interface GAB-112 fills in: read-only, local, off unless the person turns it on."""
    query = str(args.get("query", "")).strip()
    if not query:
        raise ToolError("bad_input", "query is what to look for, in words.", 'library_search {"query": "dry vocal chop in D minor"}')
    return {
        "available": False,
        "results": [],
        "reason": "Library search for agents isn't on in this Mixel yet.",
        "fix": "The person turns it on in Mixel › Settings › Library once it ships. Don't try to read their files another way.",
    }


def app_publish(args: dict) -> dict:
    from ox1audio.cli import check, registry
    from ox1audio.cli.out import Stop

    folder = _folder(args)
    report = check.run(folder)
    if not report.ok(strict=True):
        return {"ok": False, "stage": "check", **report.json(strict=True)}
    try:
        target = registry.where(folder)
        summary = {"app": report.data.get("name"), "version": report.data.get("version"), "commit": target["commit"], "repository": target["repository"]}
        if args.get("dry_run", True) is not False:
            return {"ok": True, "dry_run": True, **summary}
        status, answer = registry.call("POST", "/api/v1/registry/submissions", target, what="submissions")
    except Stop as error:
        raise ToolError(error.error or "registry_error", error.message, error.fix) from None
    if status >= 400:
        problem = answer.get("error") or {}
        raise ToolError(problem.get("code", "registry_error"), problem.get("message", "The registry refused."), problem.get("fix", ""))
    return {"ok": True, "dry_run": False, **summary, "submission": answer}


HANDLERS = {name: globals()[name] for name in [tool[0] for tool in TOOLS] + ["app_publish"]}


# --- resources --------------------------------------------------------------------------------


def resources() -> list[dict]:
    listed = [
        {"uri": "mixel://agents.md", "name": "AGENTS.md", "description": "The whole contract for building an app, under 2k tokens", "mimeType": "text/markdown"},
        {"uri": "mixel://schema/app/v1.json", "name": "app.json schema", "description": "JSON Schema for app.json v1", "mimeType": "application/schema+json"},
        {"uri": "mixel://llms.txt", "name": "llms.txt", "description": "Where the docs are", "mimeType": "text/plain"},
    ]
    for path in sorted(DOCS.glob("*.md")):
        if path.stem not in {"agents", "digest"}:
            listed.append({"uri": f"mixel://docs/{path.stem}", "name": path.stem, "mimeType": "text/markdown"})
    return listed


def templates() -> list[dict]:
    return [
        {"uriTemplate": "mixel://docs/{slug}", "name": "A docs page", "mimeType": "text/markdown"},
        {"uriTemplate": "mixel://errors/{code}", "name": "One error code: what it means and the fix", "mimeType": "text/markdown"},
    ]


def read_resource(uri: str) -> tuple[str, str]:
    if uri == "mixel://agents.md":
        return (DOCS / "agents.md").read_text(), "text/markdown"
    if uri == "mixel://schema/app/v1.json":
        return (Path(__file__).resolve().parent / "app.schema.json").read_text(), "application/schema+json"
    if uri == "mixel://llms.txt":
        return (DOCS / "llms.txt").read_text(), "text/plain"
    found = re.fullmatch(r"mixel://docs/([a-z0-9-]+)", uri)
    if found and (DOCS / f"{found.group(1)}.md").is_file():
        return (DOCS / f"{found.group(1)}.md").read_text(), "text/markdown"
    found = re.fullmatch(r"mixel://errors/([a-z_]+)", uri)
    if found and found.group(1) in _contract.ERRORS:
        info = _contract.ERRORS[found.group(1)]
        return f"# {found.group(1)}\n\n{info['means']}\n\nfix: {info['fix']}\n\ndocs: https://docs.0x1audio.com/errors#{found.group(1)}\n", "text/markdown"
    raise LookupError(uri)


# --- JSON-RPC over stdio ----------------------------------------------------------------------


class Server:
    def __init__(self, read_only: bool = False, features: set[str] | None = None) -> None:
        tools = list(TOOLS) + ([PUBLISH] if "publish" in (features or set()) else [])
        if read_only:
            tools = [tool for tool in tools if tool[4].get("readOnlyHint")]
        self.tools = tools
        self.names = {tool[0] for tool in tools}

    def handle(self, message: dict) -> dict | None:
        method, ident, params = message.get("method"), message.get("id"), message.get("params") or {}
        if ident is None:
            return None  # a notification (initialized, cancelled): nothing to answer
        try:
            result = self.dispatch(method, params)
        except LookupError as missing:
            return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32002, "message": f"Resource not found: {missing}"}}
        except _MethodMissing:
            return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": f"Method not found: {method}"}}
        except _BadParams as error:
            return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32602, "message": str(error)}}
        return {"jsonrpc": "2.0", "id": ident, "result": result}

    def dispatch(self, method: str, params: dict) -> dict:
        if method == "initialize":
            asked = params.get("protocolVersion")
            return {
                "protocolVersion": asked if asked in PROTOCOLS else PROTOCOLS[0],
                "capabilities": {"tools": {"listChanged": False}, "resources": {"listChanged": False, "subscribe": False}},
                "serverInfo": {"name": "mixel", "title": "Mixel", "version": __version__},
                "instructions": INSTRUCTIONS,
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [{"name": n, "description": d, "inputSchema": i, "outputSchema": o, "annotations": a} for n, d, i, o, a in self.tools]}
        if method == "tools/call":
            name = params.get("name")
            if name not in self.names:
                raise _BadParams(f"Unknown tool: {name}. Tools: {', '.join(sorted(self.names))}.")
            return self.call(name, params.get("arguments") or {})
        if method == "resources/list":
            return {"resources": resources()}
        if method == "resources/templates/list":
            return {"resourceTemplates": templates()}
        if method == "resources/read":
            text, mime = read_resource(str(params.get("uri", "")))
            return {"contents": [{"uri": params.get("uri"), "mimeType": mime, "text": text}]}
        if method == "prompts/list":
            return {"prompts": []}
        raise _MethodMissing()

    def call(self, name: str, args: dict) -> dict:
        if not isinstance(args, dict):
            raise _BadParams("arguments is an object.")
        try:
            # Tools reuse the CLI, which prints for people; stdout belongs to the protocol.
            with contextlib.redirect_stdout(sys.stderr):
                body = HANDLERS[name](args)
            error = False
        except ToolError as problem:
            body, error = {"error": problem.body}, True
        except Exception as exc:  # noqa: BLE001 - a tool failure is a result the agent can read
            body, error = {"error": {"code": "crashed", "message": f"{type(exc).__name__}: {exc}"}}, True
        text = json.dumps(body, separators=(",", ":"), ensure_ascii=False, default=str)
        result = {"content": [{"type": "text", "text": text}], "isError": error}
        if not error:
            result["structuredContent"] = body
        return result


class _MethodMissing(Exception):
    pass


class _BadParams(Exception):
    pass


def serve(stdin=None, stdout=None, read_only: bool = False, features: set[str] | None = None) -> None:
    server = Server(read_only, features)
    source = stdin or sys.stdin
    sink = stdout or sys.stdout
    for line in source:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            batch = message if isinstance(message, list) else [message]
            replies = [answer for item in batch if isinstance(item, dict) for answer in [server.handle(item)] if answer]
            if not replies:
                continue
            reply = replies if isinstance(message, list) else replies[0]
        sink.write(json.dumps(reply, separators=(",", ":"), ensure_ascii=False, default=str) + "\n")
        sink.flush()


def command(args: list[str]) -> int:
    features: set[str] = set()
    if "--features" in args:
        at = args.index("--features")
        features = set(args[at + 1].split(",")) if at + 1 < len(args) else set()
    serve(read_only="--read-only" in args, features=features)
    return 0
