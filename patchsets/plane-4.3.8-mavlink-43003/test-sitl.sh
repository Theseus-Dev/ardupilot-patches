#!/usr/bin/env bash
# Build Plane SITL and run the targeted MAVLink command tests.
set -euo pipefail

AP_DIR="${1:?usage: $0 <ardupilot-dir>}"

cd "$AP_DIR"

echo ">> Configure SITL"
./waf configure --board sitl

echo ">> Build Plane SITL"
./waf plane

echo ">> Run targeted Plane SITL test"
Tools/autotest/autotest.py \
    --no-configure \
    --no-clean \
    --speedup=10 \
    --timeout=1200 \
    test.Plane.ExternalPositionEstimate \
    test.Plane.VNSCrosstrackStartCommand
