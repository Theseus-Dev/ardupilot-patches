#!/usr/bin/env bash
# Run the targeted Plane test with MAVProxy map and a temporary 100 km visual offset.
set -euo pipefail

AP_DIR="${1:?usage: $0 <ardupilot-dir>}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OVERLAY="$ROOT/overlays/visual-100km/0001-Tools-autotest-use-100km-offset-for-visual-43003-test.patch"

cd "$AP_DIR"

if ! git diff --quiet -- Tools/autotest/arduplane.py; then
    echo "Tools/autotest/arduplane.py already has local changes; refusing to apply visual overlay." >&2
    exit 1
fi

echo ">> Applying temporary visual overlay: 100 km external-position offset"
git apply "$OVERLAY"

cleanup() {
    if git apply --reverse --check "$OVERLAY" >/dev/null 2>&1; then
        echo ">> Removing temporary visual overlay"
        git apply --reverse "$OVERLAY"
    fi
}
trap cleanup EXIT

echo ">> Run targeted Plane SITL test with MAVProxy map"
Tools/autotest/autotest.py \
    --map \
    --no-configure \
    --no-clean \
    --speedup=1 \
    --timeout=1600 \
    test.Plane.ExternalPositionEstimate

