"""``python -m ox1audio app.py`` loads the app and serves its actions over stdin and stdout."""

import sys

from ox1audio.app import main

if len(sys.argv) != 2:
    print("usage: python -m ox1audio app.py   (0x1audio runs this for you; to try an action use ox.test)", file=sys.stderr)
    raise SystemExit(2)
raise SystemExit(main(sys.argv[1]))
