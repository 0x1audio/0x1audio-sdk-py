"""A screen is a function. Its annotations are the controls, and yielding reports progress or exports a file."""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Callable
from typing import Any

from ox1audio.fields import Export, Field, Progress
from ox1audio.library import add
from ox1audio.runtime import sink_var

SCREENS: list[Callable] = []


def screen(title: str) -> Callable:
    def decorate(fn: Callable) -> Callable:
        fn.__ox_title__ = title  # type: ignore[attr-defined]
        if fn not in SCREENS:
            SCREENS.append(fn)
        return fn

    return decorate


def screens() -> list[Callable]:
    return list(SCREENS)


def clear() -> None:
    SCREENS.clear()


def fields_of(fn: Callable) -> list[dict]:
    signature = inspect.signature(fn)
    notes = getattr(fn, "__annotations__", {})
    found = []
    for name, param in signature.parameters.items():
        if name in {"call", "self"}:
            continue
        note = notes.get(name, param.annotation)
        if note is inspect.Parameter.empty:
            continue
        field = note() if isinstance(note, type) and issubclass(note, Field) else note
        if not isinstance(field, Field):
            continue
        found.append({"name": name, **field.spec()})
    return found


def permissions_of(fn: Callable) -> list[str]:
    needed: set[str] = set()
    for field in fields_of(fn):
        if field["kind"] == "files":
            needed.add("files")
    try:
        source = textwrap.dedent(inspect.getsource(fn))
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            attr = func.attr if isinstance(func, ast.Attribute) else ""
            name = func.id if isinstance(func, ast.Name) else ""
            if attr in {"sound", "midi", "file"} or name in {"sound", "midi", "file"}:
                needed.add("library")
    order = ["files", "library", "network", "data"]
    return [item for item in order if item in needed]


def describe() -> dict:
    described = []
    needed: set[str] = set()
    for fn in SCREENS:
        described.append({"name": fn.__name__, "title": getattr(fn, "__ox_title__", fn.__name__), "fields": fields_of(fn)})
        needed.update(permissions_of(fn))
    order = ["files", "library", "network", "data"]
    return {"screens": described, "permissions": [item for item in order if item in needed]}


def run_screen(fn: Callable, body: dict, progress: Callable[[float, str], None]) -> object:
    kwargs = {}
    for field in fields_of(fn):
        if field["name"] in body:
            kwargs[field["name"]] = body[field["name"]]
    value = fn(**kwargs)
    if not inspect.isgenerator(value):
        return _finish(value, progress)
    items: list[object] = []
    for yielded in value:
        item = _step(yielded, progress)
        if item is not None:
            items.append(item)
    return {"items": items}


def _finish(value: object, progress: Callable[[float, str], None]) -> object:
    item = _step(value, progress)
    if isinstance(value, Export):
        return {"items": [item]}
    return value


def _step(value: object, progress: Callable[[float, str], None]) -> object | None:
    if isinstance(value, Progress):
        progress(value.fraction, value.label)
        return None
    if isinstance(value, Export):
        return add(value.kind, value.path, value.title, **value.metadata)
    return None


def exercise(fn: Callable, **kwargs: object) -> dict:
    """Run a screen function in-process and record what it exported."""
    recorded: list[dict] = []

    def sink(payload: dict) -> dict:
        item = {"id": str(len(recorded) + 1), "kind": payload["kind"], "title": payload["title"], "path": payload["path"]}
        recorded.append(item)
        return item

    token = sink_var.set(sink)
    try:
        result = run_screen(fn, kwargs, lambda fraction, label: None)
    finally:
        sink_var.reset(token)
    return {"result": result, "items": recorded}


def bind(body: Any) -> dict:
    return body if isinstance(body, dict) else {}
