# Mixel app rules, short

- An app is `app.py` with `@ox.action("Title")` functions (`import ox1audio as ox`), `app.json` and `tests/`. Typed parameters are the form: `ox.Files("audio")` gives `list[Path]`, plus `ox.Folder`, `ox.Choice`, `ox.Text`, `ox.Number`, `ox.Slider`, `ox.Toggle`, or plain `str/int/float/bool`.
- Call `ox.progress(fraction, label)` often: it raises `ox.Cancelled` on Stop. Return `ox.sound(path, title)` (or a list) for the Library, or a `str` to show. `raise ox.Problem(message, hint=)` for what the person can fix.
- Use `ox.audio.probe / convert / read / write`, `ox.temp()`, `ox.data.*`; never `subprocess`, sockets or telemetry. Packages go in `pyproject.toml`.
- `app.json` permissions are binding: `files`, `library` (add), `library-read` (list and open), `data`, `network` (`{why, hosts}`), each with a one-sentence reason.
- Loop: edit, `app_check` until no errors (each has a fix), `app_test`, `app_run` on a real file. Never publish or widen permissions unless the person asks.
- Unsure: `docs_search`, `docs_read`, or `mixel://agents.md`.
