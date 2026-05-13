#!/usr/bin/env python3
"""
init_nogps.py — drive a theseus-ekf-patches plane through the on-ground
initialization sequence using values from a YAML config.

Usage:
    init_nogps.py [path/to/init_nogps.yaml]

Default config path is ./init_nogps.yaml next to this script.

What it sends, in order, on the ground before arm:
    1. SET_GPS_GLOBAL_ORIGIN          (EKF reference frame)
    2. MAV_CMD_DO_SET_HOME            (AHRS home, needed for AUTO)
    3. MAV_CMD_EXTERNAL_POSITION_ESTIMATE  (EKF: AID_NONE -> AID_ABSOLUTE)
    4. MAV_CMD_EXTERNAL_WIND_ESTIMATE (EKF wind state)

After this script returns 0, the EKF is bootstrapped and the vehicle can
be armed and taken off in any mode. The companion is responsible for
re-sending MAV_CMD_EXTERNAL_POSITION_ESTIMATE at its cruise cadence in
flight.

Requires: pymavlink (`pip install pymavlink`), pyyaml.
"""

from __future__ import annotations
import os
import sys
import time
import yaml
from pymavlink import mavutil


CONFIG_DEFAULT = os.path.join(os.path.dirname(__file__), "init_nogps.yaml")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_config(path: str) -> dict:
    with open(path) as f:
        cfg = yaml.safe_load(f)
    log(f"loaded config from {path}")
    return cfg


def wait_for_statustext(mav, needle: str, timeout: float) -> bool:
    """Block until a STATUSTEXT containing `needle` arrives, or timeout."""
    t0 = time.time()
    needle = needle.lower()
    while time.time() - t0 < timeout:
        msg = mav.recv_match(type="STATUSTEXT", blocking=True, timeout=0.5)
        if msg and needle in msg.text.lower():
            log(f"  ✓ confirmed: {msg.text}")
            return True
    return False


def step_origin(mav, cfg) -> None:
    o = cfg["position"]
    log(f"1/4 SET_GPS_GLOBAL_ORIGIN  lat={o['lat']}  lon={o['lon']}  alt={o['alt']}")
    mav.mav.set_gps_global_origin_send(
        mav.target_system,
        int(o["lat"] * 1e7),
        int(o["lon"] * 1e7),
        int(o["alt"] * 1000),
    )
    time.sleep(cfg["delays_s"]["after_origin"])


def step_home(mav, cfg) -> None:
    o = cfg["position"]
    log(f"2/4 MAV_CMD_DO_SET_HOME    lat={o['lat']}  lon={o['lon']}  alt={o['alt']}")
    mav.mav.command_int_send(
        mav.target_system, mav.target_component,
        mavutil.mavlink.MAV_FRAME_GLOBAL,
        mavutil.mavlink.MAV_CMD_DO_SET_HOME,
        0, 0,
        0,        # param1=0 means use specified location
        0, 0, 0,
        int(o["lat"] * 1e7),
        int(o["lon"] * 1e7),
        float(o["alt"]),
    )
    ack = mav.recv_match(type="COMMAND_ACK", blocking=True, timeout=3)
    if ack and ack.command == mavutil.mavlink.MAV_CMD_DO_SET_HOME:
        log(f"  ack result={ack.result}  ({'ACCEPTED' if ack.result == 0 else 'FAILED'})")
    time.sleep(cfg["delays_s"]["after_home"])


def step_position(mav, cfg) -> bool:
    p = cfg["position"]
    log(f"3/4 EXTERNAL_POSITION_ESTIMATE  lat={p['lat']}  lon={p['lon']}  acc={p['accuracy_m']}m")
    mav.mav.command_int_send(
        mav.target_system, mav.target_component,
        mavutil.mavlink.MAV_FRAME_GLOBAL,
        mavutil.mavlink.MAV_CMD_EXTERNAL_POSITION_ESTIMATE,
        0, 0,
        float(time.time()),           # param1: transmit unix time (seconds)
        0.05,                          # param2: processing delay (seconds)
        float(p["accuracy_m"]),        # param3: horizontal accuracy (m)
        0,                             # param4: unused
        int(p["lat"] * 1e7),
        int(p["lon"] * 1e7),
        float("nan"),                  # alt: NaN means "use EKF height"
    )
    time.sleep(cfg["delays_s"]["after_position"])
    if cfg["verify"]["bootstrap_statustext"]:
        if not wait_for_statustext(mav, "aiding from external pos",
                                    cfg["verify"]["timeout_s"]):
            log("  ⚠ no 'aiding from external pos' STATUSTEXT — bootstrap may have failed")
            return False
    return True


def step_wind(mav, cfg) -> bool:
    w = cfg["wind"]
    log(f"4/4 EXTERNAL_WIND_ESTIMATE  speed={w['speed_ms']}m/s  dir={w['direction_deg']}°")
    mav.mav.command_int_send(
        mav.target_system, mav.target_component,
        mavutil.mavlink.MAV_FRAME_GLOBAL,
        mavutil.mavlink.MAV_CMD_EXTERNAL_WIND_ESTIMATE,
        0, 0,
        float(w["speed_ms"]),          # param1: wind speed (m/s)
        0,                             # param2: speed accuracy (unused)
        float(w["direction_deg"]),     # param3: wind direction (0=from N, CW)
        0,                             # param4: dir accuracy (unused)
        0, 0, 0,
    )
    time.sleep(cfg["delays_s"]["after_wind"])
    if cfg["verify"]["wind_statustext"]:
        if not wait_for_statustext(mav, "wind set",
                                    cfg["verify"]["timeout_s"]):
            log("  ⚠ no 'wind set' STATUSTEXT — wind reset may have failed")
            return False
    return True


def main() -> int:
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else CONFIG_DEFAULT
    cfg = load_config(cfg_path)
    m = cfg["mavlink"]

    log(f"connecting to {m['connection']}…")
    mav = mavutil.mavlink_connection(
        m["connection"],
        baud=m.get("baud", 57600),
        source_system=m.get("source_system", 254),
        autoreconnect=True,
    )
    mav.wait_heartbeat(timeout=15)
    log(f"heartbeat OK  (sysid={mav.target_system}  compid={mav.target_component})")

    step_origin(mav, cfg)
    step_home(mav, cfg)
    pos_ok = step_position(mav, cfg)
    wind_ok = step_wind(mav, cfg)

    if pos_ok and wind_ok:
        log("init complete — EKF bootstrapped on the ground.  Safe to arm.")
        return 0
    log("init FINISHED with warnings — check STATUSTEXTs above before arming.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
