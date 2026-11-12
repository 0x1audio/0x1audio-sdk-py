"""What your Mixel Library holds, in counts: python examples/library.py"""

from ox1audio.local import Mixel, MixelError

try:
    library = Mixel(caller="sdk example").overview()
except MixelError as error:
    raise SystemExit(f"{error.message}\nfix: {error.fix or '-'}") from None

print(f"{library.sounds} sounds")
for concept, count in library.concepts.items():
    print(f"  {concept:<16} {count}")
if library.more:
    print(f"  and {library.more} more kinds")
