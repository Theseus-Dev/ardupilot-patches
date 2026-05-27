# Plane 4.3.8 MAVLink 43003 And VNS Crosstrack Backport

Patchset for Plane 4.3.8 that adds
`MAV_CMD_EXTERNAL_POSITION_ESTIMATE` (`43003`) support and native handling for
the VNS crosstrack-start command (`MAV_CMD_WAYPOINT_USER_2`, `31001`).

This is a separate customer patchset from
`../plane-4.6.3-nogps-init`. It only backports the MAVLink command definition,
ArduPilot handlers, Replay plumbing, AHRS/EKF3/DAL forwarding, and the targeted
autotest from ArduPilot PR #23903. It also handles VNS crosstrack-start
`COMMAND_LONG` messages natively so Plane 4.3.8 does not need newer Lua
`require()` or scripting MAVLink bindings. It does not add the 4.6.3 no-GPS
bootstrap behavior or `EK3_OPTIONS` changes.

## Why This Is Minimal

The upstream PR changed the `modules/mavlink` submodule from a newer baseline
than Plane 4.3.8 uses. A direct submodule bump from Plane 4.3.8 would pull in
unrelated intermediate MAVLink changes, including message/enum changes outside
the requested command. This patchset avoids that by applying only the XML entry
for command `43003` to Plane 4.3.8's existing MAVLink submodule, then applying
the ArduPilot handler commits.

## Layout

```
patchsets/plane-4.3.8-mavlink-43003/
  apply.sh
  test-sitl.sh
  visual-map-test.sh
  patches/
    mavlink/
      0001-ardupilotmega-add-MAV_CMD_EXTERNAL_POSITION_ESTIMATE.patch
    ardupilot/
      0001-AP_DAL-Add-handlers-for-external-lat-lng-position-se.patch
      0002-AP_NavEKF3-Add-handlers-for-external-lat-lng-positio.patch
      0003-Tools-Replay-Add-handlers-for-external-lat-lng-posit.patch
      0004-Tools-autotest-Add-external-lat-lng-position-set-to-.patch
      0005-AP_AHRS-Add-handlers-for-external-lat-lng-position-s.patch
      0006-GCS_MAVLink-support-EXTERNAL_POSITION_ESTIMATE-comma.patch
      0007-Tools-added-test-for-MAV_CMD_EXTERNAL_POSITION_ESTIM.patch
      0008-ArduPlane-handle-VNS-crosstrack-start-command.patch
  overlays/
    visual-100km/
      0001-Tools-autotest-use-100km-offset-for-visual-43003-test.patch
```

## Apply

From this repository:

```sh
patchsets/plane-4.3.8-mavlink-43003/apply.sh /path/to/ardupilot Plane-4.3.8
```

Manual equivalent:

```sh
cd /path/to/ardupilot
git checkout Plane-4.3.8
git checkout -b plane-4.3.8-mavlink-43003
git submodule update --init --recursive modules/mavlink

for p in /path/to/ardupilot-patches/patchsets/plane-4.3.8-mavlink-43003/patches/mavlink/*.patch; do
    git -C modules/mavlink am --3way "$p"
done

for p in /path/to/ardupilot-patches/patchsets/plane-4.3.8-mavlink-43003/patches/ardupilot/*.patch; do
    git am --3way "$p"
done
```

## Build And Test

```sh
patchsets/plane-4.3.8-mavlink-43003/test-sitl.sh /path/to/ardupilot
```

Equivalent commands:

```sh
cd /path/to/ardupilot
./waf configure --board sitl
./waf plane
Tools/autotest/autotest.py --no-configure --no-clean --speedup=10 --timeout=1200 test.Plane.ExternalPositionEstimate
Tools/autotest/autotest.py --no-configure --no-clean --speedup=10 --timeout=1200 test.Plane.VNSCrosstrackStartCommand
```

The original `43003` backport was verified locally on the backport branch:

- `./waf plane` built `build/sitl/bin/arduplane`.
- `test.Plane.ExternalPositionEstimate` passed.
- The targeted test rejected command `43003` while GPS was active and accepted
  it after GPS was disabled.

The VNS crosstrack patch adds `test.Plane.VNSCrosstrackStartCommand` to verify
command `31001` is accepted once AHRS has a current position.

## Visual Validation

Use the optional visual overlay only for map confirmation:

```sh
patchsets/plane-4.3.8-mavlink-43003/visual-map-test.sh /path/to/ardupilot
```

That script temporarily applies `overlays/visual-100km`, runs the targeted
autotest with MAVProxy `--map` at real-time speed, and removes the overlay on
exit. The overlay changes only the autotest's accepted no-GPS command to inject
a 100 km north offset so the position reset is obvious on the map.
