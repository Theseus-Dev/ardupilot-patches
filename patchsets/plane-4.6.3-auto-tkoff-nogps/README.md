# Plane 4.6.3 AUTO Takeoff Without GPS

Single-commit patch for Plane 4.6.3 that lets an AUTO `NAV_TAKEOFF`
proceed without a GPS 3D fix, gated behind a new `FLIGHT_OPTIONS` bit.

This patchset is **independent** of `../plane-4.6.3-nogps-init`. It does
not touch the EKF and does not bootstrap a position estimate — it only
relaxes the one vehicle-code gate that blocks AUTO launch when there is
no GPS lock. Pair it with whatever supplies position after launch (e.g.
the `plane-4.6.3-nogps-init` EKF bootstrap, or a companion feeding
`MAV_CMD_EXTERNAL_POSITION_ESTIMATE` once airborne).

## Motivation

FBWA launch without GPS already works (pilot controls throttle). AUTO
takeoff does not, because the launch detector hard-blocks on GPS:

```cpp
// ArduPlane/takeoff.cpp  Plane::auto_takeoff_check()
if (gps.status() < AP_GPS::GPS_OK_FIX_3D) {
    // no auto takeoff without GPS lock
    return false;
}
```

Without a 3D fix this returns false every cycle, so `suppress_throttle()`
never unsuppresses the motor and the launch never triggers.

## What it does

Adds `FlightOptions::ALLOW_AUTO_TKOFF_NO_GPS` = `FLIGHT_OPTIONS` bit 15
(`32768`). When set, the GPS 3D-fix early-return in `auto_takeoff_check()`
is skipped. Launch is then detected from the existing, GPS-independent
logic:

- **Acceleration trigger** — `TKOFF_THR_MINACC` against TECS forward
  acceleration (IMU-derived). Set this for hand/catapult launches.
- **Launch timer** — `TKOFF_THR_DELAY`.
- **Ground-speed term** — satisfied without GPS when
  `TKOFF_THR_MINSPD = 0` (the default), via the existing `is_zero()`
  branch.

`verify_takeoff()` is **not** changed. Without a GPS course lock it
already falls back to `nav_controller->update_level_flight()`, giving a
**wings-level climb** on the current heading until the takeoff altitude
(baro-relative) is reached. That is the correct no-GPS behaviour; the
companion takes over navigation once airborne.

Default behaviour is unchanged when the bit is clear.

## Scope (what is NOT changed)

- **EKF / position estimate** — untouched. You still need a position
  source after launch for the rest of the mission.
- **Arming checks** — unchanged. Clear the GPS bit in `ARMING_CHECK`
  (or set `ARMING_CHECK=0`) as you already do for FBWA no-GPS launch.
- **Home** — the AUTO mission only advances once `home_is_set()`; set
  home via `MAV_CMD_DO_SET_HOME` / `SET_GPS_GLOBAL_ORIGIN` before arming.
- **Attitude** — AHRS must still produce a usable attitude (DCM or EKF);
  this patch does not affect that.

## Files touched

| File | Change |
|---|---|
| `ArduPlane/defines.h` | add `ALLOW_AUTO_TKOFF_NO_GPS = (1<<15)` to `FlightOptions` |
| `ArduPlane/takeoff.cpp` | gate the GPS 3D-fix return on the new bit |
| `ArduPlane/Parameters.cpp` | document bit 15 in the `FLIGHT_OPTIONS` bitmask |

## Parameter to set on the vehicle

```
FLIGHT_OPTIONS  32768     # bit 15 = ALLOW_AUTO_TKOFF_NO_GPS
TKOFF_THR_MINSPD 0        # default; launch trigger does not need GPS speed
TKOFF_THR_MINACC <n>      # e.g. 15 for a hand launch (accel-based trigger)
```

OR-in `32768` if you already use other `FLIGHT_OPTIONS` bits.

## How to apply

From a clean ArduPilot checkout at the target tag:

```sh
cd /path/to/ardupilot
/path/to/ardupilot-patches/patchsets/plane-4.6.3-auto-tkoff-nogps/apply.sh \
    /path/to/ardupilot Plane-4.6.3

git submodule update --init --recursive
./waf configure --board <your-board>
./waf plane
```

Manual application is also valid: `git am --3way` the patch in
`patches/ardupilot/`.

## Targeted versions

| Branch | Status |
|---|---|
| Plane-4.6.3 | Verified — applies clean, SITL builds, and the no-GPS AUTO-takeoff behaviour passes (bit clear → no launch, bit set → launch). CubeOrangePlus firmware also builds. See `RESULTS-sitl.md`. |

The same one-line gate exists in older Plane (e.g. 4.3.8) but uses the
`g2.flight_options & FlightOptions::...` form rather than
`flight_option_enabled()`; this patch is written for the 4.6.3 source and
will not apply unmodified to 4.3.8.

## Tradeoffs / known issues

- With the bit set, AUTO launch will trigger on acceleration alone — make
  sure `TKOFF_THR_MINACC` (and `TKOFF_ACCEL_CNT` if used) are tuned so a
  bump on the ground does not arm the launch.
- The takeoff attitude check (`FLIGHT_OPTIONS` bit 2) is independent and
  still active unless you also disable it.
- Attitude during the no-GPS climb is DCM-derived (EKF3 has no position
  source). This patch does not change AHRS; supply position after launch for
  the rest of the mission.
- Verified in SITL (`RESULTS-sitl.md`); not yet flown on hardware.
