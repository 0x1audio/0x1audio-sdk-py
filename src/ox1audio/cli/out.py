"""How mixel talks: calm text for people, ``--json`` for tools, and errors that name the fix.

Exit codes: 0 ok, 1 a check or test failed, 2 usage, 3 sign-in, 4 network or registry.
"""

from __future__ import annotations

import json
import os
import sys

from ox1audio.manifest import Finding

DOCS = "https://docs.0x1audio.com"

OK, FAILED, USAGE, AUTH, NETWORK = 0, 1, 2, 3, 4


class Stop(Exception):
    """End the command with a message, a fix, and an exit code."""

    def __init__(self, message: str, fix: str = "", doc: str = "", code: int = USAGE, error: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.fix = fix
        self.doc = doc
        self.exit = code
        self.error = error


def color(text: str, tone: str) -> str:
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return text
    return {"error": "\033[31m", "warn": "\033[33m"}.get(tone, "") + text + "\033[0m"


def findings(items: list[Finding]) -> None:
    errors = [item for item in items if item.severity == "error"]
    warnings = [item for item in items if item.severity != "error"]
    for item in errors + warnings:
        label = color("error", "error") if item.severity == "error" else color("warn ", "warn")
        print(f"{label}  {item.code}  {item.where}")
        for line in item.message.splitlines():
            print(f"       {line}")
        print(f"       fix:  {item.fix}")
        print(f"       docs: {item.doc}\n")


def stop(error: Stop, as_json: bool) -> int:
    if as_json:
        body = {"ok": False, "error": {"code": error.error or "usage", "message": error.message}}
        if error.fix:
            body["error"]["fix"] = error.fix
        if error.doc:
            body["error"]["doc"] = f"{DOCS}/{error.doc}"
        emit(body)
    else:
        lines = [error.message]
        if error.fix:
            lines.append(f"fix:  {error.fix}")
        if error.doc:
            lines.append(f"docs: {DOCS}/{error.doc}")
        print("\n".join(lines), file=sys.stderr)
    return error.exit


def emit(data: object) -> None:
    print(json.dumps(data, indent=None, separators=(",", ":"), ensure_ascii=False))


def count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"
