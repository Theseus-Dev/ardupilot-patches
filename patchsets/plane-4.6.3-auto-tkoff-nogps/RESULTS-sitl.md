# Plane 4.6.3 AUTO Takeoff Without GPS: SITL Verification

Date: 2026-06-17
Base: `Plane-4.6.3` + `patches/ardupilot/0001-ArduPlane-allow-AUTO-takeoff-without-GPS-via-FLIGHT_.patch`

## Goal

Confirm that with GPS disabled, an AUTO `NAV_TAKEOFF`:

- **does NOT** launch with `FLIGHT_OPTIONS` bit 15 clear (stock gate intact), and
- **DOES** launch with bit 15 (`ALLOW_AUTO_TKOFF_NO_GPS`, value 32768) set,

with everything else held constant — isolating the patch as the only variable.

## Method

Built ArduPlane SITL from the patched tree:

```sh
./waf configure --board sitl && ./waf plane     # clean build, 1349/1349
```

Launched SITL twice (fresh `-w` each time), GPS disabled from boot:

```sh
build/sitl/bin/arduplane --model plane --speedup 10 -w \
    --defaults <case>.parm --home -35.363261,149.165230,584,353 -I0
```

Common params (both cases):

```
ARMING_CHECK     0      # bypass prearm (as done for FBWA no-GPS launch)
SIM_GPS_DISABLE  1      # no GPS from boot
TKOFF_THR_MINACC 0      # launch trigger does not wait on accel event
TKOFF_THR_MINSPD 0      # ground-speed term satisfied without GPS
TKOFF_THR_DELAY  2
TKOFF_ROTATE_SPD 0
```

Only difference between cases:

```
FLIGHT_OPTIONS   0       # negative
FLIGHT_OPTIONS   32768   # positive (bit 15)
```

Driver: `tools/sitl_nogps_tkoff_client.py`. It force-arms (MAV_CMD
COMPONENT_ARM_DISARM param2=21196), sets AUTO, uploads a 2-item mission
(home + `NAV_TAKEOFF` 40 m), sets origin+home (`SET_GPS_GLOBAL_ORIGIN` +
`DO_SET_HOME`) so the mission can run without GPS, then watches `VFR_HUD`
throttle and altitude for 35 s. "Launched" = throttle > 40% AND climb > 15 m.

## Result — PASS

| Case | FLIGHT_OPTIONS | GPS fix | Armed | Max throttle | Max climb | Outcome |
|---|---|---|---|---|---|---|
| Negative | 0 | 0 (none) | **yes** | 0 % | 0.1 m | **NO-LAUNCH** |
| Positive | 32768 | 0 (none) | **yes** | 100 % | 46.9 m | **LAUNCHED** |

Key point: **both cases armed without GPS** (`fix_type=0`, force-arm), so the
negative result is the takeoff GPS gate keeping throttle suppressed — not an
arming failure. Flipping bit 15 is the sole cause of the difference.

Raw driver output:

```
# negative
FLIGHT_OPTIONS now 0.0
GPS fix_type = 0
armed=True mode=AUTO
RESULT max_throttle=0% max_climb=0.1m -> NO-LAUNCH
EXPECT=nolaunch VERDICT=PASS

# positive
FLIGHT_OPTIONS now 32768.0
GPS fix_type = 0
armed=True mode=AUTO
RESULT max_throttle=100% max_climb=46.9m -> LAUNCHED
EXPECT=launch VERDICT=PASS
```

## Notes / caveats

- AHRS attitude during the no-GPS climb comes from DCM fallback (EKF3 has no
  position source). This patch does not change that; pair with a position
  source after launch for the rest of the mission (e.g. companion
  `MAV_CMD_EXTERNAL_POSITION_ESTIMATE`, optionally with the
  `plane-4.6.3-nogps-init` EKF bootstrap).
- `verify_takeoff()` was not modified: without a GPS course lock it climbs
  wings-level (`update_level_flight()`), which is what the SITL run did.
- SITL must be launched as a long-lived process (the harness/`run_in_background`
  or a terminal); a shell-backgrounded `&` from a one-shot command gets torn
  down with the command.
- CubeOrangePlus firmware also builds from the same patched tree (hardware
  build, not flown).
