"""openapi.json is the public part of the Mixel API, cut from the cloud's own spec; src/ox1audio/cloud is generated from it.

    uv run --extra generate python scripts/openapi.py            rewrite openapi.json, then src/ox1audio/cloud
    uv run --extra generate python scripts/openapi.py --check    exit 1 if either drifted (CI)
    uv run --extra generate python scripts/openapi.py path/to/openapi.yaml    another spec (or MIXEL_OPENAPI)

The spec is read from MIXEL_OPENAPI, or from a sibling checkout of the cloud repo
(../0x1audio-cloud/apps/api/openapi/openapi.yaml). Without one, --check still checks that
src/ox1audio/cloud is what openapi.json generates, and says the spec part was skipped.

The SDK is public; the cloud's spec also holds reviewer, admin, billing and webhook routes. Only the
operations in PUBLIC leave, with the schemas they use, and descriptions lose their pointers to
internal documents. sdk-ts cuts the same list (scripts/openapi.mjs) into a byte-identical file: change both.
"""

from __future__ import annotations

import filecmp
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDORED = ROOT / "openapi.json"
PACKAGE = ROOT / "src" / "ox1audio" / "cloud"

# operationId: what a developer, a script or an agent does with it.
PUBLIC = {
    "health": "Is the cloud up",
    "me": "Approved or waitlisted, and the Terms",
    "cliLogin": "Start a mixel sign-in (device flow)",
    "cliLoginPoll": "Finish it: the token, once",
    "cliTokens": "The command lines signed in",
    "revokeCliToken": "Sign one out",
    "appCatalog": "The reviewed apps",
    "createSubmission": "Submit an app for review",
    "submissions": "An app's submissions",
    "submission": "One submission",
}

DESCRIPTION = (
    "The Mixel cloud for developers: your account, signing in the mixel command line, and the reviewed app registry. "
    "Send the token from mixel login (or MIXEL_TOKEN) as Authorization: Bearer. Errors are {error: {code, message}}; "
    "refusals the command line prints also carry fix or doc_url."
)

# "(launch.md 1.4)", "(reports/ship/w1/…)", "(GAB-123)": pointers into documents only the team can read.
INTERNAL = re.compile(r"\s*\((?=[^()]*(?:\.md\b|reports/|GAB-\d))[^()]*\)")


def _scrub(value):
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, dict):
        return {key: INTERNAL.sub("", item) if key == "description" and isinstance(item, str) else _scrub(item) for key, item in value.items()}
    return value


def _refs(value, found: set[str] | None = None) -> set[str]:
    found = set() if found is None else found
    if isinstance(value, list):
        for item in value:
            _refs(item, found)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key == "$ref" and isinstance(item, str) and item.startswith("#/components/schemas/"):
                found.add(item[21:])
            else:
                _refs(item, found)
    return found


def cut(spec: dict) -> dict:
    paths: dict = {}
    missing = set(PUBLIC)
    for where, item in (spec.get("paths") or {}).items():
        kept = {}
        for method, operation in item.items():
            if isinstance(operation, dict) and operation.get("operationId") in PUBLIC:
                kept[method] = operation
                missing.discard(operation["operationId"])
        if kept:
            if "parameters" in item:
                kept["parameters"] = item["parameters"]
            paths[where] = kept
    if missing:
        raise SystemExit(f"The cloud's spec has no {', '.join(sorted(missing))}. Was it renamed? Update PUBLIC here and in sdk-ts.")
    every = (spec.get("components") or {}).get("schemas") or {}
    used = _refs(paths)
    queue = list(used)
    while queue:
        for name in _refs(every.get(queue.pop())):
            if name not in used:
                used.add(name)
                queue.append(name)
    info = {"title": "Mixel API", "version": (spec.get("info") or {}).get("version", "0.0.0")}
    if (spec.get("info") or {}).get("license") is not None:
        info["license"] = spec["info"]["license"]
    info["description"] = DESCRIPTION
    return _scrub({
        "openapi": spec.get("openapi"),
        "info": info,
        "servers": [{"url": "https://cloud.0x1audio.com"}],
        "paths": paths,
        "components": {"schemas": {name: schema for name, schema in every.items() if name in used}},
    })


