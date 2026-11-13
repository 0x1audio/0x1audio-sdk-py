# Contributing

Thank you for helping with ox1audio, the Python SDK and the `mixel` command. A good bug report is as welcome as a pull request.

## Issues

- **Bugs:** say what you did, what you expected, and what happened instead. Add your OS, the version or commit, and any error text.
- **Ideas and bigger changes:** open an issue before you write the code, so we can agree on the shape first.
- **Security problems:** please don't open a public issue. [SECURITY.md](SECURITY.md) explains how to tell us privately.

## Set up

You need Git and [uv](https://docs.astral.sh/uv/).

```bash
git clone <this repository> 0x1audio-sdk-py
cd 0x1audio-sdk-py
uv sync --extra generate
```

`contract/` is the one source for the rules Mixel, the SDKs and the desktop share. Change it there, then run `uv run python contract/generate.py` to rewrite every generated file, including the copies in the sibling checkouts when they are there (`0x1audio-sdk-ts`, `0x1audio-cloud` and the official apps). `--only <part of a path>` keeps it to the files whose path has that text. Never edit a generated file by hand; each one says so at the top.

## Run the checks

Run these before you open a pull request:

```bash
uv run python -m unittest discover tests
uv run python contract/generate.py --check   # nothing drifted from the contract
uv run python scripts/openapi.py --check     # openapi.json and ox1audio.cloud against the cloud's spec
```

`openapi.json` is the developer part of the cloud's spec, and `src/ox1audio/cloud/` is generated from it: `uv run python scripts/openapi.py` rewrites both. The TypeScript SDK cuts the same file, byte for byte.

With Mixel open, `uv run python examples/smoke.py` runs the examples against the real thing. A change to what `ox1audio` exports or does gets a line in [CHANGELOG.md](CHANGELOG.md), under the next version.

## Pull requests

- Keep each pull request to one change, and say what changed and why.
- Add or update tests with the change.
- For anything on screen, add screenshots in light and dark.
- Sign off every commit (see below).

A maintainer reviews every pull request. We may ask for changes; that's normal, and it's about the code, never about you.

## Sign off your commits (DCO)

We use the [Developer Certificate of Origin](https://developercertificate.org) (DCO) instead of a contributor licence agreement. You keep the copyright on your work. By signing off, you confirm you have the right to contribute it.

Add `-s` when you commit:

```bash
git commit -s -m "Explain the change"
```

Git adds a line with your name and email from `git config`:

```text
Signed-off-by: Your Name <you@example.com>
```

Use your real name, or the name you're known by in open source. Forgot one? `git commit --amend -s` fixes the last commit, and `git rebase --signoff main` fixes every commit on your branch. Then force-push the branch.

<details>
<summary>The full DCO 1.1 text</summary>

```text
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.


Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

</details>

## Your contribution's licence

Everything you contribute is licensed under **Apache-2.0**, the same licence as the rest of this repository ([LICENSE](LICENSE)). There is no separate agreement and no relicensing.

## The bar

**Code.** Small and readable beats clever. Every change comes with its tests, the checks above pass, and no secrets go into the repository.

## The name

The code is open, and the name "Mixel" and its marks are protected so people know what's official. See the [trademark policy](https://0x1audio.com/trademarks).
