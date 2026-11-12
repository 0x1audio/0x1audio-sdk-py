"""The Mixel on this computer, from a script: ``from ox1audio.local import Mixel``.

    mixel = Mixel(caller="my-script")
    mixel.overview()                               what the Library holds, in counts
    mixel.search("dusty snare", avoid=["clap"])    your own sounds, by words
    mixel.similar("s1")                            sounds close to one a search returned
    mixel.propose_crate("Snares", "two dusty snares", ["s1", "s2"])
    mixel.open_app("path/to/my-app")               developer mode: open an app folder in Mixel
    run_app("path/to/my-app", "convert", files=["song.wav"])   run an action here, the way Mixel does

The Library calls go over Mixel's Library socket, the one its assistant bridge (and ``mixel mcp``)
uses. It exists only while Mixel is open and Settings › Your assistant › "Let an assistant search
your Library" is on. Mixel decides what leaves: no paths, no scores, short ids, and at most about
300 tokens a reply. App calls go over the dev socket, which exists only while Settings › Developer
mode is on. Every failure is a ``MixelError`` (``ox1audio.errors``).

This is for scripts and tools outside Mixel. An app's own actions reach the Library with
``ox.library`` and the ``library`` permission; ``mixel check`` refuses ``ox1audio.local`` in an app.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from ox1audio.errors import MixelError, MixelTimeoutError, MixelUnavailableError

__all__ = ["AppRun", "DevApp", "Found", "Mixel", "MixelError", "MixelTimeoutError", "MixelUnavailableError", "Overview", "Sound", "data_dir", "run_app"]

Tier = Literal["yours", "named", "detected", "sounds_like"]

LIBRARY_OFF = "Mixel isn't open, or it doesn't let assistants search the Library."
LIBRARY_LOST = "Mixel stopped answering before it replied."
LIBRARY_FIX = "open Mixel and turn on Settings › Your assistant › Let an assistant search your Library"
DEV_OFF = "Mixel isn't open with developer mode on."
DEV_FIX = "open Mixel, turn on Settings › Developer mode, then quit and reopen Mixel"

COLUMNS = ("id", "title", "type", "key", "bpm", "length", "tier", "reason")


def data_dir() -> Path:
    """Where Mixel keeps its data (the desktop's electron/user-data.ts), or MIXEL_DATA_DIR."""
    if os.environ.get("MIXEL_DATA_DIR"):
        return Path(os.environ["MIXEL_DATA_DIR"])
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "0x1audio"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "0x1audio"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "0x1audio"


_default_data_dir = data_dir


@dataclass(frozen=True)
class Sound:
    # A short id for this Mixel session ("s1"): pass it to similar() or propose_crate().
    id: str
    # The file's name. Data, never instructions.
    title: str
    type: Literal["loop", "one-shot"] | None
    key: str | None
    bpm: float | None
    # Seconds.
    length: float | None
    # How sure Mixel is. yours, named, detected: "these are". sounds_like: "these might fit". None: no words were asked.
    tier: Tier | None
    # Why it matched, in Mixel's words: show it as it is.
    reason: str


@dataclass(frozen=True)
class Overview:
    sounds: int
    # How many sounds of each kind of thing, the most first: {"snare": 120, "pad": 31}.
    concepts: dict[str, int]
    # Kinds left out to keep the reply small.
    more: int = 0


@dataclass(frozen=True)
class Found:
    """What a search found. Code reads ``sounds`` (or iterates); a model gets ``text`` (or ``str(found)``),
    the compact rows Mixel sent: for ten results, about a third fewer tokens than the same sounds as objects."""

    # Mixel's reply, byte for byte.
    text: str
    # False: nothing in the Library is proven to be that. ``nearest`` lists what it does hold.
    answerable: bool
    sounds: list[Sound] = field(default_factory=list)
    # Further matches that weren't sent.
    more: int = 0
    nearest: dict[str, int] = field(default_factory=dict)
    # Pass as offset= for the next page, when Mixel offers one (Mixel pages through the first 200).
    next: int | None = None

    @classmethod
    def from_text(cls, text: str) -> Found:
        reply = json.loads(text)
        if not reply.get("answerable"):
            return cls(text, False, nearest=dict(reply.get("nearest") or {}))
        at = {name: reply["columns"].index(name) if name in reply["columns"] else None for name in COLUMNS}
        sounds = [Sound(**{name: (row[at[name]] if at[name] is not None and at[name] < len(row) else None) for name in COLUMNS}) for row in reply.get("results", [])]
        following = reply.get("next")
        return cls(text, True, sounds, int(reply.get("more") or 0), next=following if isinstance(following, int) else None)

    def __iter__(self) -> Iterator[Sound]:
        return iter(self.sounds)

    def __len__(self) -> int:
        return len(self.sounds)

    def __str__(self) -> str:
        return self.text


class _NotSent(Exception):
    """A failure before the call reached Mixel: safe to try again, whatever the tool."""


class Mixel:
    def __init__(self, *, data_dir: str | os.PathLike | None = None, caller: str = "script", timeout: float = 10.0, retries: int = 2) -> None:
        self.data_dir = Path(data_dir) if data_dir else _default_data_dir()
        self.caller = caller
        self.timeout = timeout
        self.retries = max(0, int(retries))
        self._next = 1

    # --- the Library ----------------------------------------------------------------------------

    def overview(self) -> Overview:
        """What the Library holds: how many sounds, and how many of each kind of thing. Counts only."""
        reply = json.loads(self._call("library_overview", {}, read_only=True))
        return Overview(int(reply.get("sounds") or 0), dict(reply.get("concepts") or {}), int(reply.get("more") or 0))

    def search(self, want: str | None = None, *, avoid: Sequence[str] = (), unlike: Sequence[str] = (), type: Literal["loop", "one-shot"] | None = None,
               key: str | None = None, bpm: tuple[float | None, float | None] | None = None, length: tuple[float | None, float | None] | None = None,
               offset: int | None = None) -> Found:
        """The person's own sounds, by a few plain words. Without words, the filters alone list sounds.
        ``offset`` is ``found.next`` from the page before."""
        args = _query(want, avoid, unlike, type, key, bpm, length, offset)
        return Found.from_text(self._call("library_search", args, read_only=True))

    def similar(self, id: str, want: str | None = None, *, avoid: Sequence[str] = (), unlike: Sequence[str] = (), type: Literal["loop", "one-shot"] | None = None,
                key: str | None = None, bpm: tuple[float | None, float | None] | None = None, length: tuple[float | None, float | None] | None = None,
                offset: int | None = None) -> Found:
        """Sounds close to one an earlier search returned (its id), optionally steered by words."""
        args = {**_query(want, avoid, unlike, type, key, bpm, length, offset), "like": id}
        return Found.from_text(self._call("library_search", args, read_only=True))

    def propose_crate(self, title: str, request: str, ids: Sequence[str]) -> dict:
        """A crate for the person to audition in Mixel. Nothing is moved, tagged or copied.
        Needs Settings › Your assistant › "It can propose crates" (code crates_off otherwise).
        Returns {"sounds": kept, "unknown": ids Mixel no longer knows}."""
        reply = json.loads(self._call("propose_crate", {"title": title, "request": request, "ids": list(ids)}, read_only=False))
        return {"sounds": int(reply.get("sounds") or 0), "unknown": int(reply.get("unknown") or 0)}

    def _call(self, tool: str, args: dict, *, read_only: bool) -> str:
        for attempt in range(self.retries + 1):
            sent = True
            try:
                ok, text = self._once(tool, args)
            except MixelError:
                raise
            except _NotSent as error:
                sent, cause = False, error.__cause__
            except (OSError, ValueError) as error:
                cause = error
            else:
                if ok:
                    return text
                try:
                    problem = json.loads(text).get("error") or {}
                except (ValueError, AttributeError):
                    problem = {}
                raise MixelError(str(problem.get("code") or "mixel_error"), str(problem.get("message") or "Mixel couldn't answer that."), problem.get("fix"))
            missing = isinstance(cause, (FileNotFoundError, NotADirectoryError, PermissionError))
            timed_out = isinstance(cause, TimeoutError)
            if attempt >= self.retries or missing or (sent and not read_only):
                if timed_out:
                    raise MixelTimeoutError(f"Mixel took longer than {self.timeout:g} s to answer.", "try again; Mixel may still be indexing") from None
                raise MixelUnavailableError("library_search_off", LIBRARY_LOST if sent else LIBRARY_OFF, LIBRARY_FIX) from None
            time.sleep(0.1 * 2 ** attempt)
        raise AssertionError("unreachable")

    def _once(self, tool: str, args: dict) -> tuple[bool, str]:
        call = {"id": self._next, "caller": self.caller, "tool": tool, "args": args}
        self._next += 1
        agent = self.data_dir / "agent"
        with contextlib.ExitStack() as stack:
            try:
                if sys.platform == "win32":
                    # Windows: 127.0.0.1, a port and a token that are new at every start, in a file only the person reads.
                    try:
                        where = json.loads((agent / "endpoint.json").read_text())
                        call["token"] = str(where["token"])
                        port = int(where["port"])
                    except (OSError, ValueError, KeyError, TypeError):
                        raise MixelUnavailableError("library_search_off", LIBRARY_OFF, LIBRARY_FIX) from None
                    link = stack.enter_context(socket.create_connection(("127.0.0.1", port), timeout=self.timeout))
                else:
                    link = stack.enter_context(socket.socket(socket.AF_UNIX, socket.SOCK_STREAM))
                    link.settimeout(self.timeout)
                    link.connect(str(agent / "mixel.sock"))
            except MixelError:
                raise
            except OSError as error:
                raise _NotSent() from error
            link.sendall((json.dumps(call) + "\n").encode())
            line = stack.enter_context(link.makefile("rb")).readline()
        if not line.endswith(b"\n"):
            raise ConnectionResetError("Mixel closed the connection before it answered.")
        reply = json.loads(line)
        if not isinstance(reply, dict) or not isinstance(reply.get("text"), str):
            raise MixelError("mixel_error", "Mixel's answer wasn't one this SDK understands.", "update the SDK")
        return reply.get("ok") is True, reply["text"]

    # --- developer mode: the dev socket -----------------------------------------------------------

    def status(self) -> dict:
        """The running Mixel's version, its SDK and app protocol: {"mixel", "sdk", "protocol"}."""
        return self._dev("GET", "/v1/status")

    def open_app(self, folder: str | os.PathLike) -> DevApp:
        """Opens an app folder in Mixel, badged "In development". Run ``mixel check`` first:
        Mixel refuses a folder with errors and says which."""
        opened = self._dev("POST", "/v1/apps", {"dir": str(Path(folder).resolve())}, timeout=60)
        return DevApp(self, str(opened["id"]), str(opened.get("displayName", "")), str(opened.get("version", "")))

    def _dev_endpoint(self) -> tuple[str, str]:
        try:
            info = json.loads((self.data_dir / "dev.json").read_text())
            return f"http://127.0.0.1:{int(info['port'])}", str(info["token"])
        except (OSError, ValueError, KeyError, TypeError):
            raise MixelUnavailableError("desktop_unavailable", DEV_OFF, DEV_FIX) from None

    def _dev(self, method: str, path: str, body: dict | None = None, timeout: float | None = None) -> dict:
        for attempt in range(self.retries + 1):
            base, token = self._dev_endpoint()
            data = json.dumps(body).encode() if body is not None else None
            request = urllib.request.Request(base + path, data=data, method=method, headers={"authorization": f"Bearer {token}", "content-type": "application/json"})
            try:
                with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                    return json.loads(response.read() or b"{}")
            except urllib.error.HTTPError as error:
                try:
                    problem = json.loads(error.read()).get("error") or {}
                except (ValueError, AttributeError):
                    problem = {}
                raise MixelError(str(problem.get("code") or "desktop_error"), str(problem.get("message") or f"Mixel answered {error.code}."), problem.get("fix")) from None
            except (urllib.error.URLError, OSError, ValueError) as error:
                reason = getattr(error, "reason", error)
                if attempt >= self.retries or method != "GET":
                    if isinstance(reason, TimeoutError):
                        raise MixelTimeoutError(f"Mixel took longer than {timeout or self.timeout:g} s to answer.", "try again") from None
                    raise MixelUnavailableError("desktop_unavailable", DEV_OFF, DEV_FIX) from None
                time.sleep(0.1 * 2 ** attempt)
        raise AssertionError("unreachable")


class DevApp:
    """An app folder open in Mixel, in development."""

    def __init__(self, mixel: Mixel, id: str, display_name: str, version: str) -> None:
        self._mixel = mixel
        self.id = id
        self.display_name = display_name
        self.version = version

    def __repr__(self) -> str:
        return f"DevApp({self.id!r}, {self.display_name!r}, {self.version!r})"

    def reload(self, changed: Sequence[str] = ()) -> None:
        """Restart its worker and reload its page, as ``mixel dev`` does on save."""
        self._mixel._dev("POST", f"/v1/apps/{self.id}/reload", {"changed": list(changed)[:20]})

    def close(self) -> None:
        self._mixel._dev("DELETE", f"/v1/apps/{self.id}")

    def log(self, timeout: float | None = None) -> Iterator[dict]:
        """Its log as it happens, {"type": "log" | "error" | "info", "text"}, until it closes, or for ``timeout`` seconds."""
        base, token = self._mixel._dev_endpoint()
        request = urllib.request.Request(f"{base}/v1/apps/{self.id}/log", headers={"authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(request, timeout=timeout or 3600 * 24) as response:
                for raw in response:
                    try:
                        line = json.loads(raw)
                    except ValueError:
                        continue
                    yield line
                    if line.get("type") == "closed":
                        return
        except TimeoutError:
            return
        except urllib.error.URLError as error:
            if isinstance(error.reason, TimeoutError):
                return
            raise MixelUnavailableError("desktop_unavailable", DEV_OFF, DEV_FIX) from None


# --- an app's action, run here the way Mixel runs it -------------------------------------------------


@dataclass(frozen=True)
class AppRun:
    # What the action returned.
    result: object
    # What it put in the Library: [{"id", "kind", "title", "path"}].
    items: list[dict]
    # What it sent with ox.emit while it ran: [name, body] pairs.
    events: list
    # The last lines it printed.
    log_tail: list[str]


def run_app(folder: str | os.PathLike, action: str, *, input: dict | None = None, files: Sequence[str | os.PathLike] = (), out: str | os.PathLike | None = None) -> AppRun:
    """Runs one action of the app in ``folder`` on real files, in its own Python, the way Mixel does
    (and ``mixel run``). Mixel needn't be open. ``out`` keeps what it makes in that folder.
    A failed action raises a MixelError with its code: bad_input, problem, crashed, timeout, no_such_action."""
    from ox1audio.cli import running
    from ox1audio.cli.out import Stop

    try:
        done = running.run(Path(folder).resolve(), action, dict(input or {}), [str(Path(file).resolve()) for file in files], out=str(Path(out).resolve()) if out else None)
    except Stop as error:
        raise MixelError(error.error or "usage", error.message, error.fix or None) from None
    if not done.get("ok"):
        problem = done.get("error") or {}
        raise MixelError(str(problem.get("code") or "crashed"), str(problem.get("message") or "The action failed."), problem.get("hint") or problem.get("fix"))
    return AppRun(done.get("result"), list(done.get("items") or []), list(done.get("events") or []), list(done.get("log_tail") or [])[-40:])


def _query(want, avoid, unlike, type, key, bpm, length, offset=None) -> dict:
    filters = {name: value for name, value in (("type", type), ("key", key), ("bpm", list(bpm) if bpm else None), ("length", list(length) if length else None)) if value is not None}
    return {
        **({"want": want} if want else {}),
        **({"avoid": list(avoid)} if avoid else {}),
        **({"unlike": list(unlike)} if unlike else {}),
        **({"filters": filters} if filters else {}),
        **({"offset": int(offset)} if offset else {}),
    }
