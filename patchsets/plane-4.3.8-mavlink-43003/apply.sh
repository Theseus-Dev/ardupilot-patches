#!/usr/bin/env bash
# Apply the Plane-4.3.8 MAV_CMD_EXTERNAL_POSITION_ESTIMATE backport.
#
# Usage:
#   ./apply.sh <ardupilot-dir> [<target-tag>]
#
# Examples:
#   ./apply.sh /path/to/ardupilot
#   ./apply.sh /path/to/ardupilot Plane-4.3.8
set -euo pipefail

AP_DIR="${1:?usage: $0 <ardupilot-dir> [<target-tag>]}"
TARGET_TAG="${2:-Plane-4.3.8}"
PATCH_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERIES_DIR="$PATCH_ROOT/patches"

cd "$AP_DIR"

echo ">> Checking out $TARGET_TAG"
git checkout "$TARGET_TAG"

BRANCH="plane-4.3.8-mavlink-43003-$(date +%Y%m%d-%H%M%S)"
echo ">> Creating branch $BRANCH"
git checkout -b "$BRANCH"

echo ">> Updating MAVLink submodule"
git submodule update --init --recursive modules/mavlink

echo ">> Applying MAVLink command definition patch inside modules/mavlink"
for p in "$SERIES_DIR/mavlink/"*.patch; do
    echo "   - $(basename "$p")"
    git -C modules/mavlink am --3way "$p"
done

echo ">> Applying ArduPilot handler patches"
for p in "$SERIES_DIR/ardupilot/"*.patch; do
    echo "   - $(basename "$p")"
    git am --3way "$p"
done

echo ""
echo "Done. Next steps:"
echo "  cd $AP_DIR"
echo "  ./waf configure --board <your-board>"
echo "  ./waf plane"
