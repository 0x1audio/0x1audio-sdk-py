"""mixel test: check the app, then run its tests with the app's own Python, the way Mixel runs it."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from ox1audio.cli import check, out
from ox1audio.cli.out import FAILED, OK, Stop


def command(args: list[str]) -> int:
    as_json = "--json" in args
    pattern = None
    if "-k" in args:
        at = args.index("-k")
        if at + 1 >= len(args):
            raise Stop("-k needs part of a test name.", fix="mixel test -k convert")
        pattern = args[at + 1]
    rest = [arg for i, arg in enumerate(args) if not arg.startswith("-") and (i == 0 or args[i - 1] != "-k")]
    folder = Path(rest[0]).resolve() if rest else Path.cwd()
    result = run(folder, pattern)
    if as_json:
        out.emit(result)
    else:
        show(result)
    return OK if result["ok"] else FAILED


def run(folder: Path, pattern: str | None = None) -> dict:
    """Check, then test. Returns {ok, passed, failed: [{name, where, message}], ...} or check errors."""
    report = check.run(folder)
    if report.errors:
        return {"ok": False, "stage": "check", "errors": [item.json() for item in report.errors][:20]}
    if not (folder / "tests").is_dir():
        return {"ok": False, "stage": "test", "passed": 0, "failed": [], "error": {
            "code": "no_tests", "message": "There is no tests/ folder.", "fix": "add tests/test_app.py with a unittest that calls ox.test(...)",
            "doc": f"{out.DOCS}/actions#testing"}}
    python = interpreter(folder)
    env = app_env(python)
    with tempfile.TemporaryDirectory() as scratch:
        target = Path(scratch) / "result.json"
        command = [python, "-m", "ox1audio.cli._testrun", str(target), *(["-k", pattern] if pattern else [])]
        # One data folder for the whole test run, empty at the start (ox.data as in one Mixel session).
        (Path(scratch) / "data").mkdir()
        done = subprocess.run(command, cwd=folder, env={**env, "OX1_DATA": str(Path(scratch) / "data")}, capture_output=True, text=True, timeout=3600)
        if not target.is_file():
            tail = (done.stderr or done.stdout).strip().splitlines()[-5:]
            return {"ok": False, "stage": "test", "passed": 0, "failed": [], "error": {
                "code": "tests_did_not_run", "message": "The tests didn't run: " + (" ".join(tail) or f"exit {done.returncode}"),
                "fix": "run python -m unittest in the app's folder to see the whole error", "doc": f"{out.DOCS}/actions#testing"}}
        result = json.loads(target.read_text())
    failed = result["failed"]
    for item in failed:
        if item.get("missing"):
            name = item["missing"]
            item["fix"] = f"{name} isn't installed where the tests run. List it in pyproject.toml › [project].dependencies (mixel check --fix does), then: uv sync"
    found = bool(result["passed"] or failed or result["skipped"])
    output = (done.stdout + done.stderr).strip().splitlines()
    return {
        "ok": not failed and found,
        "stage": "test",
        "passed": result["passed"],
        "failed": failed,
        "skipped": result["skipped"],
        "seconds": result["seconds"],
        "python": "app .venv" if python != sys.executable else "mixel's",
        **({"log_tail": output[-40:]} if failed and output else {}),
        **({} if found else {"error": {"code": "no_tests", "message": "tests/ has no tests" + (f" matching {pattern}" if pattern else "") + ".",
                                       "fix": "name test files test_*.py, with unittest.TestCase classes", "doc": f"{out.DOCS}/actions#testing"}}),
    }


def interpreter(folder: Path) -> str:
    """The app's .venv when it has one (uv sync and mixel dev make it), else the Python mixel runs on."""
    for candidate in (folder / ".venv" / "bin" / "python", folder / ".venv" / "Scripts" / "python.exe"):
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def app_env(python: str) -> dict:
    """The environment for running app code with ``python``: this SDK first, then its own packages
    (ffmpeg, the HTTP client) when the app's .venv doesn't have them. The app's packages come from its .venv."""
    sdk = str(Path(__file__).resolve().parents[2])
    paths = [sdk]
    if python != sys.executable:
        # Every site-packages mixel itself sees (including ones a .pth file adds), after the SDK.
        paths += [entry for entry in sys.path if entry.endswith(("site-packages", "dist-packages")) and Path(entry).is_dir() and entry not in paths]
    current = os.environ.get("PYTHONPATH", "")
    return {**os.environ, "PYTHONPATH": os.pathsep.join(paths + ([current] if current else [])), "PYTHONDONTWRITEBYTECODE": "1"}


def show(result: dict) -> None:
    if result["stage"] == "check":
        print("mixel check found errors. Fix them first: tests run against an app that checks clean.\n")
        from ox1audio.manifest import Finding

        out.findings([Finding(item["code"], item["where"], item["message"], item["fix"], item["doc"].split(out.DOCS + "/", 1)[-1], item["severity"]) for item in result["errors"]])
        return
    error = result.get("error")
    if error and not result.get("failed"):
        print(f"{out.color('error', 'error')}  {error['code']}\n       {error['message']}\n       fix:  {error['fix']}\n       docs: {error['doc']}")
        return
    for item in result["failed"]:
        print(f"{out.color('fail ', 'error')}  {item['name']}{'  ' + item['where'] if item.get('where') else ''}")
        for line in item["message"].splitlines():
            print(f"       {line}")
        if item.get("fix"):
            print(f"       fix:  {item['fix']}")
        print()
    if result["failed"] and result.get("log_tail"):
        print("Output\n" + "\n".join(f"  {line}" for line in result["log_tail"][-15:]) + "\n")
    parts = [f"{result['passed']} passed"]
    if result["failed"]:
        parts.append(f"{len(result['failed'])} failed")
    if result.get("skipped"):
        parts.append(f"{result['skipped']} skipped")
    print(f"{', '.join(parts)} in {result['seconds']:g} s.")
