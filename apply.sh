#!/usr/bin/env bash
# Dispatch to one of the independent patchset apply scripts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<'USAGE'
Usage:
  ./apply.sh <patchset> <ardupilot-dir> [target-tag]

Patchsets:
  plane-4.6.3-nogps-init
  plane-4.6.3-auto-tkoff-nogps
  plane-4.3.8-mavlink-43003

Examples:
  ./apply.sh plane-4.6.3-nogps-init /path/to/ardupilot Plane-4.6.3
  ./apply.sh plane-4.6.3-auto-tkoff-nogps /path/to/ardupilot Plane-4.6.3
  ./apply.sh plane-4.3.8-mavlink-43003 /path/to/ardupilot Plane-4.3.8
USAGE
}

if [[ $# -lt 2 ]]; then
    usage
    exit 2
fi

PATCHSET="$1"
shift

case "$PATCHSET" in
    plane-4.6.3-nogps-init)
        exec "$ROOT/patchsets/plane-4.6.3-nogps-init/apply.sh" "$@"
        ;;
    plane-4.6.3-auto-tkoff-nogps)
        exec "$ROOT/patchsets/plane-4.6.3-auto-tkoff-nogps/apply.sh" "$@"
        ;;
    plane-4.3.8-mavlink-43003)
        exec "$ROOT/patchsets/plane-4.3.8-mavlink-43003/apply.sh" "$@"
        ;;
    *)
        echo "Unknown patchset: $PATCHSET" >&2
        usage
        exit 2
        ;;
esac

