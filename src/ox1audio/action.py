"""An action is a typed Python function that 0x1audio runs for the person.

The signature is the input. 0x1audio draws a form from it (or a page calls it
with ``ox.run``), checks the values, and runs the function in the background
with progress and a Stop button.
"""

from __future__ import annotations

import atexit
import contextvars
import inspect
import shutil
import tempfile
import threading
import time
import types
import typing
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ox1audio.fields import Export, Field, Files, Folder, Number, Optional, Text, Toggle, _missing
from ox1audio.runtime import sink_var

DOCS = "https://docs.0x1audio.com"
DEFAULT_TIMEOUT = 30 * 60

_registry: dict[str, "Action"] = {}


class Problem(Exception):
    """Something the person can fix. The message and hint are shown to them as written."""

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


class Cancelled(BaseException):
    """The person pressed Stop. ``ox.progress()`` raises it; let it propagate after you clean up.

    Like KeyboardInterrupt it is a BaseException, so ``except Exception`` never swallows Stop.
    """


class BadInput(Exception):
    """The input does not match the action's controls. Pages see code ``bad_input``."""


@dataclass
class Param:
    name: str
    field: Field
    kind: type
    default: object
    optional: bool

    @property
    def required(self) -> bool:
        return self.default is _missing and self.field.natural_default() is _missing and not self.optional


@dataclass
class Action:
    fn: Callable
    name: str
    title: str
    timeout: float
    params: list[Param] = field(default_factory=list)

    def spec(self) -> dict:
        properties = {}
        for param in self.params:
            prop = param.field.schema()
            prop["title"] = param.field.label or _humanize(param.name)
            default = param.default if param.default is not _missing else param.field.natural_default()
            if default is not _missing and default is not None:
                prop["default"] = _jsonable(default)
            if param.optional:
                prop = {"anyOf": [prop, {"type": "null"}], "title": prop["title"], "x-ox": prop.get("x-ox")}
                if param.default is None:
                    prop["default"] = None
            properties[param.name] = prop
        schema = {
            "type": "object",
            "properties": properties,
            "required": [param.name for param in self.params if param.required],
            "additionalProperties": False,
        }
        return {"name": self.name, "title": self.title, "input": schema, "timeout": self.timeout}

    def permissions(self) -> set[str]:
        return {"files" for param in self.params if isinstance(param.field, (Files, Folder))}


def action(title: str, *, timeout: float | None = None) -> Callable[[Callable], Callable]:
    """Make a function an action. ``title`` is what the person sees, like "Convert files"."""
    if callable(title):
        fn = title
        raise TypeError(_teach(
            f"@ox.action needs a title: {fn.__name__}() was decorated with @ox.action and no title.",
            f'@ox.action("{_humanize(fn.__name__)}")',
            "actions",
        ))
    if not isinstance(title, str) or not title.strip():
        raise TypeError(_teach("@ox.action(title): the title is the words on the button.", '@ox.action("Convert files")', "actions"))
    if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0):
        raise TypeError(_teach(f"@ox.action(timeout={timeout!r}) is not a number of seconds.", '@ox.action("Split song", timeout=3600)', "actions"))

    def decorate(fn: Callable) -> Callable:
        if inspect.isgeneratorfunction(fn) or inspect.isasyncgenfunction(fn):
            raise TypeError(_teach(
                f"{fn.__name__}() yields. Actions return what they made and call ox.progress() as they go.",
                "replace `yield ox.progress(f, label)` with `ox.progress(f, label)`, collect exports in a list, and `return` it",
                "actions#progress-and-stop",
            ))
        if inspect.iscoroutinefunction(fn):
            raise TypeError(_teach(f"{fn.__name__}() is async. Actions are plain functions; 0x1audio already runs them in the background.", f"def {fn.__name__}(...):", "actions"))
        name = fn.__name__
        existing = _registry.get(name)
        if existing is not None and existing.fn.__code__ is not fn.__code__:
            raise ValueError(_teach(f"There are two actions called {name}.", "give one of the functions another name", "actions"))
        _registry[name] = Action(fn=fn, name=name, title=title.strip(), timeout=float(timeout or DEFAULT_TIMEOUT), params=_params(fn))
        fn.__ox_action__ = name  # type: ignore[attr-defined]
        return fn

    return decorate


def actions() -> list[Action]:
    return list(_registry.values())


def clear() -> None:
    _registry.clear()


