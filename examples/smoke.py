"""Runs every example against the Mixel on this computer and prints one line each.

    uv run python examples/smoke.py            Mixel open, "Let an assistant search your Library" on
    uv run python examples/smoke.py --strict   a skipped example fails the run

MIXEL_DATA_DIR points it at another Mixel data folder (a test profile). An example is skipped, with
the fix, when the part of Mixel it needs isn't on; it fails when it runs and goes wrong.
run_app.py always runs: it needs no Mixel, and opens the app there only in developer mode.
"""

import subprocess
import sys
import time
from pathlib import Path

from ox1audio.local import Mixel, MixelUnavailableError

HERE = Path(__file__).resolve().parent
strict = "--strict" in sys.argv
mixel = Mixel(caller="sdk smoke", retries=0)


def needs(probe) -> str | None:
    try:
        probe()
    except MixelUnavailableError as error:
        return f"{error.message} fix: {error.fix}"
    return None


library = needs(mixel.overview)
runs = [("library.py", [], library), ("search.py", ["snare"], library), ("crate.py", ["snare"], library), ("run_app.py", [], None), ("cloud.py", [], None)]
failed = 0
for file, extra, skip in runs:
    if skip:
        failed += strict
        print(f"skip  {file:<12} {skip}")
        continue
    started = time.monotonic()
    run = subprocess.run([sys.executable, str(HERE / file), *extra], capture_output=True, text=True, timeout=120)
    ms = round((time.monotonic() - started) * 1000)
    first = ((run.stdout if run.returncode == 0 else run.stderr or run.stdout).strip().splitlines() or [""])[0]
    if run.returncode == 0:
        print(f"ok    {file:<12} {ms:>5} ms  {first}")
    else:
        failed += 1
        print(f"FAIL  {file:<12} {ms:>5} ms  {first}")
        print("\n".join(f"      {line}" for line in (run.stderr or run.stdout).strip().splitlines()))
sys.exit(1 if failed else 0)
