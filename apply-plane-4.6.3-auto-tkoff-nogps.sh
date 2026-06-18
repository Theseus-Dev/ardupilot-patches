#!/usr/bin/env bash
# Convenience wrapper for the Plane 4.6.3 AUTO-takeoff-without-GPS patchset.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$ROOT/patchsets/plane-4.6.3-auto-tkoff-nogps/apply.sh" "$@"
