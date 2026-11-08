"""Files that belong to this app.

The desktop keeps them next to the installed app, under data/<author id>/<repository id>.
Updating or removing the app leaves this folder in place until the user deletes it.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def root() -> Path:
    """The folder for this app's data. It is created the first time it is used."""
    value = os.environ.get("OX1_DATA", "").strip()
    if not value:
        raise RuntimeError("This app has no data folder.")
    folder = Path(value)
    folder.mkdir(parents=True, exist_ok=True)
    return folder.resolve()


def read(path: str) -> bytes:
    file = _resolve(path)
    if not file.is_file():
        raise FileNotFoundError(f"{path} is not in this app's data.")
    return file.read_bytes()


def read_text(path: str) -> str:
    return read(path).decode()


def write(path: str, body: bytes | str) -> None:
    if isinstance(body, str):
        payload = body.encode()
    elif isinstance(body, bytes):
        payload = body
    else:
        raise TypeError("Data must be text or bytes.")
    parts = _parts(path)
    folder = root().joinpath(*parts[:-1])
    folder.mkdir(parents=True, exist_ok=True)
    _resolve(path).write_bytes(payload)


def remove(path: str) -> None:
    file = _resolve(path)
    if not file.exists() and not file.is_symlink():
        return
    if file.is_dir() and not file.is_symlink():
        shutil.rmtree(file)
        return
    file.unlink()


def list(path: str = "") -> list[str]:
    folder = root() if path == "" else _resolve(path)
    if not folder.exists():
        return []
    if not folder.is_dir():
        raise NotADirectoryError(f"{path} is a file.")
    return sorted(entry.name for entry in folder.iterdir())


def _resolve(path: str) -> Path:
    base = root()
    current = base
    parts = _parts(path)
    for part in parts:
        current = current / part
        if current.is_symlink():
            current = current.resolve()
            if not _inside(base, current):
                raise ValueError("That file is outside this app's data.")
    if current.exists():
        resolved = current.resolve()
        if not _inside(base, resolved):
            raise ValueError("That file is outside this app's data.")
        return resolved
    parent = current.parent.resolve() if current.parent.exists() else current.parent
    final = parent / current.name
    if not _inside(base, final):
        raise ValueError("That file is outside this app's data.")
    return final


def _parts(path: str) -> list[str]:
    text = path.replace("\\", "/")
    if text.startswith("/") or (len(text) >= 2 and text[1] == ":"):
        raise ValueError("That file is outside this app's data.")
    parts = [part for part in text.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." or "\0" in part for part in parts):
        raise ValueError("That file is outside this app's data.")
    return parts


def _inside(base: Path, target: Path) -> bool:
    try:
        target.relative_to(base)
    except ValueError:
        return False
    return True
