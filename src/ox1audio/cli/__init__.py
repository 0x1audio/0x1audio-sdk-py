"""The mixel command: start an app, check it, test it, open it in Mixel, and publish it.

Installed with ``uv tool install ox1audio``. Each command lives in its own module and is
imported only when it runs, so ``mixel`` starts fast (the MCP server starts it often).
"""

from __future__ import annotations

import sys

from ox1audio import __version__
from ox1audio.cli.out import DOCS, OK, Stop, stop

_SECTIONS = [
    ("Start", [
        ('new "My App"', "start an app in ./my-app (Apache-2.0 unless --license names another)", "--license SPDX"),
        ("dev", "open this app in Mixel, reload it on save", ""),
    ]),
    ("Check", [
        ("check", "the rules Mixel and its reviewers apply", "--fix --strict --json"),
        ("test", "run the tests in tests/", "-k NAME --json"),
        ("run ACTION", "run one action here", "--file PATH --set NAME=VALUE --out FOLDER --json"),
    ]),
    ("Publish", [
        ("login", "sign in with your Mixel account", ""),
        ("publish", "send this version for review", "--dry-run --json"),
        ("status", "review state and reviewer notes", "--json"),
    ]),
    ("More", [
        ("docs [TOPIC]", "the docs, offline", "--list"),
        ("doctor", "is this computer ready", "--json"),
        ("mcp", "the MCP server for coding agents (stdio)", ""),
    ]),
]


def _help() -> str:
    rows = [row for _, items in _SECTIONS for row in items]
    a = max(len(name) for name, _, _ in rows) + 6
    b = max(len(text) for _, text, _ in rows) + 2
    lines = [f"mixel {__version__}: build apps for Mixel", ""]
    for title, items in _SECTIONS:
        lines.append(title)
        lines += [f"  {('mixel ' + name).ljust(a)}  {text.ljust(b)}{flags}".rstrip() for name, text, flags in items]
    lines += ["", "Install or update: uv tool install ox1audio", f"Docs: {DOCS}", ""]
    return "\n".join(lines)


HELP = _help()


def _command_help(command: str) -> str:
    for _, items in _SECTIONS:
        for name, text, flags in items:
            if name.split()[0] == command:
                usage = f"mixel {name}" + (f" [{flags.replace(' --', '] [--').replace(' -k', '] [-k')}]" if flags else "")
                return f"{usage}\n  {text}\n\nDocs: mixel docs cli\n"
    return HELP

COMMANDS = {
    "new": "ox1audio.cli.new",
    "check": "ox1audio.cli.check",
    "test": "ox1audio.cli.testing",
    "run": "ox1audio.cli.running",
    "dev": "ox1audio.cli.dev",
    "login": "ox1audio.cli.registry",
    "logout": "ox1audio.cli.registry",
    "publish": "ox1audio.cli.registry",
    "status": "ox1audio.cli.registry",
    "docs": "ox1audio.cli.docs",
    "doctor": "ox1audio.cli.doctor",
    "mcp": "ox1audio.mcp",
}

GONE = {
    "eject": (
        "mixel eject is gone: a page builds around the same form Mixel draws.",
        'add a Vite page that renders <ActionForm action="..."/> from @0x1audio/design-system, and set "page": "dist/index.html"',
        "page",
    ),
}


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    raise SystemExit(dispatch(args))


def dispatch(args: list[str]) -> int:
    if not args or args[0] in {"-h", "--help", "help"}:
        print(HELP, end="")
        return OK
    if args[0] in {"-V", "--version", "version"}:
        print(f"mixel {__version__}")
        return OK
    command, rest = args[0], args[1:]
    as_json = "--json" in rest
    try:
        if command in GONE:
            message, fix, doc = GONE[command]
            raise Stop(message, fix=fix, doc=doc)
        module_name = COMMANDS.get(command)
        if module_name is None:
            near = [name for name in COMMANDS if name.startswith(command[:2])]
            raise Stop(f"mixel {command} is not a command.", fix=f"mixel {near[0]}" if near else "mixel --help")
        if {"-h", "--help"} & set(rest):
            print(_command_help(command), end="")
            return OK
        import importlib

        module = importlib.import_module(module_name)
        handler = getattr(module, command, None) if command in {"login", "logout", "publish", "status"} else module.command
        return int(handler(rest) or 0)
    except Stop as error:
        return stop(error, as_json)
    except KeyboardInterrupt:
        return 130


# What older code and tests import from here.
def tone(seconds: float = 0.5, rate: int = 44100) -> bytes:
    from ox1audio.cli.new import tone as make

    return make(seconds, rate)


def agents_md() -> str:
    from ox1audio.cli.new import agents_md as read

    return read()
