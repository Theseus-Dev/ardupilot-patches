# Plane 4.6.3 No-GPS Init: SITL Verification

Date: 2026-05-13
Branch tested: `plane-4.6.3-nogps-init` (Plane-4.6.3 base + this patchset)
Repo tested: local ArduPilot checkout
Patchset: `patchsets/plane-4.6.3-nogps-init`

## Goal

Apply the patch series, build ArduPlane SITL, and verify the EKF can
initialise on the ground without GPS and transition to AID_ABSOLUTE once in
the air via `MAV_CMD_EXTERNAL_POSITION_ESTIMATE` (43003).

## Result

**PASS.** With the follow-on fixes documented below, on a fresh boot
with `SIM_GPS_DISABLE=1`, `GPS1_TYPE=0`, and `EK3_OPTIONS=8`:

- EKF3 initialises on the ground from IMU + compass alone (no GPS lock).
- `LOCAL_POSITION_NED` streams from boot at origin (0,0,0) once
  `SET_GPS_GLOBAL_ORIGIN` has been provided.
- AHRS reports `EKF3 active` (no fall-back to DCM) before takeoff.
- Plane arms in FBWA and climbs under throttle override.
- The first `MAV_CMD_EXTERNAL_POSITION_ESTIMATE` after takeoff transitions
  the filter to AID_ABSOLUTE; STATUSTEXT `EKF3 IMUx aiding from external pos`
  fires; EKF status flag `POS_HORIZ_ABS` is set.
- Subsequent fixes continue to update position (not rejected by the
  dead-reckon gate).

Test artifact: `/tmp/theseus-test/test_run10.log`.

## Gaps in the original patch series

The README claims this works out of the box once `EK3_OPTIONS=8` is set, but
on a fresh boot with no GPS, four chicken-and-egg issues prevented anything
from happening on a plane:

### 1. EKF3 refuses to initialise on a plane without GPS lock

`NavEKF3_core::InitialiseFilterBootstrap` had an unconditional early-return
for fly-forward vehicles missing a 3D GPS fix. Without filter init,
`statesInitialised` stayed false, `healthy()` reported a fault, and every
downstream flag (attitude, velocity, position) was cleared. The EKF reported
flag `0x0400` (EKF_UNINITIALIZED) the entire time the plane sat on the
runway. No origin could be set, no LPN published, no bootstrap path could
ever fire.

### 2. AHRS falls back to DCM in AID_NONE

`AP_AHRS::_active_EKF_type()` (fixed-wing branch) selects DCM whenever the
EKF reports `horiz_pos_rel=false` and `horiz_pos_abs=false`, which is
exactly the state EKF3 is in while waiting for the bootstrap. The patched
`getPosNE()` returned the origin position, but AHRS never asked for it
because it had already switched to DCM. As a result `LOCAL_POSITION_NED`
was never published on the ground.

### 3. `inFlight` detection requires GPS-derived ground speed

`NavEKF3_core::detectFlight()` (plane branch) requires `highGndSpd`
(`gpsDataNew.vel.x/y` > 5 m/s) before it will even consider `inFlight=true`.
Without GPS, those velocities are 0. So `inFlight` is permanently false,
and the bootstrap gate inside `setLatLng()` (which is gated on `inFlight`)
never opens — even at 30 m/s airspeed and 2000 m altitude.

### 4. After bootstrap, subsequent fixes are rejected

`setLatLng()` rejects calls when
`(imuSampleTime_ms - lastGpsPosPassTime_ms) < deadReckonDeclare_ms`. But the
patch's AID_ABSOLUTE keepalive (in `setAidingMode()`) refreshes
`lastGpsPosPassTime_ms` every cycle while `_has_forced_position` is set.
This made the freshness check always true, so every position update from
the companion after the bootstrap was rejected. Only the first fix made
it through. The README's "Cruise: ... Standard position resets" was not
actually happening.

## Changes made

All four changes are gated on `EK3_OPTIONS` bit 3 (`ExtPosCanBootstrap`) so
default behaviour for users without this option set is unchanged.

### `libraries/AP_NavEKF3/AP_NavEKF3_core.cpp` (Fix 1)

In `InitialiseFilterBootstrap()`, allow EKF init to proceed without a GPS
3D fix on a plane when `ExtPosCanBootstrap` is set:

```cpp
if (assume_zero_sideslip() && dal.gps().status(preferred_gps) < AP_DAL_GPS::GPS_OK_FIX_3D &&
    !(frontend->_options & (int32_t)NavEKF3::Options::ExtPosCanBootstrap)) {
    // ... existing "EKF3 init failure: No GPS lock" path ...
}
```

The EKF still initialises tilt from accel and yaw from compass; it just
doesn't refuse to start.

### `libraries/AP_NavEKF3/AP_NavEKF3_Control.cpp` (Fix 2)

At the end of `updateFilterStatus()`, after the regular flags have been
assigned, force the relative-aiding flags so AHRS doesn't fall back to DCM
before the bootstrap:

```cpp
if ((frontend->_options & (int32_t)NavEKF3::Options::ExtPosCanBootstrap) &&
    validOrigin && filterHealthy) {
    status.flags.horiz_vel = true;
    status.flags.horiz_pos_rel = true;
    status.flags.pred_horiz_pos_rel = true;
    status.flags.const_pos_mode = false;
}
```

Position reported during this window is the origin (held at 0,0 by AID_NONE
constant-position fusion). That's the same position the patched `getPosNE()`
was already prepared to return — this change just makes AHRS actually ask
for it.

### `libraries/AP_NavEKF3/AP_NavEKF3_VehicleStatus.cpp` (Fix 3)

