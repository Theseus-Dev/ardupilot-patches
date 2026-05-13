# No-GPS bootstrap — initialization procedure

The five-step sequence verified in SITL.

## Vehicle params (one time)

```
EK3_OPTIONS    8        # bit 3 = ExtPosCanBootstrap (master switch)
EK3_ENABLE     1
EK2_ENABLE     0
AHRS_EKF_TYPE  3
GPS1_TYPE      0        # if you have no GPS hardware at all
EK3_SRC1_POSXY 0        # NONE — EKF won't expect GPS for horiz pos
EK3_SRC1_VELXY 0        # NONE — EKF won't expect GPS for horiz vel
EK3_SRC1_POSZ  1        # BARO (default)
EK3_SRC1_VELZ  0        # NONE
ARSPD_USE      1        # required: inFlight detection uses airspeed
ARMING_CHECK   0        # or clear the GPS-required bits
```

## Companion sequence

```
ON GROUND, BEFORE ARM:

  1. SET_GPS_GLOBAL_ORIGIN(lat, lon, alt)
     → EKF gets a reference frame  (validOrigin = true)

  2. MAV_CMD_DO_SET_HOME(lat, lon, alt)
     → AHRS gets home              (required for AUTO mission to run)

  3. MAV_CMD_EXTERNAL_POSITION_ESTIMATE  (43003)  lat, lon
     → EKF: AID_NONE → AID_ABSOLUTE
     → position state set
     → STATUSTEXT: "EKF3 IMUx aiding from external pos"

  4. MAV_CMD_EXTERNAL_WIND_ESTIMATE  (43004)  speed, direction
     → EKF wind state pinned to companion-supplied value
     → STATUSTEXT: "EKF3 IMUx wind set N=... E=..."

THEN: arm, takeoff (whatever mode you take off in).

IN FLIGHT:

  5. MAV_CMD_EXTERNAL_POSITION_ESTIMATE  at companion cadence
     (Cyclops conop: ~500m / ~20s)
     → position state reset to each new fix
     → velocity state unchanged (anchored by airspeed/sideslip + frozen wind)
```

## Validating it worked

| signal | expected |
|---|---|
| STATUSTEXT after step 3 | `EKF3 IMU0 aiding from external pos` (one per IMU) |
| STATUSTEXT after step 4 | `EKF3 IMU0 wind set N=… E=…` |
| `EKF_STATUS_REPORT.flags` | `0x033f` (ATTITUDE + VEL_HORIZ + VEL_VERT + POS_HORIZ_REL + POS_HORIZ_ABS + POS_VERT_ABS + PRED_POS_HORIZ_REL + PRED_POS_HORIZ_ABS) |
| `GLOBAL_POSITION_INT` | actual lat/lon (no longer 0/0 = Africa) |

## What turns off if you don't have the bit set

`EK3_OPTIONS = 0` → identical behaviour to stock Plane. All four bits of behaviour change above are gated on `ExtPosCanBootstrap`.

## Failure modes that aren't bugs

- **Stalling after long stable cruise in SITL** — TECS/airframe tuning, not EKF. Reproducible without our patches.
- **Slow yaw drift in pure dead-reckon (no periodic fixes)** — gyro bias has no absolute anchor without GPS or periodic fixes; bounded by compass declination noise.
- **Subsequent `MAV_CMD_EXTERNAL_POSITION_ESTIMATE` returning `MAV_RESULT_FAILED` in stock builds** — only happens without patch 03/0004 (Fix 4). Confirm `EK3_OPTIONS = 8` and that the build includes the 03 series.
