"""mixel doctor: is this computer ready to build, test and publish a Mixel app."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from ox1audio import __version__
from ox1audio.cli import out
from ox1audio.cli.out import FAILED, OK, Stop


def command(args: list[str]) -> int:
    rows: list[dict] = []

    def row(name: str, ok: bool, detail: str, fix: str = "", needed: bool = True) -> None:
        rows.append({"name": name, "ok": ok, "detail": detail, **({"fix": fix} if fix and not ok else {}), "needed": needed})

    row("mixel", True, f"{__version__} on Python {sys.version.split()[0]}")
    row("uv", bool(shutil.which("uv")), shutil.which("uv") or "not found", "install uv: https://docs.astral.sh/uv/getting-started/installation/", needed=False)
    row("git", bool(shutil.which("git")), shutil.which("git") or "not found", "install git (needed to publish)", needed=False)
    page = (Path.cwd() / "package.json").is_file()
    if page:
        row("node", bool(shutil.which("node")), shutil.which("node") or "not found", "install Node 20 or newer to build the page")
    from ox1audio.cli.dev import Desktop

    try:
        desktop = Desktop()
        row("Mixel", True, f"running, developer mode on (desktop SDK {desktop.status.get('sdk', '?')})")
    except Stop as error:
        row("Mixel", False, error.message, error.fix, needed=False)
    from ox1audio.cli.registry import api, token

    row("sign-in", token() is not None, f"signed in to {api()}" if token() else "not signed in", "mixel login (needed to publish)", needed=False)
    if "--json" in args:
        out.emit({"ok": all(item["ok"] for item in rows if item["needed"]), "checks": rows})
    else:
        width = max(len(item["name"]) for item in rows)
        for item in rows:
            mark = "ok  " if item["ok"] else out.color("no  ", "warn")
            print(f"{mark}  {item['name'].ljust(width)}  {item['detail']}")
            if item.get("fix"):
                print(f"      {' ' * width}  fix:  {item['fix']}")
    return OK if all(item["ok"] for item in rows if item["needed"]) else FAILED
