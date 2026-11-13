"""Run an app: one action, on a real file, the way Mixel runs it. Then, if Mixel is open with
Settings › Developer mode on, open the app there too, badged "In development".

    python examples/run_app.py                      a new app from `mixel new`, on its own test tone
    python examples/run_app.py path/to/app ACTION path/to/song.wav
"""

import subprocess
import sys
import tempfile
from pathlib import Path

from ox1audio.local import Mixel, MixelError, MixelUnavailableError, run_app

with tempfile.TemporaryDirectory(prefix="mixel-example-") as scratch:
    if len(sys.argv) > 3:
        folder, action, song = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    else:
        subprocess.run([sys.executable, "-m", "ox1audio.cli", "new", "Make It Flac"], cwd=scratch, check=True, capture_output=True)
        folder, action = Path(scratch) / "make-it-flac", "convert"
        song = folder / "tests" / "tone.wav"
    try:
        run = run_app(folder, action, files=[song], input={"format": "flac"} if len(sys.argv) <= 3 else None, out=Path(scratch) / "out")
    except MixelError as error:
        raise SystemExit(f"{error.code}: {error.message}\nfix: {error.fix or '-'}") from None
    for item in run.items:
        print(f"Made {item['title']} ({item['kind']}): {Path(item['path']).name}")

    mixel = Mixel(caller="sdk example")
    try:
        app = mixel.open_app(folder)
    except MixelUnavailableError as error:
        print(f"Not opened in Mixel: {error.message} (fix: {error.fix})")
    except MixelError as error:
        raise SystemExit(f"{error.code}: {error.message}\nfix: {error.fix or '-'}") from None
    else:
        print(f"Opened {app.display_name} {app.version} in Mixel {mixel.status()['mixel']}.")
        for line in app.log(timeout=2):
            if line.get("text"):
                print(f"[{line['type']}] {line['text']}")
        app.close()
        print("Closed it.")
