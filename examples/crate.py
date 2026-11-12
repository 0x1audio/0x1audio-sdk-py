"""Hand yourself a crate of sounds to audition in Mixel: python examples/crate.py snare

Nothing is moved, tagged or copied. Needs Settings › Your assistant › It can propose crates.
"""

import sys

from ox1audio.local import Mixel, MixelError

want = sys.argv[1] if len(sys.argv) > 1 else "snare"
mixel = Mixel(caller="sdk example")
try:
    found = mixel.search(want)
    if not found.answerable:
        raise SystemExit(f'Nothing in the Library is proven to be "{want}".\nfix: try other words')
    crate = mixel.propose_crate(f"From a script: {want}"[:40], want, [sound.id for sound in found])
except MixelError as error:
    raise SystemExit(f"{error.message}\nfix: {error.fix or '-'}") from None
print(f"Proposed a crate of {crate['sounds']} sounds. It's in Mixel, under From your assistant.")