def find(fn_or_name: Callable | str) -> Action:
    name = fn_or_name if isinstance(fn_or_name, str) else getattr(fn_or_name, "__ox_action__", None)
    found = _registry.get(name) if isinstance(name, str) else None
    if found is None:
        label = fn_or_name if isinstance(fn_or_name, str) else getattr(fn_or_name, "__name__", repr(fn_or_name))
        raise LookupError(_teach(f"{label} is not an action.", f'decorate it with @ox.action("…")', "actions"))
    return found


# --- the signature is the input ---------------------------------------------------------------

def _number(whole: bool) -> Number:
    control = Number()
    control.whole = whole
    return control


_plain: dict[type, Callable[[], Field]] = {
    str: Text,
    int: lambda: _number(True),
    float: lambda: _number(False),
    bool: Toggle,
    Path: Folder,
}


def _params(fn: Callable) -> list[Param]:
    try:
        hints = typing.get_type_hints(fn)
    except Exception:
        hints = dict(getattr(fn, "__annotations__", {}))
    found = []
    for name, param in inspect.signature(fn).parameters.items():
        if name == "call" and param.annotation is inspect.Parameter.empty:
            raise TypeError(_teach(
                f"{fn.__name__}(call): actions take typed parameters, not a call object.",
                f"def {fn.__name__}(files: ox.Files(\"audio\"), format: ox.Choice(\"wav\", \"mp3\")):  and use ox.progress() for progress",
                "actions#controls",
            ))
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            raise TypeError(_teach(f"{fn.__name__}(): *args and **kwargs can't become controls.", "list each control as its own parameter", "actions#controls"))
        note = hints.get(name, param.annotation)
        default = _missing if param.default is inspect.Parameter.empty else param.default
        control, kind, optional = _control(fn.__name__, name, note)
        if default is not _missing and default is not None:
            _check_default(fn.__name__, name, control, default)
        if default is None:
            optional = True
        found.append(Param(name=name, field=control, kind=kind, default=default, optional=optional))
    return found


def _control(fn_name: str, name: str, note: object) -> tuple[Field, type, bool]:
    optional = False
    origin = typing.get_origin(note)
    if origin in (typing.Union, types.UnionType):
        args = [arg for arg in typing.get_args(note) if arg is not type(None)]
        if len(args) == 1 and len(typing.get_args(note)) == 2:
            note, optional = args[0], True
    if isinstance(note, Optional):
        note, optional = note.field, True
    if isinstance(note, type) and issubclass(note, Field):
        try:
            note = note()
        except TypeError:
            pass
    if isinstance(note, Field):
        return note, type(note), optional
    if isinstance(note, type) and note in _plain:
        return _plain[note](), note, optional
    if note is inspect.Parameter.empty:
        problem = f'{fn_name}(): the parameter "{name}" has no type, so 0x1audio can\'t draw a control for it.'
    else:
        shown = getattr(note, "__name__", None) or repr(note)
        problem = f'{fn_name}(): the parameter "{name}" is a {shown}, which is not a control.'
    raise TypeError(_teach(problem, f'annotate it with a control, like {name}: ox.Files("audio"), ox.Choice("a", "b"), ox.Slider(0, 1), or a plain str, int, float, bool', "actions#controls"))


def _check_default(fn_name: str, name: str, control: Field, default: object) -> None:
    try:
        _coerce(control, name, default, Path)
    except BadInput as error:
        raise TypeError(_teach(f"{fn_name}(): the default for {name} doesn't fit its control. {error}", f"change the default of {name}", "actions#controls")) from None


# --- running ---------------------------------------------------------------------------------


@dataclass
class _Running:
    id: int
    cancel: threading.Event
    report: Callable[[float | None, str], None]
    last_sent: float = 0.0
    last_label: str = ""
    coalesce: bool = True


_running: contextvars.ContextVar[_Running | None] = contextvars.ContextVar("ox_running", default=None)


