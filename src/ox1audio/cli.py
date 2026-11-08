"""The ox command: start an app, and check it the way 0x1audio will."""

from __future__ import annotations

import importlib.util
import io
import json
import math
import re
import struct
import sys
import wave
from pathlib import Path

from ox1audio import __version__
from ox1audio.manifest import SCHEMA, Finding, check as check_manifest

DOCS = "https://docs.0x1audio.com"

HELP = f"""ox {__version__}: build 0x1audio apps

  ox new "My App"   start an app in ./my-app
  ox check          check app.json and the actions in this folder

Docs: {DOCS}
"""

APP = '''import ox1audio as ox


@ox.action("Convert")
def convert(files: ox.Files("audio"), format: ox.Choice("wav", "flac", "mp3") = "wav"):
    made = []
    for i, path in enumerate(files):
        ox.progress(i / len(files), path.name)
        out = ox.audio.convert(path, format)
        made.append(ox.sound(out, title=path.stem))
    return made
'''

TEST = '''import unittest
from pathlib import Path

import ox1audio as ox

import app

TONE = Path(__file__).with_name("tone.wav")


class AppTest(unittest.TestCase):
    def test_convert_makes_a_copy_for_the_library(self):
        run = ox.test(app.convert, files=[TONE], format="flac")
        self.assertEqual(run["items"][0]["title"], "tone")
        self.assertTrue(run["items"][0]["path"].endswith(".flac"))


if __name__ == "__main__":
    unittest.main()
'''

GITIGNORE = """__pycache__/
*.py[cod]
.venv/
node_modules/
"""

PYPROJECT = """[project]
name = "{slug}"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []
"""

README = """# {title}

{summary}

A 0x1audio app. `app.py` holds its actions; `AGENTS.md` explains how to build it.

```sh
ox check
python -m unittest
```
"""


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help", "help"}:
        print(HELP, end="")
        return
    command, rest = args[0], args[1:]
    if command == "new":
        title = " ".join(rest).strip()
        if not title:
            _usage('ox new needs a name, like ox new "Make It Louder".')
        raise SystemExit(new(Path.cwd() / _slug(title), title))
    if command == "check":
        raise SystemExit(check(Path(rest[0]) if rest else Path.cwd()))
    if command == "eject":
        _usage(
            "ox eject is gone: a page now builds around the same form 0x1audio draws.",
            fix='add a Vite page that renders <ActionForm action="..."/> from @0x1audio/design-system, and set "page": "dist/index.html"',
            doc="page",
        )
    _usage(f"ox {command} is not a command.", fix="run ox --help")


def _usage(message: str, fix: str = "", doc: str = "") -> None:
    lines = [message]
    if fix:
        lines.append(f"fix:  {fix}")
    if doc:
        lines.append(f"docs: {DOCS}/{doc}")
    print("\n".join(lines), file=sys.stderr)
    raise SystemExit(2)


def new(directory: Path, title: str) -> int:
    if directory.exists() and any(directory.iterdir()):
        print(f"{directory.name}/ already has files in it. Choose another name.", file=sys.stderr)
        return 1
    slug = directory.name
    summary = "Convert songs to another format."
    files = {
        "app.py": APP,
        "app.json": json.dumps({
            "$schema": SCHEMA,
            "name": slug,
            "displayName": title[:48],
            "summary": summary,
            "version": "0.1.0",
            "sdk": f"^{'.'.join(__version__.split('.')[:2])}",
            "entry": "app.py",
            "permissions": {
                "files": "Open the songs you choose.",
                "library": "Save the converted copies to your Library.",
            },
        }, indent=2) + "\n",
        "AGENTS.md": agents_md(),
        "tests/__init__.py": "",
        "tests/test_app.py": TEST,
        "pyproject.toml": PYPROJECT.format(slug=slug),
        "README.md": README.format(title=title, summary=summary),
        ".gitignore": GITIGNORE,
    }
    for name, body in files.items():
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    (directory / "tests" / "tone.wav").write_bytes(tone())
    print(f"Created {slug}/")
    width = max(len(name) for name in files)
    notes = {"app.py": "one action: convert", "app.json": "name, version, permissions", "AGENTS.md": "the rules, for you and your coding agent", "tests/test_app.py": "runs convert on a test tone"}
    for name, note in notes.items():
        print(f"  {name.ljust(width)}  {note}")
    print(f"Next\n  cd {slug}\n  ox check")
    return 0


def agents_md() -> str:
    return (Path(__file__).with_name("AGENTS.md")).read_text()


