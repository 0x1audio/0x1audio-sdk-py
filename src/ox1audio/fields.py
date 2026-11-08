"""Controls a screen declares, and the files a screen hands back."""

from __future__ import annotations

from pathlib import Path


class Field:
    kind = ""

    def spec(self) -> dict:
        return {"kind": self.kind}


class Files(Field):
    """A drop target. The desktop hands the function a list of paths."""

    kind = "files"

    def __init__(self, accept: str = "audio") -> None:
        self.accept = accept

    def spec(self) -> dict:
        return {"kind": self.kind, "accept": self.accept}


class Choice(Field):
    kind = "choice"

    def __init__(self, *options: str) -> None:
        self.options = [str(option) for option in options]

    def spec(self) -> dict:
        return {"kind": self.kind, "options": self.options}


class Text(Field):
    kind = "text"

    def __init__(self, placeholder: str = "") -> None:
        self.placeholder = placeholder

    def spec(self) -> dict:
        return {"kind": self.kind, "placeholder": self.placeholder}


class Number(Field):
    kind = "number"

    def __init__(self, min: float | None = None, max: float | None = None, step: float | None = None) -> None:
        self.min = min
        self.max = max
        self.step = step

    def spec(self) -> dict:
        spec: dict = {"kind": self.kind}
        if self.min is not None:
            spec["min"] = self.min
        if self.max is not None:
            spec["max"] = self.max
        if self.step is not None:
            spec["step"] = self.step
        return spec


class Toggle(Field):
    kind = "toggle"

    def __init__(self, default: bool = False) -> None:
        self.default = default

    def spec(self) -> dict:
        return {"kind": self.kind, "default": self.default}


class Slider(Field):
    kind = "slider"

    def __init__(self, min: float = 0, max: float = 1, step: float = 0.01) -> None:
        self.min = min
        self.max = max
        self.step = step

    def spec(self) -> dict:
        return {"kind": self.kind, "min": self.min, "max": self.max, "step": self.step}


class Progress:
    def __init__(self, fraction: float, label: str = "") -> None:
        self.fraction = fraction
        self.label = label


def progress(fraction: float, label: str = "") -> Progress:
    return Progress(fraction, label)


class Export:
    def __init__(self, kind: str, path: str | Path, title: str, **metadata: object) -> None:
        self.kind = kind
        self.path = path
        self.title = title
        self.metadata = metadata


def sound(path: str | Path, title: str, **metadata: object) -> Export:
    return Export("sound", path, title, **metadata)


def midi(path: str | Path, title: str, **metadata: object) -> Export:
    return Export("midi", path, title, **metadata)


def file(path: str | Path, title: str, **metadata: object) -> Export:
    return Export("other", path, title, **metadata)
