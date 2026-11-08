"""mixel dev: open this folder in the running Mixel desktop, reload it on save, and stream its log.

The desktop listens on 127.0.0.1 only while developer mode is on, and writes the port and a
per-session token to ``<Mixel's data folder>/dev.json`` (readable only by you). Every request
carries that token.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

from ox1audio.cli import check, out
from ox1audio.cli.out import FAILED, NETWORK, OK, Stop

WATCHED = {".py", ".json", ".toml", ".html", ".js", ".css", ".svg", ".png"}
SKIPPED = {".venv", ".git", "node_modules", "__pycache__", "tests", ".mixel"}


def desktop_folder() -> Path:
    """Where the Mixel desktop keeps its data (its Electron userData folder)."""
    if os.environ.get("MIXEL_DESKTOP_DIR"):
        return Path(os.environ["MIXEL_DESKTOP_DIR"])
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "0x1audio"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")) / "0x1audio"
    return Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config") / "0x1audio"


class Desktop:
    """The dev socket of a running Mixel desktop."""

    def __init__(self) -> None:
        file = desktop_folder() / "dev.json"
        settings = desktop_folder() / "settings.json"
        unavailable = Stop(
            "Mixel isn't running with developer mode on.",
            fix=f'open Mixel and turn on Settings › Developer mode (or add "developerMode": true to {settings} and reopen Mixel)',
            doc="start#mixel-dev", code=NETWORK, error="desktop_unavailable",
        )
        try:
            info = json.loads(file.read_text())
            self.base = f"http://127.0.0.1:{int(info['port'])}"
            self.token = str(info["token"])
        except (OSError, ValueError, KeyError, TypeError):
            raise unavailable from None
        try:
            self.status = self.request("GET", "/v1/status")
        except Stop:
            raise unavailable from None

    def request(self, method: str, path: str, body: dict | None = None, timeout: float = 30) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method, headers={"authorization": f"Bearer {self.token}", "content-type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            try:
                problem = json.loads(error.read()).get("error", {})
            except ValueError:
                problem = {}
            raise Stop(problem.get("message") or f"Mixel answered {error.code}.", fix=problem.get("fix", ""), code=FAILED if error.code < 500 else NETWORK, error=problem.get("code", "desktop_error")) from None
        except (urllib.error.URLError, OSError, ValueError):
            raise Stop("Lost the connection to Mixel.", fix="open Mixel, then run mixel dev again", code=NETWORK, error="desktop_unavailable") from None

    def stream(self, path: str):
        request = urllib.request.Request(self.base + path, headers={"authorization": f"Bearer {self.token}"})
        with urllib.request.urlopen(request, timeout=3600 * 24) as response:
            for line in response:
                try:
                    yield json.loads(line)
                except ValueError:
                    continue


def command(args: list[str]) -> int:
    unknown = [arg for arg in args if arg.startswith("--")]
    if unknown:
        raise Stop(f"mixel dev has no option {unknown[0]}.", fix="mixel dev [folder]")
    folder = Path(args[0]).resolve() if args else Path.cwd()
    report = check.run(folder)
    if report.errors:
        check.show(report)
        print("\nmixel dev opens the app once mixel check has no errors.")
        return FAILED
    desktop = Desktop()
    opened = desktop.request("POST", "/v1/apps", {"dir": str(folder)}, timeout=60)
    ident = opened["id"]
    print(f"Opened {opened.get('displayName', folder.name)} {opened.get('version', '')} in Mixel, in development.".replace("  ", " "))
    print("Watching for changes. Press Ctrl-C to stop.\n")
    closed = threading.Event()
    threading.Thread(target=_follow, args=(desktop, ident, closed), daemon=True).start()
    seen = _snapshot(folder)
    try:
        while not closed.wait(0.5):
            now = _snapshot(folder)
            changed = sorted(name for name in now.keys() | seen.keys() if now.get(name) != seen.get(name))
            if not changed:
                continue
            seen = now
            report = check.run(folder)
            if report.errors:
                print(f"{changed[0]} changed, but mixel check found errors. Not reloaded:\n")
                out.findings(report.errors)
                continue
            desktop.request("POST", f"/v1/apps/{ident}/reload", {"changed": changed[:20]})
            print(f"Reloaded: {', '.join(changed[:3])}{' and more' if len(changed) > 3 else ''} changed.")
    except KeyboardInterrupt:
        try:
            desktop.request("DELETE", f"/v1/apps/{ident}", timeout=5)
        except Stop:
            pass
        print("\nClosed it in Mixel.")
        return OK
    print("The window was closed in Mixel.")
    return OK


def _follow(desktop: Desktop, ident: str, closed: threading.Event) -> None:
    try:
        for message in desktop.stream(f"/v1/apps/{ident}/log"):
            kind = message.get("type")
            if kind == "closed":
                break
            text = str(message.get("text", "")).rstrip()
            if not text:
                continue
            prefix = {"log": "log  ", "error": out.color("error", "error"), "info": "     "}.get(kind, "     ")
            for line in text.splitlines():
                print(f"{prefix}  {line}", flush=True)
    except (OSError, urllib.error.URLError):
        print("Lost the connection to Mixel.", file=sys.stderr)
    closed.set()


def _snapshot(folder: Path) -> dict[str, float]:
    found: dict[str, float] = {}
    for root, dirs, files in os.walk(folder):
        dirs[:] = [name for name in dirs if name not in SKIPPED and not name.startswith(".")]
        for name in files:
            if Path(name).suffix in WATCHED:
                path = Path(root) / name
                try:
                    found[str(path.relative_to(folder))] = path.stat().st_mtime
                except OSError:
                    continue
    return found

