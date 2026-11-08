"""mixel run ACTION: run one action here, on real files, and see its progress and result."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from ox1audio.cli import out
from ox1audio.cli.out import FAILED, OK, Stop
from ox1audio.cli.testing import app_env, interpreter

USAGE = "mixel run ACTION [--file PATH ...] [--set NAME=VALUE ...] [--out FOLDER] [--json]"


def command(args: list[str]) -> int:
    as_json = "--json" in args
    files: list[str] = []
    out_dir: str | None = None
    values: dict[str, object] = {}
    positional: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in {"--file", "--set", "--out"}:
            if i + 1 >= len(args):
                raise Stop(f"{arg} needs a value.", fix=USAGE)
            value = args[i + 1]
            if arg == "--file":
                files.append(str(Path(value).resolve()))
            elif arg == "--out":
                out_dir = str(Path(value).resolve())
            else:
                name, sep, raw = value.partition("=")
                if not sep or not name:
                    raise Stop(f"--set {value} is not NAME=VALUE.", fix='mixel run convert --set format=flac')
                values[name] = _value(raw)
            i += 2
            continue
        if arg != "--json":
            positional.append(arg)
        i += 1
    if not positional:
        raise Stop("mixel run needs an action name.", fix=USAGE)
    result = run(Path.cwd(), positional[0], values, files, live=not as_json, out=out_dir)
    if as_json:
        out.emit(result)
    else:
        show(result)
    return OK if result["ok"] else FAILED


def _value(raw: str) -> object:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def run(folder: Path, action: str, values: dict | None = None, files: list[str] | None = None, live: bool = False, out: str | None = None) -> dict:
    """Run ``action`` from the app in ``folder``. --file paths fill the action's Files control.

    What the action makes stays on disk (it would go to the Library); ``out`` copies it to a folder.
    """
    from ox1audio.manifest import check as manifest

    folder = folder.resolve()
    data = manifest(folder).data
    entry = data.get("entry")
    if not isinstance(entry, str) or not (folder / entry).is_file():
        return {"ok": False, "error": {"code": "manifest_entry", "message": "app.json has no entry file here.", "fix": "run mixel check"}}
    given = dict(values or {})
    if files:
        control = _files_control(folder / entry, action)
        if control == ("", False):
            return {"ok": False, "error": {"code": "no_such_action", "message": f"{entry} has no action called {action}.", "fix": "mixel check lists the actions"}}
        if control is None:
            return {"ok": False, "error": {"code": "bad_input", "message": f"{action} has no Files control for --file.", "fix": "use --set NAME=VALUE"}}
        name, multiple = control
        given.setdefault(name, files if multiple else files[0])
    python = interpreter(folder)
    process = subprocess.Popen(
        [python, "-m", "ox1audio.cli._actionrun", str(folder / entry), action, json.dumps(given), *([out] if out else [])],
        cwd=folder, env=app_env(python), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    final: dict = {}
    events: list = []
    log: list[str] = []
    import threading

    reader = threading.Thread(target=lambda: log.extend(process.stderr or []), daemon=True)
    reader.start()
    for line in process.stdout or []:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if message["type"] == "progress" and live:
            fraction = message["fraction"]
            print(f"{'  …' if fraction is None else f'{round(fraction * 100):>3}%'}  {message['label']}".rstrip(), flush=True)
        elif message["type"] == "event":
            events.append([message["name"], message["body"]])
            if live:
                print(f"event  {message['name']}  {json.dumps(message['body'])[:200]}", flush=True)
        elif message["type"] in {"done", "error"}:
            final = message
    process.wait()
    reader.join(timeout=5)
    tail = [line.rstrip("\n") for line in log][-40:]
    if final.get("type") == "done":
        return {"ok": True, "result": final["result"], "items": final["items"], "progress_calls": final["progress_calls"], "events": events, "log_tail": tail}
    error = final.get("error") or {"code": "crashed", "message": "The action stopped without a result.", "fix": "read the log below"}
    return {"ok": False, "error": error, "items": final.get("items", []), "events": events, "log_tail": tail}


def _files_control(entry: Path, action: str) -> tuple[str, bool] | None:
    import ast

    tree = ast.parse(entry.read_text(errors="replace"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == action:
            for arg in node.args.args:
                text = ast.unparse(arg.annotation) if arg.annotation is not None else ""
                if "Files(" in text:
                    return arg.arg, "multiple=False" not in text.replace(" ", "")
            return None
    return "", False


def show(result: dict) -> None:
    if not result["ok"]:
        error = result["error"]
        if result.get("log_tail") and error.get("code") == "crashed":
            print("Log\n" + "\n".join(f"  {line}" for line in result["log_tail"][-15:]) + "\n")
        print(f"{out.color('error', 'error')}  {error['code']}{'  ' + error['where'] if error.get('where') else ''}\n       {error['message']}")
        if error.get("hint"):
            print(f"       hint: {error['hint']}")
        if error.get("fix"):
            print(f"       fix:  {error['fix']}")
        return
    items = result["items"]
    if items:
        print(f"Result  {out.count(len(items), 'item')} for the Library")
        for item in items:
            meta = item.get("metadata") or {}
            detail = f"  {meta['duration']:.1f} s" if isinstance(meta.get("duration"), (int, float)) else ""
            print(f"  {item['kind']:<6} {item['title']}{detail}  {item['path']}")
        print("The files stay where they are, for you to listen to; delete them when you're done.")
    elif result["result"] is not None:
        print("Result  " + (result["result"] if isinstance(result["result"], str) else json.dumps(result["result"])[:500]))
    else:
        print("Result  nothing (the action returned None)")
    if not result["progress_calls"]:
        print("note   it never called ox.progress, so Stop can't reach it")
