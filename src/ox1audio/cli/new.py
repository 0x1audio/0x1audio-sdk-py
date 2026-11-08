"""mixel new: an app that checks clean and passes its own test from the first minute."""

from __future__ import annotations

import io
import json
import math
import re
import struct
import wave
from pathlib import Path

from ox1audio import __version__
from ox1audio.cli.out import FAILED, OK, Stop
from ox1audio._contract import LICENSE_PATTERN
from ox1audio.manifest import SCHEMA

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
out/
"""

PYPROJECT = """[project]
name = "{slug}"
version = "0.1.0"
requires-python = ">=3.11"
license = "{license}"
dependencies = []
"""

README = """# {title}

{summary}

A Mixel app. `app.py` holds its actions; `AGENTS.md` explains how to build it.

```sh
mixel check   # the rules Mixel and the reviewers apply
mixel test    # the tests in tests/
mixel dev     # open it in Mixel, reload on save
```
"""


def command(args: list[str]) -> int:
    license = "Apache-2.0"
    words = []
    rest = iter(args)
    for arg in rest:
        if arg == "--license" or arg.startswith("--license="):
            license = arg.split("=", 1)[1] if "=" in arg else next(rest, "")
            if not re.match(LICENSE_PATTERN, license):
                raise Stop(f"{license or 'That'} is not an SPDX licence identifier.", fix='mixel new "Make It Louder" --license MIT', doc="reference/app-json#license")
        elif not arg.startswith("--"):
            words.append(arg)
    title = " ".join(words).strip()
    if not title:
        raise Stop('mixel new needs a name.', fix='mixel new "Make It Louder"', doc="start")
    return new(Path.cwd() / slug(title), title, license)


# The words about converting that an app must rewrite once it does something else (mixel check --strict).
TEMPLATE_WORDS = {"summary": "Convert songs to another format.", "library": "Save the converted copies to your Library."}


def new(directory: Path, title: str, license: str = "Apache-2.0") -> int:
    if directory.exists() and any(directory.iterdir()):
        raise Stop(f"{directory.name}/ already has files in it.", fix=f'choose another name, or delete {directory.name}/', code=FAILED, error="folder_not_empty")
    name = directory.name
    summary = TEMPLATE_WORDS["summary"]
    files = {
        "app.py": APP,
        "app.json": json.dumps({
            "$schema": SCHEMA,
            "name": name,
            "displayName": title[:48],
            "summary": summary,
            "version": "0.1.0",
            "sdk": f"^{'.'.join(__version__.split('.')[:2])}",
            "entry": "app.py",
            "license": license,
            "permissions": {
                "files": "Open the songs you choose.",
                "library": TEMPLATE_WORDS["library"],
            },
        }, indent=2) + "\n",
        "AGENTS.md": agents_md(),
        "tests/__init__.py": "",
        "tests/test_app.py": TEST,
        "pyproject.toml": PYPROJECT.format(slug=name, license=license),
        "README.md": README.format(title=title, summary=summary),
        ".gitignore": GITIGNORE,
    }
    # Apache-2.0 by default, like Mixel's own apps. Another licence: bring its text as LICENSE.
    if license == "Apache-2.0":
        files["LICENSE"] = Path(__file__).resolve().parents[1].joinpath("templates", "Apache-2.0.txt").read_text()
    for file, body in files.items():
        target = directory / file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    (directory / "tests" / "tone.wav").write_bytes(tone())
    repository = _git_init(directory)
    print(f"Created {name}/{' (a new git repository)' if repository else ''}")
    notes = {
        "app.py": "one action, convert: change it into yours",
        "app.json": "name, summary, permissions (rewrite the words for your app)",
        "AGENTS.md": "the whole API, for you and your coding agent",
        "tests/test_app.py": "runs convert on tests/tone.wav",
        "pyproject.toml": "Python packages your app needs",
        "LICENSE": "Apache-2.0; mixel new --license MIT picks another" if license == "Apache-2.0" else f"add the {license} text here",
    }
    width = max(len(file) for file in notes)
    for file, note in notes.items():
        print(f"  {file.ljust(width)}  {note}")
    print(f"Next\n  cd {name}\n  mixel check   the rules Mixel and its reviewers apply\n  mixel test    run tests/\n  mixel dev     open it in Mixel, reload on save")
    return OK


def _git_init(directory: Path) -> bool:
    """An app is its own repository (publish needs one). Not inside another repository, and never fatal."""
    import shutil
    import subprocess

    if not shutil.which("git"):
        return False
    try:
        inside = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=directory, capture_output=True, text=True, timeout=20)
        if inside.returncode == 0:
            return False
        return subprocess.run(["git", "init", "-q", "-b", "main"], cwd=directory, capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def agents_md() -> str:
    return Path(__file__).resolve().parents[1].joinpath("AGENTS.md").read_text()


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


def slug(title: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in title).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    if cleaned and not cleaned[0].isalpha():
        cleaned = f"app-{cleaned}"
    return cleaned[:48].strip("-") or "app"
