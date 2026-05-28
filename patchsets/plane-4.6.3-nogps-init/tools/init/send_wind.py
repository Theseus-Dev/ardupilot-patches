#!/usr/bin/env python3
"""
send_wind.py — push only the wind estimate to a Plane.

Reads init_nogps.yaml for the MAVLink connection and the `wind:` block,
connects, and sends a single MAV_CMD_EXTERNAL_WIND_ESTIMATE. Used after
fetch_wind.py refreshes the YAML, or any time you want to update the
EKF's wind state without re-running the full bootstrap.

Convention (same as init_nogps.py):
    speed_ms       — wind speed in m/s
    direction_deg  — meteorological bearing the wind is FROM,
                     0° = from N, measured clockwise

Usage:
    send_wind.py [path/to/init_nogps.yaml]

Requires: pymavlink, pyyaml.
"""

from __future__ import annotations
import os
import sys
import time
import yaml
from pymavlink import mavutil


CONFIG_DEFAULT = os.path.join(os.path.dirname(__file__), "init_nogps.yaml")
MAV_CMD_EXTERNAL_WIND_ESTIMATE = getattr(
    mavutil.mavlink,
    "MAV_CMD_EXTERNAL_WIND_ESTIMATE",
    43004,
)


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def wait_for_statustext_any(mav, needles: list[str], timeout: float):
    t0 = time.time()
    needles_l = [n.lower() for n in needles]
    while time.time() - t0 < timeout:
        msg = mav.recv_match(type="STATUSTEXT", blocking=True, timeout=0.5)
        if not msg:
            continue
        text_l = msg.text.lower()
        for needle, needle_l in zip(needles, needles_l):
            if needle_l in text_l:
                log(f"  ✓ confirmed: {msg.text}")
                return msg, needle
    return None, None


def send_wind(mav, wind: dict, verify: bool, timeout_s: float) -> bool:
    speed = float(wind["speed_ms"])
    direction = float(wind["direction_deg"])
    log(f"EXTERNAL_WIND_ESTIMATE  speed={speed}m/s  dir={direction}°")
    mav.mav.command_int_send(
        mav.target_system, mav.target_component,
        mavutil.mavlink.MAV_FRAME_GLOBAL,
        MAV_CMD_EXTERNAL_WIND_ESTIMATE,
        0, 0,
        speed,        # param1: wind speed (m/s)
        0,            # param2: speed accuracy (unused)
        direction,    # param3: wind direction (0=from N, CW)
        0,            # param4: dir accuracy (unused)
        0, 0, 0,
    )
    if not verify:
        return True
    _msg, needle = wait_for_statustext_any(
        mav,
        ["wind set rejected", "wind set N="],
        timeout_s,
    )
    if needle == "wind set rejected":
        log("  ⚠ wind estimate was rejected")
        return False
    if needle != "wind set N=":
        log("  ⚠ no 'wind set' STATUSTEXT — wind reset may have failed")
        return False
    return True


def main() -> int:
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else CONFIG_DEFAULT
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    log(f"loaded config from {cfg_path}")

    m = cfg["mavlink"]
    log(f"connecting to {m['connection']}…")
    mav = mavutil.mavlink_connection(
        m["connection"],
        baud=m.get("baud", 57600),
        source_system=m.get("source_system", 254),
        autoreconnect=True,
    )
    mav.wait_heartbeat(timeout=15)
    heartbeat_sysid = mav.target_system
    heartbeat_compid = mav.target_component
    mav.target_system = m.get("target_system", heartbeat_sysid)
    mav.target_component = m.get("target_component", 1)
    log(
        f"heartbeat OK  (sysid={heartbeat_sysid}  compid={heartbeat_compid}); "
        f"targeting sysid={mav.target_system} compid={mav.target_component}"
    )

    verify = bool(cfg.get("verify", {}).get("wind_statustext", True))
    timeout_s = float(cfg.get("verify", {}).get("timeout_s", 5.0))
    ok = send_wind(mav, cfg["wind"], verify, timeout_s)

    if ok:
        log("wind estimate sent.")
        return 0
    log("wind estimate FINISHED with warnings — check STATUSTEXTs above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
