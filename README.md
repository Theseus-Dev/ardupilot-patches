# theseus-ekf-patches

Patch series that allows the ArduPilot EKF3 to initialize and produce a
useful position estimate without GPS, using `MAV_CMD_EXTERNAL_POSITION_ESTIMATE`
(43003) from a companion computer (e.g. Theseus Cyclops visual navigation).

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
patches/
  01-upstream-backport/        # Master EKF3 ground/zero-vel hardening (PR #32396 + #32986)
    0001-AP_NavEKF3-use-onGroundNotMoving-for-zero-velocity-f.patch
    0002-AP_NavEKF3-inhibit-accel-bias-learning-when-on-groun.patch
    0003-AP_NavEKF3-clarify-position-noise-fallback-in-zero-v.patch
    0004-AP_NavEKF3-rename-onGroundNotFlying2-onGroundNotFlyi.patch
    0005-AP_NavEKF3-constrain-fusingStationaryZeroVel-to-not-.patch
    0006-AP_NavEKF3-gate-stationary-zero-velocity-fusion-on-i.patch
  02-cyclops-bootstrap/        # New code for external-position bootstrap
    0001-AP_NavEKF3-external-position-bootstrap-for-AID_NONE-.patch
    0002-AP_NavEKF3-gate-TAS-and-sideslip-fusion-through-when.patch
  03-sitl-nogps-fixes/         # Close the chicken-and-egg gaps that
                               # prevented the 02 series from firing on a
                               # plane with no GPS from boot, plus the
                               # wind-anchor + ground-bootstrap fixes that
                               # let AUTO mission actually navigate.
                               # See RUNBOOK.md for the init procedure.
    0001-AP_NavEKF3-allow-init-without-GPS-lock-when-ExtPosCa.patch
    0002-AP_NavEKF3-report-relative-aiding-flags-during-exter.patch
    0003-AP_NavEKF3-detect-inFlight-from-airspeed-and-baro-wh.patch
    0004-AP_NavEKF3-bypass-setLatLng-dead-reckon-gate-after-e.patch
    0005-AP_NavEKF3-disable-wind-learning-while-_has_forced_p.patch
    0006-AP_NavEKF3-companion-supplied-wind-ground-bootstrap-.patch
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

## How to apply

From a clean ArduPilot checkout at the target tag:

```sh
cd /path/to/ardupilot
git checkout Plane-4.6.3
git checkout -b theseus-cyclops-bootstrap

for p in /path/to/theseus-ekf-patches/patches/01-upstream-backport/*.patch; do
    git am --3way "$p"
done
for p in /path/to/theseus-ekf-patches/patches/02-cyclops-bootstrap/*.patch; do
    git am --3way "$p"
done
for p in /path/to/theseus-ekf-patches/patches/03-sitl-nogps-fixes/*.patch; do
    git am --3way "$p"
done

git submodule update --init --recursive
./waf configure --board <your-board>
./waf plane
```

## MAVLink flow

Expected sequence from a companion computer (e.g. Cyclops):

| Stage | Command | Effect |
|---|---|---|
| Boot | `SET_GPS_GLOBAL_ORIGIN` (lat/lon) | Sets `validOrigin`. EKF starts publishing `LOCAL_POSITION_NED` at origin (0,0 NE). Companion can now come up. |
| Pre-flight (ground) | none | EKF stays in `AID_NONE`. Companion fixes (if sent) are rejected. |
| Takeoff | (Plane vehicle code flips `inFlight=true`) | Bootstrap becomes available. |
| First fix post-takeoff | `MAV_CMD_EXTERNAL_POSITION_ESTIMATE` (43003) | Transitions to `AID_ABSOLUTE`. GCS message: `EKF3 IMUx aiding from external pos`. |
| Cruise | `MAV_CMD_EXTERNAL_POSITION_ESTIMATE` at companion cadence | Standard position resets. Velocity interpolated via TAS + sideslip + IMU between fixes. |

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

For Plane-4.5.x, expect more conflicts in the upstream-backport series since
the zero-velocity fusion infrastructure was added more recently.

## Tradeoffs / known issues

- Wind state is **not** frozen — it learns naturally once `|velocity| > 5 m/s`.
  This adds wind-shift adaptivity at the cost of some bias-absorption risk
  between fixes. For typical 500m / ~20s fix cadence, the absorbed drift is
  bounded.
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
