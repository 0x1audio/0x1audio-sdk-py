"""Controls an action declares, and the files an action hands back.

A control is a parameter annotation. Mixel draws it, checks the value, and
passes the action a plain Python value: Files become ``list[Path]``, a Folder
becomes a ``Path``, a Range a ``(low, high)`` tuple, the rest are ``str``, ``int``,
``float`` or ``bool``.
"""

from __future__ import annotations

from pathlib import Path

from ox1audio.runtime import made_var

_accepts = ("audio", "midi", "any")


class Field:
    """A control. Its spec is part of the action's JSON Schema."""

    control = ""

    def __init__(self, label: str | None = None) -> None:
        self.label = label

    def schema(self) -> dict:
        raise NotImplementedError

    def natural_default(self) -> object:
        """The value the form starts with when the Python parameter has no default."""
        return _missing

    def __or__(self, other: object) -> "Optional":
        # `folder: ox.Folder() | None = None` reads like any other optional parameter.
        if other is None:
            return Optional(self)
        return NotImplemented

    __ror__ = __or__

    def _ox(self, **extra: object) -> dict:
        spec: dict = {"control": self.control}
        if self.label:
            spec["label"] = self.label
        spec.update({key: value for key, value in extra.items() if value is not None})
        return spec


class Optional:
    """A control that may be left empty: ``ox.Folder() | None``. The action gets ``None`` then."""

    def __init__(self, field: Field) -> None:
        self.field = field


class Files(Field):
    """Files the person drops or picks. The action gets ``list[Path]``, or one ``Path`` with ``multiple=False``."""

    control = "files"

    def __init__(self, accept: str = "audio", multiple: bool = True, label: str | None = None) -> None:
        super().__init__(label)
        if accept not in _accepts:
            raise ValueError(
                f'ox.Files(accept="{accept}") is not a kind of file.\n'
                'fix:  use accept="audio", "midi" or "any".\n'
                "docs: https://docs.0x1audio.com/actions#controls"
            )
        self.accept = accept
        self.multiple = bool(multiple)

    def schema(self) -> dict:
        ox = self._ox(accept=self.accept, multiple=self.multiple)
        if self.multiple:
            return {"type": "array", "items": {"type": "string"}, "minItems": 1, "x-ox": ox}
        return {"type": "string", "minLength": 1, "x-ox": ox}


class Folder(Field):
    """A folder the person picks. The action gets a ``Path``."""

    control = "folder"

    def schema(self) -> dict:
        return {"type": "string", "minLength": 1, "x-ox": self._ox()}


class Choice(Field):
    """One of a few options, as a ``str``; with ``multiple=True``, some of them, as a ``list[str]``.

    The first option is the default unless the parameter has one.
    """

    control = "choice"

    def __init__(self, *options: str, multiple: bool = False, label: str | None = None) -> None:
        super().__init__(label)
        if not options:
            raise ValueError(
                "ox.Choice() needs at least one option.\n"
                'fix:  list the options, like ox.Choice("wav", "flac", "mp3").\n'
                "docs: https://docs.0x1audio.com/actions#controls"
            )
        self.options = [str(option) for option in options]
        self.multiple = bool(multiple)

    def schema(self) -> dict:
        if self.multiple:
            return {"type": "array", "items": {"type": "string", "enum": list(self.options)}, "minItems": 1, "uniqueItems": True, "x-ox": self._ox(multiple=True)}
        return {"type": "string", "enum": list(self.options), "x-ox": self._ox()}

    def natural_default(self) -> object:
        return [self.options[0]] if self.multiple else self.options[0]


class Text(Field):
    """A line of text, as a ``str``."""

    control = "text"

    def __init__(self, placeholder: str = "", label: str | None = None) -> None:
        super().__init__(label)
        self.placeholder = placeholder

    def schema(self) -> dict:
        return {"type": "string", "maxLength": 10000, "x-ox": self._ox(placeholder=self.placeholder or None)}

    def natural_default(self) -> object:
        return ""


class Number(Field):
    """A number typed in a box. Whole numbers come back as ``int`` unless a bound or the step is a fraction.

    ``unit`` is shown after the value, like ``"dB"``, ``"Hz"`` or ``"%"``.
    """

    control = "number"

    def __init__(self, min: float | None = None, max: float | None = None, step: float | None = None, label: str | None = None, *, unit: str | None = None) -> None:
        super().__init__(label)
        _check_range(f"ox.{type(self).__name__}", min, max, step)
        self.min = min
        self.max = max
        self.step = step
        self.unit = _check_unit(f"ox.{type(self).__name__}", unit)
        self.whole: bool | None = None

    @property
    def integer(self) -> bool:
        """Whole numbers when every bound and the step that is given is an int."""
        if self.whole is not None:
            return self.whole
        given = [value for value in (self.min, self.max, self.step) if value is not None]
        return bool(given) and all(isinstance(value, int) for value in given)

    def schema(self) -> dict:
        spec: dict = {"type": "integer" if self.integer else "number"}
        if self.min is not None:
            spec["minimum"] = self.min
        if self.max is not None:
            spec["maximum"] = self.max
        spec["x-ox"] = self._ox(step=self.step, unit=self.unit)
        return spec


