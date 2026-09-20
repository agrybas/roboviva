#!/usr/bin/env bash
# Pre-fetch the large Debian packages the oracle image needs.
#
# texlive-fonts-extra is a 513MB download that supplies exactly three style
# files the cue sheet preamble loads (latex.py:176-177):
#   fourier -> \danger      bbding -> \Plus      ifsym[alpine] -> \Mountain
#
# On a slow link that download regularly outlives a build attempt, and a failed
# `docker build` throws away the partial download every time. Fetching it here
# with a resumable request means an interrupted run picks up where it left off.
# Re-running when the file is already complete is a no-op.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CACHE="$HERE/.debcache"
mkdir -p "$CACHE"

DEB="texlive-fonts-extra_2020.20210202-3_all.deb"
URL="http://deb.debian.org/debian/pool/main/t/texlive-extra/$DEB"
EXPECTED_BYTES=513031872

target="$CACHE/$DEB"
attempt=0
while true; do
  if [[ -f "$target" ]]; then
    have=$(stat -c%s "$target")
    if [[ "$have" -eq "$EXPECTED_BYTES" ]]; then
      echo "$DEB complete ($have bytes)"
      break
    fi
    echo "resuming $DEB at $((have / 1048576))MB of $((EXPECTED_BYTES / 1048576))MB"
  fi
  attempt=$((attempt + 1))
  if [[ "$attempt" -gt 20 ]]; then
    echo "giving up after $attempt attempts" >&2
    exit 1
  fi
  # --continue-at - resumes; a dropped connection costs only the current chunk.
  curl -fSL --continue-at - --retry 5 --retry-delay 2 -o "$target" "$URL" || true
done

# A truncated .deb fails confusingly deep inside apt, so check it here.
if command -v dpkg-deb >/dev/null 2>&1; then
  dpkg-deb --info "$target" >/dev/null && echo "archive validates"
elif command -v ar >/dev/null 2>&1; then
  ar t "$target" >/dev/null && echo "archive structure OK"
fi
