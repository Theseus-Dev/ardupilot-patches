#!/usr/bin/env bash
# Apply the Plane 4.6.3 no-GPS initialization patchset.
#
# Usage:
#   ./apply.sh <ardupilot-dir> [<target-tag>]
#
# Examples:
#   ./apply.sh /path/to/ardupilot Plane-4.6.3
#   ./apply.sh /path/to/ardupilot                  # defaults to Plane-4.6.3
set -euo pipefail

AP_DIR="${1:?usage: $0 <ardupilot-dir> [<target-tag>]}"
TARGET_TAG="${2:-Plane-4.6.3}"

PATCH_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$AP_DIR"

echo ">> Checking out $TARGET_TAG"
git checkout "$TARGET_TAG"

BRANCH="plane-4.6.3-nogps-init-$(date +%Y%m%d-%H%M%S)"
echo ">> Creating branch $BRANCH"
git checkout -b "$BRANCH"

for dir in \
    "$PATCH_ROOT/patches/01-upstream-ekf3-zero-velocity-backport" \
    "$PATCH_ROOT/patches/02-external-position-bootstrap" \
    "$PATCH_ROOT/patches/03-nogps-bootstrap-runtime-fixes"
do
    echo ">> Applying $(basename "$dir")"
    for p in "$dir/"*.patch; do
        echo "   - $(basename "$p")"
        git am --3way "$p"
    done
done

total_patches=$(find "$PATCH_ROOT/patches" -name '*.patch' | wc -l | tr -d ' ')
echo ""
echo "Done. Commits added on top of $(git rev-parse --short HEAD~${total_patches})..HEAD:"
git log --oneline "HEAD~${total_patches}..HEAD"
echo ""
echo "Next steps:"
echo "  cd $AP_DIR"
echo "  git submodule update --init --recursive"
echo "  ./waf configure --board <your-board>"
echo "  ./waf plane"
