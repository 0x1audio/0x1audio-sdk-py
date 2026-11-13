## What changed, and why

<!-- One change per pull request. Link the issue if there is one: "Fixes #12". -->

## How you checked it

<!-- What you ran, and what you saw or heard. -->

## Before you ask for review

- [ ] Every commit is signed off (`git commit -s`), as CONTRIBUTING.md explains.
- [ ] Tests are added or updated with the change.
- [ ] `uv run python -m unittest discover tests` passes.
- [ ] `uv run python contract/generate.py --check` and `uv run python scripts/openapi.py --check` pass; no generated file was edited by hand.
- [ ] A change to what `ox1audio` exports or does has a line in `CHANGELOG.md`.
- [ ] Nothing an app written today relies on was renamed or removed. If it was: why, and what an app author does instead.
- [ ] No secrets, and no audio you don't have the right to share.