def progress(fraction: float | None = None, label: str = "") -> None:
    """Say how far along the action is (0 to 1, or None when unknown) and what it's doing.

    If the person pressed Stop, this raises ``ox.Cancelled``. Call it often, including
    from inside library callbacks, so Stop is quick.
    """
    current = _running.get()
    if current is None:
        return
    if current.cancel.is_set():
        raise Cancelled()
    if fraction is not None:
        try:
            fraction = min(1.0, max(0.0, float(fraction)))
        except (TypeError, ValueError):
            raise TypeError(_teach(f"ox.progress({fraction!r}): the fraction is a number from 0 to 1.", "ox.progress(i / len(files), path.name)", "actions#progress-and-stop")) from None
        if fraction != fraction:
            fraction = None
    label = str(label or "")
    now = time.monotonic()
    if current.coalesce and label == current.last_label and fraction != 1.0 and now - current.last_sent < 0.05:
        return
    current.last_sent = now
    current.last_label = label
    current.report(fraction, label)


def bind(act: Action, given: object) -> dict:
    """Check the input against the action's controls and turn it into Python values."""
    if given is None:
        given = {}
    if not isinstance(given, dict):
        raise BadInput(f"The input to {act.name} is an object of control values.")
    known = {param.name for param in act.params}
    extra = [key for key in given if key not in known]
    if extra:
        raise BadInput(f"{act.name} has no control called {extra[0]}. Its controls are: {', '.join(sorted(known)) or 'none'}.")
    values = {}
    for param in act.params:
        if param.name in given and given[param.name] is not None:
            values[param.name] = _coerce(param.field, param.name, given[param.name], param.kind)
        elif param.name in given and param.optional:
            values[param.name] = None
        elif param.default is not _missing:
            values[param.name] = param.default
        elif param.field.natural_default() is not _missing:
            values[param.name] = param.field.natural_default()
        elif param.optional:
            values[param.name] = None
        else:
            raise BadInput(_missing_message(param))
    return values


def _missing_message(param: Param) -> str:
    if isinstance(param.field, Files):
        return "Add a MIDI file first." if param.field.accept == "midi" else "Add a file first."
    if isinstance(param.field, Folder):
        return "Choose a folder first."
    return f"{param.field.label or _humanize(param.name)} is needed."


def _coerce(control: Field, name: str, value: object, kind: type) -> object:
    label = control.label or _humanize(name)
    if isinstance(control, Files):
        items = value if isinstance(value, (list, tuple)) else [value]
        if not control.multiple and isinstance(value, (list, tuple)):
            if len(value) != 1:
                raise BadInput(f"{label} takes one file.")
        paths = []
        for item in items:
            if not isinstance(item, (str, Path)) or not str(item):
                raise BadInput(f"{label} is a list of file paths.")
            path = Path(item)
            if not path.is_file():
                raise BadInput(f"{path.name or label} is not there anymore. Choose it again.")
            paths.append(path)
        if not paths:
            raise BadInput(_missing_message(Param(name, control, kind, _missing, False)))
        return paths if control.multiple else paths[0]
    if isinstance(control, Folder):
        if not isinstance(value, (str, Path)) or not str(value):
            raise BadInput(f"{label} is a folder path.")
        path = Path(value)
        if not path.is_dir():
            raise BadInput(f"The folder {path.name or path} is not there anymore. Choose it again.")
        return path
    if isinstance(control, Toggle):
        if not isinstance(value, bool):
            raise BadInput(f"{label} is on or off (true or false).")
        return value
    if isinstance(control, Number):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
            raise BadInput(f"{label} must be a number{_bounds(control)}.")
        if control.min is not None and value < control.min or control.max is not None and value > control.max:
            raise BadInput(f"{label} must be a number{_bounds(control)}. It was {value:g}.")
        if kind is int or (control.integer and kind is not float):
            if float(value) != int(value):
                raise BadInput(f"{label} must be a whole number{_bounds(control)}.")
            return int(value)
        return float(value)
    choices = getattr(control, "options", None)
    if choices is not None:
        if getattr(control, "multiple", False):
            picked = value if isinstance(value, (list, tuple)) else [value]
            if not picked:
                raise BadInput(f"Choose at least one option for {label.lower()}.")
            for item in picked:
                if item not in choices:
                    raise BadInput(f"{label} can include {', '.join(choices)}. It had {item}.")
            return [option for option in choices if option in picked]
        if value not in choices:
            raise BadInput(f"{label} is one of {', '.join(choices)}.")
        return value
    if not isinstance(value, str):
        raise BadInput(f"{label} is text.")
    return value


def _bounds(control: Number) -> str:
    if control.min is not None and control.max is not None:
        return f" from {control.min:g} to {control.max:g}"
    if control.min is not None:
        return f" of at least {control.min:g}"
    if control.max is not None:
        return f" of at most {control.max:g}"
    return ""