def tone(seconds: float = 0.5, rate: int = 44100) -> bytes:
    """A quiet 440 Hz tone, so the first test has audio to work on."""
    frames = b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate))) for i in range(int(seconds * rate)))
    out = io.BytesIO()
    with wave.open(out, "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(rate)
        file.writeframes(frames)
    return out.getvalue()


def check(folder: Path) -> int:
    folder = folder.resolve()
    manifest = check_manifest(folder)
    findings = list(manifest.findings)
    data = manifest.data
    names: list[str] = []
    worker = data.get("worker")
    entry = data.get("entry") or (worker.get("entry") if isinstance(worker, dict) else None)
    if isinstance(entry, str) and (folder / entry).is_file():
        loaded, problem = _load(folder / entry)
        if problem:
            findings.append(problem)
        else:
            names = [item.name for item in loaded]
            used = set()
            for item in loaded:
                used |= item.permissions()
            used |= _static_permissions(folder)
            declared = manifest.permissions
            if data.get("$schema"):
                for code in sorted(used - declared):
                    findings.append(Finding(
                        "permission_undeclared", f"app.json › permissions.{code}",
                        f"The code uses {code} ({_why_used(code)}), but app.json doesn't ask for it.",
                        f'add "{code}": "{_reason(code)}" to permissions (write the reason in your own words)', "permissions",
                    ))
                for code in sorted(declared - used - {"network"}):
                    findings.append(Finding("permission_unused", f"app.json › permissions.{code}", f"app.json asks for {code}, but the code doesn't seem to use it.", "remove it, so people aren't asked for more than the app needs", "permissions", "warn"))
    title = f"{data.get('name') or folder.name} {data.get('version') or ''}".strip()
    print(f"Checking {title} (sdk {data.get('sdk', 'missing')})\n")
    errors = [item for item in findings if item.severity == "error"]
    warnings = [item for item in findings if item.severity != "error"]
    for item in errors + warnings:
        label = "error" if item.severity == "error" else "warn "
        print(f"{label}  {item.code}  {item.where}")
        for line in item.message.splitlines():
            print(f"       {line}")
        print(f"       fix:  {item.fix}")
        print(f"       docs: {item.doc}\n")
    if errors:
        print(f"{_count(len(errors), 'error')}{', ' + _count(len(warnings), 'warning') if warnings else ''}. Fix the errors, then run ox check again.")
        return 1
    actions = f"{_count(len(names), 'action')}: {', '.join(names)}" if names else "no actions"
    print(f"No errors{', ' + _count(len(warnings), 'warning') if warnings else ''}. {actions}.")
    return 0


def _load(entry: Path):
    from ox1audio import app as runner
    from ox1audio.action import actions, clear

    clear()
    sys.path.insert(0, str(entry.parent))
    runner._loading = True
    try:
        spec = importlib.util.spec_from_file_location("__ox_check__", entry)
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as exc:  # noqa: BLE001 - every failure is reported as a finding
        text = str(exc)
        fix_line = re.search(r"\nfix:  (.*)", text)
        doc_line = re.search(r"\ndocs: https://docs\.0x1audio\.com/(\S+)", text)
        first = text.split("\nfix:")[0].strip() or type(exc).__name__
        return [], Finding("app_failed_to_load", f"{entry.name}{_line_of(exc, entry)}", f"{type(exc).__name__}: {first}", fix_line.group(1) if fix_line else "fix the error at that line", doc_line.group(1) if doc_line else "actions")
    finally:
        runner._loading = False
        sys.path.remove(str(entry.parent))
    found = actions()
    if not found:
        return [], Finding("no_actions", entry.name, f"{entry.name} has no actions.", '@ox.action("Title") above a function makes it an action', "actions#an-action")
    return found, None


def _line_of(exc: BaseException, entry: Path) -> str:
    tb = exc.__traceback__
    line = ""
    while tb is not None:
        if Path(tb.tb_frame.f_code.co_filename).resolve() == entry.resolve():
            line = f":{tb.tb_lineno}"
        tb = tb.tb_next
    return line


_library = re.compile(r"\b(ox\.)?(sound|midi|file)\(|\blibrary\.add\(")
_data = re.compile(r"\bdata\.(read|read_text|write|list|remove|root)\(|OX1_DATA")


def _static_permissions(folder: Path) -> set[str]:
    used: set[str] = set()
    for path in folder.rglob("*.py"):
        parts = set(path.relative_to(folder).parts)
        if parts & {".venv", "tests", "node_modules", "dist", "__pycache__"}:
            continue
        text = path.read_text(errors="replace")
        if _library.search(text) and "ox1audio" in text:
            used.add("library")
        if _data.search(text):
            used.add("data")
    return used


def _why_used(code: str) -> str:
    return {"files": "a Files or Folder control", "library": "it returns or adds sounds", "data": "it uses ox.data"}.get(code, code)


def _reason(code: str) -> str:
    return {"files": "Open the songs you choose.", "library": "Save the results to your Library.", "data": "Remember your settings on this computer."}.get(code, "Why the app needs it.")


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def _slug(title: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in title).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned or "app"


if __name__ == "__main__":
    main()
