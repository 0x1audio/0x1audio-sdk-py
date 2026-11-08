# Building a 0x1audio app

This folder is one app: Python actions that 0x1audio runs on the person's computer. Use only the API on this page; what is not here is not supported. Don't read the SDK source.

## Loop
1. Edit `app.py`. If what the code touches changes, update `app.json` › `permissions`.
2. `mixel check` until it reports no errors. Each error ends with a `fix:` line; do that. `--fix` adds missing permissions.
3. `mixel test` runs `tests/`. `mixel run ACTION --file song.wav --set NAME=VALUE` runs one action on a real file.
4. `mixel dev` opens the app in 0x1audio and reloads it on save. Never `mixel publish`, or change permissions, unless the person asks.

## An action
```python
import ox1audio as ox

@ox.action("Convert")
def convert(files: ox.Files("audio"), format: ox.Choice("wav", "flac", "mp3") = "wav"):
    made = []
    for i, path in enumerate(files):             # each path is a pathlib.Path
        ox.progress(i / len(files), path.name)   # Stop takes effect here
        out = ox.audio.convert(path, format)     # a new file, in a temporary folder
        made.append(ox.sound(out, title=path.stem))
    return made                                  # sounds are added to the Library
```
- One decorated function per action. The parameters are the controls; Python defaults are their defaults. 0x1audio draws the form, checks the input, runs the action in the background, and shows progress and Stop.
- Controls: `ox.Files("audio" | "midi" | "any", multiple=True)` gives `list[Path]` (one `Path` with `multiple=False`), `ox.Folder()` gives a `Path`, `ox.Choice("a", "b")` a `str`, `ox.Text(placeholder="")`, `ox.Number(min, max, step)`, `ox.Slider(min, max, step)`, `ox.Toggle`. Plain `str`, `int`, `float`, `bool` work too. Every control takes `label=`. `ox.Folder() | None = None` makes one optional.
- Return `None`, a `str` (shown to the person), a JSON-able `dict` or `list` (for your page), or `ox.sound(path, title)`, `ox.midi(...)`, `ox.file(...)`, or a list of those. Metadata like `bpm=120, key="A minor"` goes after the title.
- `ox.progress(fraction, label)`: fraction 0 to 1, or `None` when unknown. Call it often, also from library callbacks. When the person presses Stop it raises `ox.Cancelled` (a `BaseException`, so `except Exception` doesn't catch it): clean up in `except ox.Cancelled:` and re-raise. Every `ox.sound/midi/file` already made is kept and reaches the Library.
- A problem the person can fix: `raise ox.Problem("That file has no audio.", hint="Try a WAV or MP3.")`. Any other exception shows "The app ran into a problem" and the details go to the log.
- `print` goes to the log. Don't write a server, threads, or `if __name__ == "__main__"`: 0x1audio runs the actions.

## Testing
```python
import unittest

import ox1audio as ox
import app

class ConvertTest(unittest.TestCase):
    def test_converts_to_wav(self):
        run = ox.test(app.convert, files=["tests/tone.wav"], format="wav")
        self.assertEqual(run["items"][0]["title"], "tone")  # what reached the Library
```
`ox.test` returns `{"result", "items", "progress", "events"}`: what a page gets, the Library items (`id, kind, title, path, metadata`), each `(fraction, label)` and `(name, body)`. `stop_at=0.5` presses Stop halfway: it raises `ox.Cancelled`, whose `.kept` lists what was kept. `ox.Problem` is raised as is.

## Helpers
| Need | Use |
| --- | --- |
| File info | `ox.audio.probe(path)` → `.rate .channels .duration .codec` |
| Another format | `ox.audio.convert(path, "wav" / "aiff" / "flac" / "mp3" / "aac" / "ogg" / "opus", folder=None, bits=None)` → `Path` (lossless keeps the source's bit depth) |
| Samples (numpy) | `ox.audio.read(path)` → `(samples, rate)`, float32 shaped `(frames, channels)`; `ox.audio.write(samples, rate, "wav", folder=None, name="audio")` → `Path` |
| A folder for new files | `ox.temp()` → an empty folder, removed when the app closes. `folder=None` above uses one. |
| The app's own files | `ox.data.read / read_text / write / list / remove("presets/a.json")` (needs `data`) |

## app.json
```json
{
  "$schema": "https://0x1audio.com/schema/app/v1.json",
  "name": "my-converter",
  "displayName": "My Converter",
  "summary": "One file to many formats at once.",
  "version": "0.1.0",
  "sdk": "^0.3",
  "entry": "app.py",
  "permissions": {
    "files": "Open the songs you choose.",
    "library": "Save the converted copies to your Library."
  },
  "accent": "#20b4c4"
}
```
- Permissions are binding: `files` (Files and Folder controls), `library` (returning sounds), `data` (`ox.data`), `network` as `{"why": "…", "hosts": ["example.com"]}`. Ask only for what the code uses. Each reason is one sentence, 12 to 120 characters, that tells the person why.
- Optional: `icon` (a square `.svg` or `.png` in the app), `window` (`{"width", "height", "minWidth", "minHeight"}`), `tags` (up to 5), `page` (below).
- Raise `version` before each release. Never change `name`.

## Dependencies
Python packages go in `pyproject.toml` › `[project].dependencies`, wheels only; 0x1audio installs only those (`mixel check` finds missing ones). numpy, scipy and soundfile are fine. The SDK already has ffmpeg; don't add ffmpeg wrappers, pydub, or requests. Never commit models, audio, or files over 5 MB.

## A page (only when the drawn form is not enough)
A Vite + React page built to `dist/index.html`, set as `"page"`. It uses `@0x1audio/design-system` and calls the same actions:
```tsx
import { ox } from "@0x1audio/sdk/page"
import { ActionForm } from "@0x1audio/design-system"

export const App = () => <ActionForm action="convert" />   // the form 0x1audio draws; build around it
// your own controls: await ox.run("convert", { files, format }, { onProgress: (f, label) => {}, onEvent: (name, body) => {}, signal })
```
Page API: `ox.run`, `ox.actions`, `ox.files.pick / fromDrop / read / reveal`, `ox.library.list / add / file / onChange`, `ox.data.*`, `ox.app.open`. Errors are `OxError` with `.code` (`cancelled` after Stop, with `.kept`). `ox.emit("partial", body)` in Python reaches `onEvent`. Use design-system components and tokens only, no hex colours; light and dark both work.

## Words
Say what it does for a musician: song, sound, file, folder, Library. Never: worker, manifest, SDK, ffmpeg. Sentence case. Buttons are verbs. No exclamation marks. Errors say what happened, then what to do.

## Never
- Touch files other than the ones the person chose, files next to them, `ox.temp()` and `ox.data`.
- Use `subprocess`, `os.system`, `eval`/`exec`, raw sockets, or telemetry.
- Edit `AGENTS.md` or `dist/` by hand, or commit `.venv/` or `node_modules/`.
