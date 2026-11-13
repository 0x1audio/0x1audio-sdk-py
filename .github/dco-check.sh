#!/bin/sh
# Checks that every commit in BASE..HEAD is signed off by its author.
#   sh .github/dco-check.sh origin/main HEAD
# Merge commits are skipped. A sign-off counts when its email is the commit
# author's, in any letter case.
set -eu

base="${1:?usage: dco-check.sh BASE HEAD}"
head="${2:-HEAD}"
bad=0

for commit in $(git rev-list --no-merges "$base..$head"); do
  author=$(git log -1 --format='%ae' "$commit" | tr '[:upper:]' '[:lower:]')
  signed=$(git log -1 --format='%(trailers:key=Signed-off-by,valueonly)' "$commit" | tr '[:upper:]' '[:lower:]')
  case "$signed" in
    *"<$author>"*) ;;
    *)
      bad=1
      echo "Not signed off by its author: $(git log -1 --format='%h %s' "$commit")"
      ;;
  esac
done

if [ "$bad" -ne 0 ]; then
  echo
  echo "fix: git rebase --signoff $base, then push the branch again with --force-with-lease."
  echo "docs: CONTRIBUTING.md, \"Sign off your commits (DCO)\"."
  exit 1
fi
echo "Every commit is signed off."