def render(spec: dict) -> str:
    return json.dumps(spec, indent=2, ensure_ascii=False) + "\n"


def changes(before: dict, after: dict) -> list[str]:
    """What changed between two cut specs, by name: what a person needs to judge the drift."""

    def index(spec: dict) -> dict[str, str]:
        found = {}
        for where, item in (spec.get("paths") or {}).items():
            for method, operation in item.items():
                if isinstance(operation, dict) and operation.get("operationId"):
                    found[f"operation {operation['operationId']} ({method.upper()} {where})"] = json.dumps(operation, sort_keys=True)
        for name, schema in ((spec.get("components") or {}).get("schemas") or {}).items():
            found[f"schema {name}"] = json.dumps(schema, sort_keys=True)
        return found

    old, now = index(before), index(after)
    lines = [f"added    {name}" for name in now if name not in old]
    lines += [f"changed  {name}" for name in now if name in old and old[name] != now[name]]
    lines += [f"removed  {name}" for name in old if name not in now]
    return lines


def source(given: str | None) -> Path | None:
    for candidate in (given, os.environ.get("MIXEL_OPENAPI"), ROOT.parent / "0x1audio-cloud" / "apps" / "api" / "openapi" / "openapi.yaml"):
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def generate(into: Path) -> None:
    """src/ox1audio/cloud as openapi-python-client writes it from openapi.json, into ``into``."""
    with tempfile.TemporaryDirectory(prefix="mixel-cloud-") as scratch:
        out = Path(scratch) / "out"
        subprocess.run(
            [sys.executable, "-m", "openapi_python_client", "generate", "--path", str(VENDORED), "--config", str(ROOT / "openapi-python-client.yaml"),
             "--output-path", str(out), "--meta", "none", "--overwrite"],
            check=True, capture_output=True, text=True,
        )
        shutil.copytree(out, into, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", ".ruff_cache"))


def _files(folder: Path) -> set[str]:
    return {str(path.relative_to(folder)) for path in folder.rglob("*") if path.is_file() and "__pycache__" not in path.parts and ".ruff_cache" not in path.parts}


def stale_package() -> list[str]:
    with tempfile.TemporaryDirectory(prefix="mixel-cloud-want-") as scratch:
        want = Path(scratch)
        generate(want)
        names = _files(want) | _files(PACKAGE)
        return sorted(name for name in names if not (want / name).is_file() or not (PACKAGE / name).is_file() or not filecmp.cmp(want / name, PACKAGE / name, shallow=False))


def shown(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def main(args: list[str]) -> int:
    check = "--check" in args
    given = next((arg for arg in args if not arg.startswith("--")), None)
    spec_file = source(given)
    failed = False
    if spec_file is None:
        print("openapi.json: skipped, no cloud spec here (set MIXEL_OPENAPI, or check out 0x1audio-cloud beside this repo).")
    else:
        import yaml

        want = render(cut(yaml.safe_load(spec_file.read_text())))
        have = VENDORED.read_text() if VENDORED.is_file() else ""
        if want == have:
            print(f"openapi.json: up to date with {shown(spec_file)}.")
        elif check:
            failed = True
            print(f"openapi.json: behind {shown(spec_file)}.")
            for line in changes(json.loads(have) if have else {}, json.loads(want)):
                print(f"  {line}")
            print("fix: uv run --extra generate python scripts/openapi.py, then read the diff before you commit.")
        else:
            temporary = VENDORED.with_suffix(".json.tmp")
            temporary.write_text(want)
            temporary.replace(VENDORED)
            print(f"openapi.json: rewritten from {shown(spec_file)}.")
    if check:
        stale = stale_package()
        if stale:
            failed = True
            print(f"src/ox1audio/cloud: {len(stale)} file(s) differ from what openapi.json generates ({', '.join(stale[:3])}{', …' if len(stale) > 3 else ''}).")
            print("fix: uv run --extra generate python scripts/openapi.py")
        else:
            print("src/ox1audio/cloud: what openapi.json generates.")
    else:
        with tempfile.TemporaryDirectory(prefix="mixel-cloud-new-") as scratch:
            generate(Path(scratch))
            shutil.rmtree(PACKAGE)
            shutil.copytree(scratch, PACKAGE)
        print("src/ox1audio/cloud: generated from openapi.json.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
