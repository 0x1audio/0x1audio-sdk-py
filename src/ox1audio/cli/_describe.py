"""Loads an app's entry file with the app's own Python and prints its actions as JSON.

    python -m ox1audio.cli._describe ENTRY

``mixel check`` runs it, so actions load with the packages the app installs (its .venv),
not with whatever mixel itself runs on.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path


def main(argv: list[str]) -> int:
    report = sys.stdout
    sys.stdout = sys.stderr
    from ox1audio.cli.check import _load

    loaded, problem = _load(Path(argv[0]).resolve())
    body = {"finding": asdict(problem)} if problem else {"actions": [{"spec": item.spec(), "permissions": sorted(item.permissions())} for item in loaded]}
    report.write(json.dumps(body, default=str) + "\n")
    report.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
