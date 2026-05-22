#!/usr/bin/env bash
# Convenience wrapper for the Plane 4.3.8 MAVLink 43003 backport patchset.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$ROOT/patchsets/plane-4.3.8-mavlink-43003/apply.sh" "$@"

