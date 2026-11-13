# Changelog

Every release of `ox1audio` (the Python SDK and the `mixel` command), newest first.

**How versions work.** `ox1audio` follows [semantic versioning](https://semver.org).

- **Until 1.0, the middle number is the app API.** An app's `app.json` says `"sdk": "^0.3"`, and every 0.3.x release keeps that app working. 0.3.x releases only add things and fix bugs.
- A release that changes what an existing app hears or makes says so first, under **Changed**.
- Something an app can use is never removed within 0.3. A name that goes away first stays, with an error that names its replacement.
- The tools for scripts outside Mixel (`ox1audio.local`, `ox1audio.api`, `ox1audio.cloud`) follow the same promise from 0.3.5.

## 0.3.5 (not published yet)

### Added

- **`ox1audio.local`: the Mixel on this computer, from a script.** `Mixel()` finds the running Mixel through its data folder (or `MIXEL_DATA_DIR`).
  - `overview()` says what the Library holds, in counts.
  - `search(words, avoid=, type=, key=, bpm=, length=)` searches your own sounds by words, 10 at a time. `offset=found.next` gets the next page from a Mixel that pages.
  - `similar(id)` finds sounds close to one a search returned.
  - `propose_crate(title, request, ids)` hands you a crate to audition.
  - In developer mode, `status()` and `open_app(folder)` open an app folder in Mixel, with `reload()`, `log()` and `close()`.
  - `run_app(folder, action, files=, input=)` runs one action here, the way Mixel runs it (and as `mixel run` does). Mixel needn't be open.
- **`ox1audio.api.connect()`: the cloud with timeouts, retries and typed errors.** It uses the token `mixel login` saved (or `MIXEL_TOKEN`). Each attempt may take 30 s. A GET is tried 2 more times after a network failure, a timeout, or a 408, 429, 502, 503 or 504, honouring `Retry-After`. A POST is never sent twice. The `asyncio` functions behave the same way.
- **`ox1audio.errors`.** Every failure is a `MixelError` with `code`, `message` and `fix`:
  - `MixelApiError` when the cloud answered with an error, with `status`, `param`, `doc_url` and every problem in `errors`;
  - `MixelUnavailableError` when nothing answered;
  - `MixelTimeoutError` when the answer was too slow.

  `str(error)` is one line, and `error.to_dict()` is `{code, message, fix}`.
- Agent-friendly output: `str(found)` is the compact reply Mixel sent (about 300 tokens at most), not the objects.
- `examples/` with five runnable examples, and `examples/smoke.py` to run them against your Mixel.
- `scripts/openapi.py` cuts `openapi.json` from the cloud's spec and regenerates `ox1audio.cloud`. With `--check`, it fails when either is behind.
- `mixel dev` also finds Mixel through `MIXEL_DATA_DIR`, the name the desktop itself uses.
- `mixel mcp`: `library_search` takes `offset` (the reply's `next`) for the next page, as Mixel's own tools do. When Mixel takes too long, the code is `timeout`, not `library_search_off`.
- The errors index (`mixel docs errors`, `mixel://errors/{code}`, the docs site) lists the Library's codes (`not_ready`, `unknown_id`, `too_many`, `crates_off`, `unknown_tool`, `too_long`, `mixel_error`) and the registry's (`github_required`, `repository_not_yours`, `commit_not_pushed`, `submission_pending`, `waitlisted`, `terms_required`, …), so every `doc_url` the cloud sends lands on a row.

- **The `library-read` permission (Mixel 0.1.23).** `library` adds to the Library; `library-read` lists it and opens a sound the person picks. `app.json`'s schema, `mixel check`, `mixel docs permissions` and AGENTS.md know both.
- `ox1audio.cloud` follows today's API: `Me` has `notices`, and `TermsStanding` has `minimum`, `required_from` and `review`.
- `python-dateutil` is a dependency: `ox1audio.cloud` imports it, and an install without the development extras failed on `import ox1audio.cloud`.
- Package metadata for PyPI (the README as the project page, links, classifiers), CI on every push, and a wheel attached to every GitHub release, for installs before PyPI.

### Changed

- **A page that lists or opens Library sounds needs `"library-read"` in `app.json`.** `mixel check` reports `permission_undeclared` for `ox.library.list`, `ox.library.file`, `LibraryDialog` or `LibraryBrowser` without it, and no longer counts them as `library`. An app that only returns or adds sounds changes nothing.
- `library_search_off` says where the switch is now: Settings › Your assistant. `desktop_unavailable` says to reopen Mixel after turning on Developer mode, because it takes effect then.
- A design-system component's one-line use, in `ui_components`, is cut after a whole word.
- **`ox1audio.cloud` now matches the Mixel cloud as it is.** The calls are `health`, `me`, `cli_login`, `cli_login_poll`, `cli_tokens`, `revoke_cli_token`, `app_catalog`, `create_submission`, `submissions` and `submission`.
- **`mixel check` fails when `app.json` asks for `library-read` and `network` together** (`permission_pair`). An app that sees the person's Library can't also reach the network until Mixel runs apps in a sandbox, and Mixel won't install or open one that asks for both. Mixel's own apps (a checkout whose origin is a 0x1audio repository) follow the rules they had. A Files control lets people choose their sounds without `library-read`.
- **`mixel check --fix` installs numpy for `ox.audio.read` and `ox.audio.write`.** It listed numpy and wrote `uv.lock` but didn't install it, so the next `mixel check` passed and `mixel run` stopped at the helper. A listed package the helpers need that isn't installed is now `dependency_not_installed`, which `--fix` settles with `uv sync`; without `uv`, the finding stays and names the command.
- `mixel new --page` and AGENTS.md name the page SDK `@ox1audio/sdk`, the name it has on npm.
- `mixel check` refuses `ox1audio.local`, `ox1audio.api`, `ox1audio.cli` and `ox1audio.mcp` in an app's code. An app reaches the Library through `ox.library` and its `library` permission.

### Removed

- `ox1audio.cloud`'s `register`, `verify_registration`, `choose_password`, `resend_registration`, `login`, `session`, `logout`, `desktop_handoff` and `desktop_exchange`. Sign-in is now on the web, through the cloud's own sign-in pages. These routes no longer exist on the server, so calling them already failed.

## 0.3.4

- The `gpu` permission, for apps that run a model on the graphics card.

## 0.3.3

- `ox.audio.write`: the samples' dtype decides for integer samples. An integer copy is cut only for samples over full scale.

## 0.3.2

- Audio Engineering's review of 0.3.1. `convert` lowers a float source that goes over 0 dBFS by one whole-file gain, and says so in the result.

## 0.3.1

**Changed: the audio output stage.**

- `ox.audio.write` dithers (TPDF) only when the bit depth drops, and refuses to clip silently.
- `bits=32` writes float.
- `convert` keeps tags, cover art and loop points.

## 0.3.0

One way to build an app: `@ox.action`, a typed Python function that Mixel runs as a job, with progress and Stop. `@ox.screen`, `@ox.job` and `serve` became errors that name their replacement.

**The SDK:**

- controls inferred from types, including `ox.Range` and `ox.Slider(origin=)`;
- `ox.beside`, `ox.emit` and `ox.temp`;
- Stop keeps what an action finished;
- the shared contract for `app.json`, the protocol and the errors.

**The `mixel` command:** `new` (with `--page`), `check` (refusing dangerous code however it is spelled), `test`, `run`, `dev`, `login`, `publish`, `status`, `docs`, `doctor` and `mcp`.

**Licence and publishing:** Apache-2.0, a DCO for contributions, a security policy, and a hand-run PyPI publish with trusted publishing.
