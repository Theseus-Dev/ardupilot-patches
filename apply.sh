#!/usr/bin/env bash
# Apply the theseus-ekf-patches series to an ArduPilot checkout.
#
# Usage:
#   ./apply.sh <ardupilot-dir> [<target-tag>]
#
# Examples:
#   ./apply.sh /path/to/ardupilot Plane-4.6.3
#   ./apply.sh /path/to/ardupilot                  # apply to current HEAD
set -euo pipefail

AP_DIR="${1:?usage: $0 <ardupilot-dir> [<target-tag>]}"
TARGET_TAG="${2:-}"

PATCH_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$AP_DIR"

if [[ -n "$TARGET_TAG" ]]; then
    echo ">> Checking out $TARGET_TAG"
    git checkout "$TARGET_TAG"
fi

BRANCH="theseus-cyclops-bootstrap-$(date +%Y%m%d-%H%M%S)"
echo ">> Creating branch $BRANCH"
git checkout -b "$BRANCH"

echo ">> Applying upstream backport patches"
for p in "$PATCH_ROOT/patches/01-upstream-backport/"*.patch; do
    echo "   - $(basename "$p")"
    git am --3way "$p"
done

echo ">> Applying cyclops bootstrap patches"
for p in "$PATCH_ROOT/patches/02-cyclops-bootstrap/"*.patch; do
    echo "   - $(basename "$p")"
    git am --3way "$p"
done

echo ">> Applying SITL no-GPS fix patches"
for p in "$PATCH_ROOT/patches/03-sitl-nogps-fixes/"*.patch; do
    echo "   - $(basename "$p")"
    git am --3way "$p"
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
