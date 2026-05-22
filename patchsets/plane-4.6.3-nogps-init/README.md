# Plane 4.6.3 No-GPS Initialization Patchset

Patch series for Plane 4.6.3 that allows ArduPilot EKF3 to initialize and
produce a useful position estimate without GPS, using
`MAV_CMD_EXTERNAL_POSITION_ESTIMATE` (`43003`) from a companion computer
(e.g. Theseus Cyclops visual navigation).

This patchset is independent from
`../plane-4.3.8-mavlink-43003`. Plane 4.6.3 already has the MAVLink command;
this series changes EKF3 bootstrap behavior for no-GPS operation.

## What it does

Adds `EK3_OPTIONS` bit 3 (`ExtPosCanBootstrap`). When set:

1. `LOCAL_POSITION_NED` publishes from boot once `SET_GPS_GLOBAL_ORIGIN` has
   provided a valid origin, even while the EKF is in `AID_NONE`. This unblocks
   companion software that needs LPN to come up before it can produce its own
   fixes (eliminates the boot-time chicken-and-egg).

2. `MAV_CMD_EXTERNAL_POSITION_ESTIMATE` is allowed to transition the filter
   `AID_NONE → AID_ABSOLUTE` once the vehicle is in flight (`inFlight=true`).
   Gated on `inFlight` rather than just `!onGround` to avoid baking compass
   interference, pitot-cover effects, or pre-arm sensor states into the
   bootstrap.

3. Airspeed and synthetic-sideslip fusion are allowed to run after bootstrap
   even while EKF3's wind states are still inhibited (which they are until
   `|velocity_NED| > 5 m/s`). This breaks the chicken-and-egg gate where wind
   un-inhibition needs velocity and velocity needs airspeed/sideslip fusion.
   Wind learning resumes naturally once the velocity threshold is crossed.

4. The position pass time is kept fresh every cycle while in bootstrapped
   mode, so the EKF's internal `attAidLossCritical` / `posAidLossCritical`
   timeouts don't tear down `AID_ABSOLUTE` between companion fixes whose
   cadence exceeds the EKF's retry windows (~7–10 s).

The TAS innovation consistency gate is **not** bypassed — pitot failure
detection is preserved. If the airspeed sensor is reporting garbage, the
gate rejects it and the EKF's health flags reflect the degradation.

Default behaviour is unchanged unless `EK3_OPTIONS` bit 3 is set.

## Patch series

```
patchsets/plane-4.6.3-nogps-init/
  patches/
    01-upstream-ekf3-zero-velocity-backport/
                               # Master EKF3 ground/zero-vel hardening (PR #32396 + #32986)
      0001-AP_NavEKF3-use-onGroundNotMoving-for-zero-velocity-f.patch
      0002-AP_NavEKF3-inhibit-accel-bias-learning-when-on-groun.patch
      0003-AP_NavEKF3-clarify-position-noise-fallback-in-zero-v.patch
      0004-AP_NavEKF3-rename-onGroundNotFlying2-onGroundNotFlyi.patch
      0005-AP_NavEKF3-constrain-fusingStationaryZeroVel-to-not-.patch
      0006-AP_NavEKF3-gate-stationary-zero-velocity-fusion-on-i.patch
    02-external-position-bootstrap/
                               # New code for external-position bootstrap
      0001-AP_NavEKF3-external-position-bootstrap-for-AID_NONE-.patch
      0002-AP_NavEKF3-gate-TAS-and-sideslip-fusion-through-when.patch
    03-nogps-bootstrap-runtime-fixes/
                               # Close the chicken-and-egg gaps that
                               # prevented the 02 series from firing on a
                               # plane with no GPS from boot, plus the
                               # wind-anchor + ground-bootstrap fixes that
                               # let AUTO mission actually navigate.
                               # See RUNBOOK.md for the init procedure.
      0001-AP_NavEKF3-allow-init-without-GPS-lock-when-ExtPosCa.patch
      0002-AP_NavEKF3-keep-filter-healthy-and-wind-frozen-durin.patch
      0003-AP_NavEKF3-detect-inFlight-from-airspeed-and-baro-wh.patch
      0004-AP_NavEKF3-companion-driven-position-wind-ground-boo.patch
      0005-AP_NavEKF3-learn-wind-only-while-external-position-.patch
```

### What the 03 series fixes

Each fix is gated on `EK3_OPTIONS` bit 3 (`ExtPosCanBootstrap`); default
behaviour is unchanged for users without it.

1. **0001 (`AP_NavEKF3_core.cpp`)** — `InitialiseFilterBootstrap` refused
   to start the EKF on a plane without a 3D GPS fix, so `statesInitialised`
   stayed false forever. Allow init from IMU + compass alone when
   bootstrap is enabled.
