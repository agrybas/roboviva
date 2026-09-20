#!/usr/bin/env bash
# Driver for the legacy oracle container.
#
#   run.sh build      build the pinned python2 + TeX Live image
#   run.sh generate   run the corpus through the legacy code -> harness/golden/
#   run.sh verify     regenerate into a temp dir and diff against the committed
#                     goldens; non-zero exit means they are not reproducible
#   run.sh shell      interactive shell in the image, for poking at the legacy code
#   run.sh bridge     stdio bridge (what `pytest --sut=legacy` drives)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARNESS="$(cd "$HERE/.." && pwd)"
REPO="$(cd "$HARNESS/.." && pwd)"
IMAGE="${ROBOVIVA_ORACLE_IMAGE:-roboviva-oracle:latest}"

# --network none: the oracle must never reach RideWithGPS. Fixtures are
# recorded deliberately by harness/oracle/record_fixtures.py, on the host.
#
# --security-opt label=disable: on SELinux hosts (Fedora, RHEL) the container
# cannot read a plain bind mount. The usual fix is a ':z' mount flag, but that
# RELABELS the user's working tree on the host; disabling the label check for
# this throwaway container leaves the repo untouched.
docker_run() {
  local mount_mode="$1"; shift
  docker run --rm -i \
    --network none \
    --security-opt label=disable \
    --user "$(id -u):$(id -g)" \
    -v "$REPO:/repo:$mount_mode" \
    -w /repo \
    -e HOME=/tmp \
    -e PYTHONHASHSEED=0 \
    -e SOURCE_DATE_EPOCH=0 \
    -e FORCE_SOURCE_DATE=1 \
    "$IMAGE" -c "$*"
}

cmd="${1:-}"
case "$cmd" in
  build)
    docker build --progress=plain -t "$IMAGE" "$HERE"
    ;;

  generate)
    docker_run rw "python2 /repo/harness/oracle/generate.py /repo/harness/golden"
    ;;

  verify)
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    # Regenerate into a scratch dir the container can write to, then compare.
    docker run --rm -i \
      --network none \
      --security-opt label=disable \
      --user "$(id -u):$(id -g)" \
      -v "$REPO:/repo:ro" \
      -v "$tmp:/out:rw" \
      -w /repo \
      -e HOME=/tmp \
      -e PYTHONHASHSEED=0 -e SOURCE_DATE_EPOCH=0 -e FORCE_SOURCE_DATE=1 \
      "$IMAGE" -c "python2 /repo/harness/oracle/generate.py /out"
    if diff -ru "$HARNESS/golden" "$tmp"; then
      echo "goldens are reproducible"
    else
      echo "GOLDENS DRIFTED -- the legacy code or the toolchain changed" >&2
      exit 1
    fi
    ;;

  shell)
    docker run --rm -it --network none -v "$REPO:/repo:rw" -w /repo "$IMAGE"
    ;;

  bridge)
    docker_run ro "exec python2 /repo/harness/oracle/bridge.py"
    ;;

  *)
    sed -n '2,10p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'
    exit 1
    ;;
esac
