#!/bin/sh
# The first five minutes, with only the installed package: a new app, checked, tested and run.
# CI runs it against the built wheel; run it yourself in any environment that has ox1audio.
set -eu
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"
mixel new "Make It Flac"
cd make-it-flac
mixel check --strict
mixel test
mixel run convert --file tests/tone.wav --set format=flac --out out
test -s out/tone.flac
python -c "import ox1audio, ox1audio.local, ox1audio.api, ox1audio.errors; print('ox1audio', ox1audio.__version__, 'ok')"
