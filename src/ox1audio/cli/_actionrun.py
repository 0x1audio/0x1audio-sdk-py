"""Runs one action of an app here, the way Mixel would, and reports as NDJSON. ``mixel run`` starts it.

    python -m ox1audio.cli._actionrun ENTRY ACTION INPUT_JSON

stdout carries only report lines; the app's own print goes to stderr.
"""

from __future__ import annotations

import json
import sys
import threading
import traceback
from pathlib import Path


def main(argv: list[str]) -> int:
    entry, name, given = Path(argv[0]).resolve(), argv[1], json.loads(argv[2])
    report = sys.stdout
    sys.stdout = sys.stderr

    def send(message: dict) -> None:
        report.write(json.dumps(message) + "\n")
        report.flush()

    from ox1audio import app as runner
    from ox1audio.action import BadInput, Cancelled, Problem, actions, call, find, stopped_message
    from ox1audio.runtime import sink_var

    sys.path.insert(0, str(entry.parent))
    runner._loading = True
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(entry.stem if entry.stem.isidentifier() else "app", entry)
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        sys.modules[spec.name] = module  # type: ignore[union-attr]
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except BaseException as exc:  # noqa: BLE001
        traceback.print_exc()
        send({"type": "error", "error": {"code": "app_failed_to_load", "message": f"{entry.name} could not start: {type(exc).__name__}: {exc}", "fix": "run mixel check, it shows the line"}})
        return 1
    finally:
        runner._loading = False
    try:
        act = find(name)
    except LookupError:
        names = ", ".join(item.name for item in actions()) or "none"
        send({"type": "error", "error": {"code": "no_such_action", "message": f"{entry.name} has no action called {name}.", "fix": f"use one of: {names}"}})
        return 1
    items: list[dict] = []

    def sink(payload: dict) -> dict:
        item = {"id": str(len(items) + 1), "kind": payload["kind"], "title": payload["title"]}
        items.append({**item, "path": payload["path"], "metadata": payload.get("metadata", {})})
        return item

    sink_var.set(sink)
    progress = 0
    try:
        def on_progress(fraction, label):
            nonlocal progress
            progress += 1
            send({"type": "progress", "fraction": fraction, "label": label})

        result = call(act, given, cancel=threading.Event(), report=on_progress, send=lambda event, body: send({"type": "event", "name": event, "body": body}))
        send({"type": "done", "result": result, "items": items, "progress_calls": progress})
        return 0
    except Problem as problem:
        send({"type": "error", "error": {"code": "problem", "message": problem.message, **({"hint": problem.hint} if problem.hint else {})}, "items": items})
    except BadInput as bad:
        from ox1audio.fields import Files

        controls = " ".join("--file PATH" if isinstance(param.field, Files) else f"--set {param.name}=VALUE" for param in act.params)
        send({"type": "error", "error": {"code": "bad_input", "message": str(bad), "fix": f"mixel run {name} {controls}".strip()}})
    except Cancelled as stop:
        send({"type": "error", "error": {"code": "cancelled", "message": stopped_message(stop.kept)}, "items": items})
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        frames = [frame for frame in traceback.extract_tb(exc.__traceback__) if Path(frame.filename).resolve().is_relative_to(entry.parent)]
        where = f"{Path(frames[-1].filename).name}:{frames[-1].lineno}" if frames else ""
        send({"type": "error", "error": {"code": "crashed", "message": f"{type(exc).__name__}: {exc}", "where": where, "fix": "fix the error at that line; the traceback is above"}, "items": items})
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
