"""Add a file to the Library. The desktop copies it and keeps the provenance.

Most actions just return ``ox.sound(path, title)``. Call ``ox.library.add``
only when a file must reach the Library before the action ends.
"""

from __future__ import annotations

from pathlib import Path

from ox1audio.runtime import link_var, sink_var


def add(kind: str, path: str | Path, title: str, **metadata: object) -> object:
    """Copy ``path`` into the Library and return the item the desktop stored."""
    if kind not in {"sound", "midi", "other"}:
        raise ValueError("A Library item is a sound, a midi, or an other file.")
    source = Path(path)
    if not source.is_file():
        raise ValueError(f"{source.name} is not there anymore.")
    payload = {
        "op": "add",
        "kind": kind,
        "path": str(source),
        "title": title.strip() or source.stem,
        "metadata": {key: value for key, value in metadata.items() if value is not None},
    }
    sink = sink_var.get()
    if sink is not None:
        return sink(payload)
    link = link_var.get()
    if link is None or not hasattr(link, "library"):
        raise RuntimeError(
            "The Library is only there while Mixel runs the app.\n"
            "fix:  in a test, run the action with ox.test(action, ...), which records Library items.\n"
            "docs: https://docs.0x1audio.com/actions#results"
        )
    return link.library(payload)