def call(act: Action, given: object, *, ident: int = 0, cancel: threading.Event | None = None, report: Callable[[float | None, str], None] | None = None, coalesce: bool = True) -> object:
    """Run one action: bind the input, call the function, and turn what it returned into JSON."""
    values = bind(act, given)
    state = _Running(id=ident, cancel=cancel or threading.Event(), report=report or (lambda fraction, label: None), coalesce=coalesce)
    token = _running.set(state)
    try:
        returned = act.fn(**values)
        if state.cancel.is_set():
            raise Cancelled()
        return finish(returned, act.name)
    finally:
        _running.reset(token)


def finish(value: object, name: str = "") -> object:
    """Exports go to the Library and come back as items; the rest must be JSON."""
    if isinstance(value, Export):
        return {"items": [_export(value)]}
    if isinstance(value, (list, tuple)) and value and all(isinstance(item, Export) for item in value):
        return {"items": [_export(item) for item in value]}
    return _json(value, name, "the result")


def _json(value: object, name: str, where: str) -> object:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if value == value and value not in (float("inf"), float("-inf")) else None
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Export):
        return _export(value)
    if isinstance(value, (list, tuple)):
        return [_json(item, name, where) for item in value]
    if isinstance(value, dict):
        return {str(key): _json(item, name, f"{where}[{key!r}]") for key, item in value.items()}
    raise TypeError(_teach(
        f"{name}() returned {where} as a {type(value).__name__}, which can't be sent to the page.",
        "return None, a str, a dict or list of plain values, or ox.sound(path, title) exports",
        "actions#results",
    ))


def _export(item: Export) -> dict:
    from ox1audio.library import add

    stored = add(item.kind, item.path, item.title or item.path.stem, **item.metadata)
    record = dict(stored) if isinstance(stored, dict) else {}
    record.setdefault("kind", item.kind)
    record.setdefault("title", item.title or item.path.stem)
    record["path"] = str(item.path)
    return record


def test(fn: Callable | str, *, stop_at: float | None = None, **values: object) -> dict:
    """Run an action here, without 0x1audio, the way the desktop would.

    Returns ``{"result", "items", "progress"}``: what the page would get, the
    Library items it would add (``id, kind, title, path, metadata``), and every
    ``(fraction, label)`` it reported. ``stop_at=0.5`` presses Stop once progress
    reaches half way, so the action's next ``ox.progress`` raises ``ox.Cancelled``.
    """
    act = find(fn)
    items: list[dict] = []
    reported: list[tuple[float | None, str]] = []
    stop = threading.Event()

    def report(fraction: float | None, label: str) -> None:
        reported.append((fraction, label))
        if stop_at is not None and fraction is not None and fraction >= stop_at:
            stop.set()

    def sink(payload: dict) -> dict:
        item = {"id": str(len(items) + 1), "kind": payload["kind"], "title": payload["title"]}
        items.append({**item, "path": payload["path"], "metadata": payload.get("metadata", {})})
        return item

    token = sink_var.set(sink)
    try:
        result = call(act, _plainify(values), cancel=stop, report=report, coalesce=False)
    finally:
        sink_var.reset(token)
    return {"result": result, "items": items, "progress": reported}


def _plainify(values: dict) -> dict:
    def plain(value: object) -> object:
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, (list, tuple)):
            return [plain(item) for item in value]
        return value

    return {key: plain(value) for key, value in values.items()}


_temps: list[Path] = []


def temp() -> Path:
    """A new, empty folder for files the action makes. It is removed when the app closes,
    after 0x1audio has copied returned sounds into the Library."""
    folder = Path(tempfile.mkdtemp(prefix="ox1-"))
    _temps.append(folder)
    return folder


@atexit.register
def _remove_temps() -> None:
    for folder in _temps:
        shutil.rmtree(folder, ignore_errors=True)


# --- words -----------------------------------------------------------------------------------


def _teach(problem: str, fix: str, page: str) -> str:
    return f"{problem}\nfix:  {fix}\ndocs: {DOCS}/{page}"


def _humanize(name: str) -> str:
    words = name.replace("_", " ").replace("-", " ").strip().split()
    text = " ".join(word if word.isupper() and len(word) > 1 else word.lower() for word in words)
    return text[:1].upper() + text[1:] if text else name


def _jsonable(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
