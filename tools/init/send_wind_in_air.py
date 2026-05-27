#!/usr/bin/env python3
"""
send_wind_in_air.py — repeatedly send MAV_CMD_EXTERNAL_WIND_ESTIMATE.

Use this after launch, once the aircraft is actually airborne. The custom
no-GPS EKF firmware rejects external wind while on ground.

Examples:
    ./send_wind_in_air.py --speed-ms 6 --direction-deg 270
    ./send_wind_in_air.py --connection /dev/ttyUSB0 --baud 57600 --speed-ms 5.5 --direction-deg 240
    ./send_wind_in_air.py --duration-s 30 --rate-hz 2 --speed-ms 8 --direction-deg 300

Direction is standard meteorological direction: wind FROM this direction,
clockwise from north. Example: wind from west is 270 degrees.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any

import yaml
from pymavlink import mavutil


CONFIG_DEFAULT = os.path.join(os.path.dirname(__file__), "init_nogps.yaml")
MAV_CMD_EXTERNAL_WIND_ESTIMATE = getattr(
    mavutil.mavlink,
    "MAV_CMD_EXTERNAL_WIND_ESTIMATE",
    43004,
)


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def load_config(path: str) -> dict[str, Any]:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send MAV_CMD_EXTERNAL_WIND_ESTIMATE after takeoff.",
    )
    parser.add_argument(
        "config",
        nargs="?",
        default=CONFIG_DEFAULT,
        help=f"init_nogps.yaml path (default: {CONFIG_DEFAULT})",
    )
    parser.add_argument("--connection", help="MAVLink endpoint, overrides YAML")
    parser.add_argument("--baud", type=int, help="Serial baud, overrides YAML")
    parser.add_argument("--source-system", type=int, help="MAVLink sender sysid, overrides YAML")
    parser.add_argument("--source-component", type=int, default=190, help="MAVLink sender compid (default: 190)")
    parser.add_argument("--target-system", type=int, help="Autopilot sysid, overrides YAML/heartbeat")
    parser.add_argument("--target-component", type=int, default=1, help="Autopilot compid (default: 1)")
    parser.add_argument("--speed-ms", type=float, help="Wind speed in m/s, overrides YAML wind.speed_ms")
    parser.add_argument(
        "--direction-deg",
        type=float,
        help="Wind direction FROM, degrees clockwise from north, overrides YAML wind.direction_deg",
    )
    parser.add_argument("--duration-s", type=float, default=20.0, help="How long to send for (default: 20)")
    parser.add_argument("--rate-hz", type=float, default=1.0, help="Send rate in Hz (default: 1)")
    parser.add_argument("--heartbeat-timeout-s", type=float, default=15.0, help="Heartbeat wait timeout (default: 15)")
    parser.add_argument("--quiet-statustext", action="store_true", help="Do not print unrelated STATUSTEXT messages")
    return parser.parse_args()


def send_wind_command(mav, speed_ms: float, direction_deg: float) -> None:
    mav.mav.command_int_send(
        mav.target_system,
        mav.target_component,
        mavutil.mavlink.MAV_FRAME_GLOBAL,
        MAV_CMD_EXTERNAL_WIND_ESTIMATE,
        0,
        0,
        float(speed_ms),
        0.0,
        float(direction_deg),
        0.0,
        0,
        0,
        0.0,
    )


def drain_messages(mav, quiet_statustext: bool, deadline: float) -> tuple[bool, bool]:
    confirmed = False
    rejected = False
    while time.time() < deadline:
        msg = mav.recv_match(type=["STATUSTEXT", "COMMAND_ACK"], blocking=True, timeout=0.1)
        if msg is None:
            continue

        msg_type = msg.get_type()
        if msg_type == "STATUSTEXT":
            text = msg.text
            text_l = text.lower()
            if "wind set n=" in text_l:
                log(f"CONFIRMED: {text}")
                confirmed = True
            elif "wind set rejected" in text_l:
                log(f"REJECTED: {text}")
                rejected = True
            elif not quiet_statustext:
                log(f"STATUSTEXT: {text}")
            continue

        if msg_type == "COMMAND_ACK" and msg.command == MAV_CMD_EXTERNAL_WIND_ESTIMATE:
            log(f"COMMAND_ACK result={msg.result}")

    return confirmed, rejected


def main() -> int:
    args = parse_args()
    cfg = load_config(args.config)
    mav_cfg = cfg.get("mavlink", {})
    wind_cfg = cfg.get("wind", {})

    connection = args.connection or mav_cfg.get("connection")
    if not connection:
        log("ERROR: no MAVLink connection provided in CLI or YAML")
        return 2

    speed_ms = args.speed_ms if args.speed_ms is not None else wind_cfg.get("speed_ms")
    direction_deg = args.direction_deg if args.direction_deg is not None else wind_cfg.get("direction_deg")
    if speed_ms is None or direction_deg is None:
        log("ERROR: provide --speed-ms and --direction-deg, or set wind in YAML")
        return 2

    if args.rate_hz <= 0 or args.duration_s <= 0:
        log("ERROR: --rate-hz and --duration-s must be positive")
        return 2

    baud = args.baud if args.baud is not None else mav_cfg.get("baud", 57600)
    source_system = args.source_system if args.source_system is not None else mav_cfg.get("source_system", 254)

    log(f"connecting to {connection} ...")
    mav = mavutil.mavlink_connection(
        connection,
        baud=baud,
        source_system=source_system,
        source_component=args.source_component,
        autoreconnect=True,
    )

    mav.wait_heartbeat(timeout=args.heartbeat_timeout_s)
    heartbeat_sysid = mav.target_system
    heartbeat_compid = mav.target_component
    mav.target_system = args.target_system if args.target_system is not None else mav_cfg.get("target_system", heartbeat_sysid)
    mav.target_component = args.target_component

    log(
        f"heartbeat OK (sysid={heartbeat_sysid}, compid={heartbeat_compid}); "
        f"targeting sysid={mav.target_system}, compid={mav.target_component}"
    )
    log(
        f"sending wind estimate: speed={float(speed_ms):.2f} m/s, "
        f"direction_from={float(direction_deg):.1f} deg, duration={args.duration_s:.1f}s"
    )

    interval = 1.0 / args.rate_hz
    end_time = time.time() + args.duration_s
    next_send = time.time()
    confirmed_any = False
    rejected_any = False
    send_count = 0

    while time.time() < end_time:
        now = time.time()
        if now >= next_send:
            send_wind_command(mav, float(speed_ms), float(direction_deg))
            send_count += 1
            log(f"sent #{send_count}")
            next_send = now + interval

        confirmed, rejected = drain_messages(mav, args.quiet_statustext, min(next_send, end_time))
        confirmed_any = confirmed_any or confirmed
        rejected_any = rejected_any or rejected

    log(f"done; sent {send_count} wind commands")
    if confirmed_any:
        log("at least one EKF wind-set confirmation was received")
        return 0
    if rejected_any:
        log("only wind rejection(s) were observed; was the aircraft still on ground?")
        return 1
    log("no EKF wind confirmation observed; command may still have arrived if STATUSTEXT was dropped")
    return 2


if __name__ == "__main__":
    sys.exit(main())
