"""Search your own sounds by words, then find more like the first one:

    python examples/search.py snare --avoid clap
"""

import sys

from ox1audio.local import Mixel, MixelError

args = sys.argv[1:]
want = args[0] if args and not args[0].startswith("--") else "snare"
avoid = [args[at + 1] for at, arg in enumerate(args[:-1]) if arg == "--avoid"]
mixel = Mixel(caller="sdk example")
try:
    found = mixel.search(want, avoid=avoid)
    if not found.answerable:
        print(f'Nothing in the Library is proven to be "{want}". Nearest: {", ".join(found.nearest) or "none"}')
    else:
        for sound in found:
            print(f"{sound.id:<5} {sound.title:<32} {sound.tier or '-'}: {sound.reason}")
        if found.more:
            print(f"and {found.more} more")
        first = found.sounds[0]
        try:
            like = mixel.similar(first.id)
            print(f"\nLike {first.title}: {', '.join(sound.title for sound in like) or 'nothing close'}")
        except MixelError as error:
            # Sounds like this one need Mixel's sound model; words work without it.
            if error.code != "not_ready":
                raise
            print(f"\nLike {first.title}: {error.message}")
    # What to hand a model: Mixel's compact reply, not the objects above.
    print(f"\nFor a model ({len(found.text)} bytes): {found.text}")
except MixelError as error:
    raise SystemExit(f"{error.message}\nfix: {error.fix or '-'}") from None