2. **0002 (`AP_NavEKF3_Control.cpp`)** — `AP_AHRS::_active_EKF_type`
   (fixed-wing branch) selects DCM when EKF3 reports neither
   `horiz_pos_rel` nor `horiz_pos_abs` and `const_pos_mode` is set, which
   is exactly the EKF3 state while waiting for the in-air bootstrap. Force
   `horiz_vel`, `horiz_pos_rel`, `pred_horiz_pos_rel = true` and
   `const_pos_mode = false` while in bootstrap mode so AHRS keeps using
   EKF3 and `LOCAL_POSITION_NED` publishes from boot.
3. **0003 (`AP_NavEKF3_VehicleStatus.cpp`)** — `detectFlight` (plane
   branch) gates `inFlight` on GPS-derived `highGndSpd`, which is
   permanently false without GPS. Allow `inFlight` to latch on
   `highAirSpd && largeHgtChange` (airspeed > 10 m/s AND |baro hgt
   change| > 10 m) — two independent sensors, joint confirmation.
4. **0004 (`AP_NavEKF3_PosVelFusion.cpp`)** — `setLatLng`'s dead-reckon
   freshness gate is permanently closed by the AID_ABSOLUTE keepalive
   added in the 02 series, so only the first companion fix is accepted.
   Bypass the gate when `_has_forced_position` is set so subsequent
   fixes update position as the README intended.
5. **0005 (`AP_NavEKF3_Control.cpp`, `AP_NavEKF3_core.cpp`)** — allow
   wind learning only while external position fixes are fresh, then freeze
   wind again once fixes go stale. Preserve the wind covariance diagonal
   when wind is frozen so injected or learned wind is not logged as exact
   truth.

## How to apply

From a clean ArduPilot checkout at the target tag:

```sh
cd /path/to/ardupilot
/path/to/ardupilot-patches/patchsets/plane-4.6.3-nogps-init/apply.sh \
    /path/to/ardupilot Plane-4.6.3

git submodule update --init --recursive
./waf configure --board <your-board>
./waf plane
```

Manual application is also valid: apply each `*.patch` with `git am --3way`
in the three patch directories shown above, in numeric order.

## MAVLink flow

Expected sequence from a companion computer (e.g. Cyclops):

| Stage | Command | Effect |
|---|---|---|
| Boot | `SET_GPS_GLOBAL_ORIGIN` (lat/lon) | Sets `validOrigin`. EKF starts publishing `LOCAL_POSITION_NED` at origin (0,0 NE). Companion can now come up. |
| Pre-flight (ground) | none | EKF stays in `AID_NONE`. Companion fixes can initialise the forced-position bootstrap when configured. |
| Takeoff | (Plane vehicle code flips `inFlight=true`) | Bootstrap becomes available. |
| First fix post-takeoff | `MAV_CMD_EXTERNAL_POSITION_ESTIMATE` (43003) | Transitions to `AID_ABSOLUTE`. GCS message: `EKF3 IMUx aiding from external pos`. |
| Cruise | `MAV_CMD_EXTERNAL_POSITION_ESTIMATE` at companion cadence | Standard position resets. Velocity interpolated via TAS + sideslip + IMU between fixes. Wind can learn while fixes are fresh, then freezes once fixes go stale. |

## Parameter to set on the vehicle

```
EK3_OPTIONS = 8     # bit 3 = ExtPosCanBootstrap
```

## Targeted versions

| Branch | Status |
|---|---|
| Plane-4.6.3 | Verified — full series (01 + 02 + 03) applies clean, SITL Plane builds and the no-GPS-from-boot bootstrap flow passes end-to-end (see `RESULTS-sitl-nogps.md`) |
| Plane-4.5.x | Not yet tested |
| master | Not yet tested |

For Plane-4.5.x, expect more conflicts in the upstream EKF3 zero-velocity
backport series since the zero-velocity fusion infrastructure was added more
recently.

## Tradeoffs / known issues

- Wind state is learnable only while external position fixes are fresh. Once
  fixes go stale, wind is frozen again to avoid velocity/wind co-drift during
  pure no-GPS dead reckoning. The frozen wind covariance diagonal is preserved
  instead of being zeroed, so a held wind state is not represented as exact.
- The TAS innovation gate is preserved (not bypassed). Recovery from a stuck
  pitot eventually falls through to the existing `(tasTimeout && posTimeout)`
  fallback path, which forces fusion through after the timeouts age.
- `_has_forced_position` is a one-way flag: once set in a flight, it stays set
  until the next EKF init. If real GPS becomes available mid-flight, this
  patch does not clear the flag or revert to normal GPS-driven aiding.
- No interaction tested with optical flow, beacon, or external-nav sources.
  Behavior with those configured is undefined.

## Related upstream PRs

- [#32396](https://github.com/ArduPilot/ardupilot/pull/32396) — synthetic zero-velocity fusion (merged Apr 2026, master only)
- [#32986](https://github.com/ArduPilot/ardupilot/pull/32986) — `!inFlight` gate on zero-vel fusion (open, andyp1per's fork)
