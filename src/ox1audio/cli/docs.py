"""mixel docs [TOPIC]: the docs, offline, from the same contract as the site. ``--list`` shows the topics."""

from __future__ import annotations

from pathlib import Path

from ox1audio.cli import out
from ox1audio.cli.out import OK, Stop

FOLDER = Path(__file__).resolve().parents[1] / "docs"
DOCS_PREFIX = "https://docs.0x1audio.com/"


def topics() -> dict[str, str]:
    """slug -> first heading, for every page shipped with the SDK."""
    found = {}
    for path in sorted(FOLDER.glob("*.md")):
        if path.stem == "digest":
            continue
        first = next((line.lstrip("# ").strip() for line in path.read_text().splitlines() if line.startswith("#")), path.stem)
        found[path.stem] = first
    return found


# The docs site's pages that live inside another page offline (error links say "actions#…").
ALIASES = {"actions": "agents", "page": "agents", "start": "agents", "app-json": "app-json", "sdk": "app-json", "v1": "app-json", "fields": "app-json", "network": "permissions", "publish": "cli"}


def read(slug: str) -> str:
    slug = slug.split("#", 1)[0].removeprefix(DOCS_PREFIX).strip("/")
    slug = ALIASES.get(slug, slug)
    path = FOLDER / f"{slug}.md"
    if not path.is_file():
        names = ", ".join(topics()) or "none"
        raise Stop(f"There is no docs page called {slug}.", fix=f"mixel docs {next(iter(topics()), 'agents')}   (topics: {names})", error="no_such_topic")
    return path.read_text()


def command(args: list[str]) -> int:
    rest = [arg for arg in args if not arg.startswith("--")]
    if "--list" in args or not rest:
        found = topics()
        if "--json" in args:
            out.emit([{"slug": slug, "title": title} for slug, title in found.items()])
            return OK
        width = max((len(slug) for slug in found), default=0)
        for slug, title in found.items():
            print(f"  {slug.ljust(width)}  {title}")
        print("\nmixel docs TOPIC prints one.")
        return OK
    text = read(rest[0])
    if "--json" in args:
        out.emit({"slug": rest[0], "markdown": text})
    else:
        print(text, end="" if text.endswith("\n") else "\n")
    return OK