In `detectFlight()` (plane branch), add a no-GPS fallback path for
`inFlight` detection:

```cpp
if (highGndSpd && (dal.get_takeoff_expected() || highAirSpd || largeHgtChange)) {
    inFlight = true;
} else if ((frontend->_options & (int32_t)NavEKF3::Options::ExtPosCanBootstrap) &&
           highAirSpd && largeHgtChange) {
    // No GPS available - require both airspeed > 10 m/s and >10 m of
    // baro height change as joint confirmation we are in the air.
    inFlight = true;
}
```

Both `highAirSpd` (airspeed > 10 m/s) and `largeHgtChange`
(`|hgtMea| > 10 m`) must hold — the conjunction is what guards against false
positives. The two signals are independent (pitot vs baro), so it takes a
genuine failure of both to declare flight wrongly.

### `libraries/AP_NavEKF3/AP_NavEKF3_PosVelFusion.cpp` (Fix 4)

In `setLatLng()`, bypass the dead-reckon freshness gate once
`_has_forced_position` is set:

```cpp
const bool deadReckonGate =
    !_has_forced_position &&
    (imuSampleTime_ms - lastGpsPosPassTime_ms) < frontend->deadReckonDeclare_ms;
if (deadReckonGate || ...) {
    return false;
}
```

The gate's intent is "don't override when fresh GPS is actively passing."
In bootstrap mode there is no GPS; the keepalive is simulating freshness
purely to keep AID_ABSOLUTE alive. Skipping the gate when `_has_forced_position`
is set lets the companion's fixes actually reset position again.

## SITL repro

Defaults file (layered on `Tools/autotest/models/plane.parm`):

```
EK3_OPTIONS    8        # bit 3 = ExtPosCanBootstrap
EK3_ENABLE     1
EK2_ENABLE     0
AHRS_EKF_TYPE  3
EK3_MAG_CAL    2
SIM_GPS_DISABLE 1
GPS1_TYPE      0
ARMING_CHECK   0
ARSPD_USE      1
EK3_SRC1_POSXY 0
EK3_SRC1_VELXY 0
EK3_SRC1_POSZ  1
EK3_SRC1_VELZ  0
```

Launch (sim_vehicle.py with mavproxy disabled or detached):

```sh
python3 Tools/autotest/sim_vehicle.py -v ArduPlane -f plane --speedup 10 \
    -w -L CMAC --add-param-file=/tmp/theseus-test/nogps.parm
```

Test driver: `/tmp/theseus-test/test_nogps_bootstrap.py`. Connect to
`tcp:127.0.0.1:5760`. The test:

1. Verifies `EK3_OPTIONS=8`, `GPS1_TYPE=0`, etc.
2. Sends `SET_GPS_GLOBAL_ORIGIN`; waits 12 s and counts LPN frames.
3. Sets FBWA, arms (force), drives throttle to 100 % and elevator nose-up.
4. After ~25 s of climb (alt > 2000 m, airspeed ~29 m/s) sends
   `MAV_CMD_EXTERNAL_POSITION_ESTIMATE` (lat ~1 km north of origin).
5. Looks for STATUSTEXT `EKF3 IMUx aiding from external pos` and
   `POS_HORIZ_ABS` in `EKF_STATUS_REPORT`.
6. Sends 5 more position fixes at 3 s spacing and verifies each is
   accepted.

## Final EKF state during the run

Before bootstrap (on ground, post-origin, pre-arm):
- `EKF_STATUS_REPORT.flags = 0x012f` — attitude, velocity, vert pos,
  horiz_pos_rel, pred_horiz_pos_rel set. No abs flags, no const_pos_mode.
- LPN streaming at ~117 Hz, x≈0, y≈0, z≈0.

After bootstrap (mid-flight, post-`setLatLng`):
- `EKF_STATUS_REPORT.flags = 0x033f` — same as above plus `POS_HORIZ_ABS`
  (0x010) and `PRED_POS_HORIZ_ABS` (0x200).
- LPN tracking position from bootstrap injection point.

## Caveats

- Subsequent `setLatLng` calls now succeed. The README warned that
  "_has_forced_position is a one-way flag" — that's still true, but Fix 4
  means the EKF actually does the position resets the README promised
  during cruise.
- I made no changes to AHRS, vehicle code, or pre-arm checks. The user
  still needs `ARMING_CHECK=0` (or specifically clear the GPS bit) and
  must disable any AHRS GPS check elsewhere if applicable.
- Test ran on macOS x86_64 (Rosetta on M1 Max) with `sim_vehicle.py` as the
  launcher (`run_in_terminal_window.sh` AppleScript path keeps SITL alive
  across the Bash tool's shell teardowns; raw `&` + `disown` from inside
  the Bash tool dies because of SITL's `kill(_parent_pid, 0)` watchdog).
- I did not exercise GPS-recovery-mid-flight or any optical-flow / beacon /
  ext-nav interactions; same caveats as the README.

## Files touched

| File | Lines added | Purpose |
|---|---|---|
| libraries/AP_NavEKF3/AP_NavEKF3_core.cpp | +6/-2 | Allow EKF init without GPS lock when bootstrap option set |
| libraries/AP_NavEKF3/AP_NavEKF3_Control.cpp | +15 | Suppress DCM fallback by forcing aiding flags |
| libraries/AP_NavEKF3/AP_NavEKF3_VehicleStatus.cpp | +6 | Allow inFlight detection from airspeed + height change |
| libraries/AP_NavEKF3/AP_NavEKF3_PosVelFusion.cpp | +9/-1 | Allow subsequent fixes after bootstrap |
