"""Create an app, or turn its screen into a page the author can edit."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from ox1audio.screen import clear as clear_screens
from ox1audio.screen import screens

AGENTS = """# Building this app

This folder is the whole app.

- `app.py` is the work. A function decorated with `@ox.screen` becomes a screen.
- `app.json` names the app.
- `ui/App.tsx` is optional. `ox eject` writes it when the screen needs a custom layout.
- `ui/components/` holds a React component the kit does not have.
- `AGENTS.md` is the spec. Read this and stop.

```python
import ox1audio as ox

@ox.screen("Audio Converter")
def convert(files: ox.Files, format: ox.Choice("wav", "flac", "mp3")):
    for audio in files:
        out = ox.audio.convert(audio, format)
        yield ox.progress(1, audio)
        yield ox.sound(out, title="Converted")
```

Controls: `Files`, `Choice`, `Text`, `Number`, `Toggle`, `Slider`.
Yield `ox.progress(fraction, label)` to report progress.
Yield `ox.sound`, `ox.midi`, or `ox.file` to add to the Library.
`ox.test(convert, files=[...])` runs the function without the desktop.
`print` goes to the log. The desktop owns the protocol stream.
Permissions come from the controls and the exports. A custom page lists them in `app.json`: `files`, `library`, `network`, `data`.
"""

APP = '''import ox1audio as ox


@ox.screen("{title}")
def hello(name: ox.Text):
    who = name.strip() if isinstance(name, str) and name.strip() else "world"
    return {{"message": f"Hello, {{who}}"}}


if __name__ == "__main__":
    ox.run()
'''

MANIFEST = """{{
  "name": "{slug}",
  "displayName": "{title}",
  "version": "0.1.0",
  "worker": {{
    "runtime": "python",
    "entry": "app.py"
  }}
}}
"""


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help"}:
        print("ox new \"Audio Converter\"\nox eject")
        return
    if args[0] == "new":
        title = " ".join(args[1:]).strip() or "Hello"
        _new(Path.cwd() / _slug(title), title)
        return
    if args[0] == "eject":
        _eject(Path.cwd())
        return
    raise SystemExit("Use ox new or ox eject.")


def _new(directory: Path, title: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    slug = directory.name
    (directory / "app.py").write_text(APP.format(title=title))
    (directory / "app.json").write_text(MANIFEST.format(slug=slug, title=title))
    (directory / "AGENTS.md").write_text(AGENTS)
    print(directory)


def _eject(directory: Path) -> None:
    entry = directory / "app.py"
    if not entry.is_file():
        raise SystemExit("This folder has no app.py.")
    clear_screens()
    spec = importlib.util.spec_from_file_location("ox_app", entry)
    if spec is None or spec.loader is None:
        raise SystemExit("Could not read app.py.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    found = screens()
    if not found:
        raise SystemExit("app.py has no screen.")
    ui = directory / "ui"
    ui.mkdir(exist_ok=True)
    (ui / "App.tsx").write_text(_tsx(found))
    manifest = directory / "app.json"
    data = json.loads(manifest.read_text()) if manifest.is_file() else {}
    data["frontend"] = "ui/App.tsx"
    manifest.write_text(json.dumps(data, indent=2) + "\n")
    print(ui / "App.tsx")


def _tsx(found) -> str:
    screen = found[0]
    from ox1audio.screen import fields_of

    fields = fields_of(screen)
    names = sorted({_component(field["kind"]) for field in fields} | {"Button", "Screen"})
    controls = "\n".join(_control(field) for field in fields)
    title = getattr(screen, "__ox_title__", screen.__name__)
    return (
        f'import {{ {", ".join(names)} }} from "@0x1audio/ui"\n\n'
        "export function App() {\n"
        "  return (\n"
        f'    <Screen title="{title}" action="{screen.__name__}">\n'
        f"{controls}\n"
        "      <Button>Run</Button>\n"
        "    </Screen>\n"
        "  )\n"
        "}\n"
    )


def _component(kind: str) -> str:
    return {"files": "Drop", "choice": "Choice", "text": "Field", "number": "Field", "toggle": "Toggle", "slider": "Slider"}.get(kind, "Field")


def _control(field: dict) -> str:
    kind = field["kind"]
    name = field["name"]
    if kind == "files":
        return f'      <Drop name="{name}" accept="{field.get("accept", "audio")}" />'
    if kind == "choice":
        options = ", ".join(f'"{option}"' for option in field.get("options", []))
        return f'      <Choice name="{name}" options={{[{options}]}} />'
    if kind == "slider":
        return f'      <Slider name="{name}" min={{{field.get("min", 0)}}} max={{{field.get("max", 1)}}} />'
    if kind == "toggle":
        return f'      <Toggle name="{name}" />'
    return f'      <Field name="{name}" />'


def _slug(title: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in title).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned or "app"