class Slider(Number):
    """A number on a slider. Starts at ``min`` unless the parameter has a default.

    Whole numbers (an ``int``) when min, max and step are all ints: ``ox.Slider(1, 8, step=1)``.
    """

    control = "slider"

    def __init__(self, min: float = 0, max: float = 1, step: float = 0.01, label: str | None = None, *, unit: str | None = None) -> None:
        super().__init__(min, max, step, label, unit=unit)

    def natural_default(self) -> object:
        return self.min


class Range(Field):
    """A start and an end on one slider, like a band of frequencies or a part of a song.

    The action gets a ``(low, high)`` tuple, ints when min, max and step are all ints.
    It starts at the whole range unless the parameter has a default, like ``= (200, 4000)``.
    """

    control = "slider"

    def __init__(self, min: float = 0, max: float = 1, step: float = 0.01, label: str | None = None, *, unit: str | None = None) -> None:
        super().__init__(label)
        _check_range("ox.Range", min, max, step)
        if min is None or max is None:
            raise TypeError("ox.Range(): min and max are numbers.\nfix:  write it like ox.Range(20, 20000, step=1, unit=\"Hz\").\ndocs: https://docs.0x1audio.com/actions#controls")
        self.min = min
        self.max = max
        self.step = step
        self.unit = _check_unit("ox.Range", unit)

    @property
    def integer(self) -> bool:
        return all(isinstance(value, int) for value in (self.min, self.max, self.step))

    def schema(self) -> dict:
        items = {"type": "integer" if self.integer else "number", "minimum": self.min, "maximum": self.max}
        return {"type": "array", "items": items, "minItems": 2, "maxItems": 2, "x-ox": self._ox(step=self.step, unit=self.unit)}

    def natural_default(self) -> object:
        return (self.min, self.max)


class Toggle(Field):
    """On or off, as a ``bool``. Off unless the parameter defaults to ``True``."""

    control = "toggle"

    def schema(self) -> dict:
        return {"type": "boolean", "x-ox": self._ox()}

    def natural_default(self) -> object:
        return False


class _Missing:
    def __repr__(self) -> str:
        return "missing"


_missing = _Missing()


def _check_range(name: str, low: float | None, high: float | None, step: float | None) -> None:
    for value in (low, high, step):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise TypeError(f"{name}(): min, max and step are numbers.\nfix:  write it like {name}(0, 12, step=0.5).\ndocs: https://docs.0x1audio.com/actions#controls")
    if low is not None and high is not None and low > high:
        raise ValueError(f"{name}({low}, {high}): min is larger than max.\nfix:  swap them.\ndocs: https://docs.0x1audio.com/actions#controls")
    if step is not None and step <= 0:
        raise ValueError(f"{name}(step={step}): the step is above zero.\nfix:  use a step like 1 or 0.5.\ndocs: https://docs.0x1audio.com/actions#controls")


def _check_unit(name: str, unit: object) -> str | None:
    if unit is None:
        return None
    if not isinstance(unit, str) or not unit.strip() or len(unit) > 12 or "\n" in unit:
        raise TypeError(f"{name}(unit={unit!r}): the unit is a short word shown after the value.\nfix:  write it like unit=\"dB\", \"Hz\", \"%\" or \"s\".\ndocs: https://docs.0x1audio.com/actions#controls")
    return unit.strip()


class Export:
    """A file the action made, for the Library. Return it (or a list of them) from the action."""

    def __init__(self, kind: str, path: str | Path, title: str, **metadata: object) -> None:
        self.kind = kind
        self.path = Path(path)
        self.title = title
        self.metadata = metadata
        made = made_var.get()
        if made is not None:
            made.append(self)

    def __repr__(self) -> str:
        return f"ox.{'file' if self.kind == 'other' else self.kind}({str(self.path)!r}, title={self.title!r})"


def sound(path: str | Path, title: str = "", **metadata: object) -> Export:
    """A sound for the Library: ``bpm``, ``key``, ``duration`` and the like go in ``metadata``."""
    return Export("sound", path, title, **metadata)


def midi(path: str | Path, title: str = "", **metadata: object) -> Export:
    return Export("midi", path, title, **metadata)


def file(path: str | Path, title: str = "", **metadata: object) -> Export:
    return Export("other", path, title, **metadata)
