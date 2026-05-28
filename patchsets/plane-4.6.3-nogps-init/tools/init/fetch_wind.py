#!/usr/bin/env python3
"""
fetch_wind.py — interactive wind lookup for the no-GPS init flow.

Pulls the current 10 m wind speed and direction from Open-Meteo for a
given lat/lon and (optionally) writes them into init_nogps.yaml so the
next init_nogps.py run sends them as MAV_CMD_EXTERNAL_WIND_ESTIMATE.

Conventions match the rest of this toolset:
    speed_ms       — wind speed in m/s
    direction_deg  — meteorological bearing the wind is FROM,
                     0° = from N, measured clockwise

Open-Meteo is free, requires no API key, and is backed by the same
ECMWF / GFS / ICON models commercial sites (Windy, etc.) consume. Wind
direction in its response already uses the from-N CW convention, so the
number drops straight into MAV_CMD_EXTERNAL_WIND_ESTIMATE.

Usage:
    fetch_wind.py [path/to/init_nogps.yaml]

Only stdlib + pyyaml.
"""

from __future__ import annotations
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from typing import Optional

import yaml


CONFIG_DEFAULT = os.path.join(os.path.dirname(__file__), "init_nogps.yaml")
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
HTTP_TIMEOUT_S = 10.0

COMPASS_16 = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def compass_from_deg(deg: float) -> str:
    """16-point compass label for a bearing in degrees (0=N, CW)."""
    idx = int((deg % 360) / 22.5 + 0.5) % 16
    return COMPASS_16[idx]


def prompt(label: str, default: Optional[str] = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        try:
            raw = input(f"{label}{suffix}: ").strip()
        except EOFError:
            print()
            sys.exit(1)
        if raw:
            return raw
        if default is not None:
            return default


def prompt_float(label: str, default: Optional[float]) -> float:
    default_str = None if default is None else f"{default:g}"
    while True:
        raw = prompt(label, default_str)
        try:
            return float(raw)
        except ValueError:
            print(f"  not a number: {raw!r}")


def prompt_yes(label: str, default_yes: bool = True) -> bool:
    suffix = "Y/n" if default_yes else "y/N"
    raw = prompt(f"{label} ({suffix})", "y" if default_yes else "n").lower()
    return raw.startswith("y")


def fetch_open_meteo(lat: float, lon: float) -> dict:
    params = urllib.parse.urlencode({
        "latitude": lat,
        "longitude": lon,
        "current": "wind_speed_10m,wind_direction_10m,wind_gusts_10m",
        "wind_speed_unit": "ms",
        "timezone": "UTC",
    })
    url = f"{OPEN_METEO_URL}?{params}"
    with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT_S) as resp:
        data = json.load(resp)
    cur = data.get("current")
    if not cur or "wind_speed_10m" not in cur or "wind_direction_10m" not in cur:
        raise RuntimeError(f"unexpected Open-Meteo response: {data!r}")
    return {
        "time": cur.get("time"),
        "speed_ms": float(cur["wind_speed_10m"]),
        "direction_deg": float(cur["wind_direction_10m"]),
        "gust_ms": float(cur["wind_gusts_10m"]) if cur.get("wind_gusts_10m") is not None else None,
        "elevation_m": data.get("elevation"),
    }


def print_wind(report: dict, lat: float, lon: float) -> None:
    speed = report["speed_ms"]
    deg = report["direction_deg"]
    # Bearing wind is from -> bearing wind is to is 180° opposite.
    to_deg = (deg + 180.0) % 360.0
    # NED components of the wind velocity vector (where the air is going).
    # See AHRS hook in patch 0004: windN = -cos(dir)*speed, windE = -sin(dir)*speed.
    rad = math.radians(deg)
    windN = -math.cos(rad) * speed
    windE = -math.sin(rad) * speed
    print()
    print(f"  location:     {lat:.5f}, {lon:.5f}"
          + (f"   (elev {report['elevation_m']:.0f} m)" if report.get("elevation_m") is not None else ""))
    if report.get("time"):
        print(f"  valid (UTC):  {report['time']}")
    print(f"  speed:        {speed:.2f} m/s"
          + (f"   gust {report['gust_ms']:.2f} m/s" if report.get("gust_ms") is not None else ""))
    print(f"  direction:    {deg:6.1f}°  (from {compass_from_deg(deg)},"
          f" blowing toward {compass_from_deg(to_deg)} / {to_deg:.0f}°)")
    print(f"  EKF NED wind: N={windN:+.2f}  E={windE:+.2f}  m/s")
    print()


def update_yaml_wind(path: str, speed_ms: float, direction_deg: float) -> None:
    """Rewrite speed_ms / direction_deg under the `wind:` block in place,
    preserving comments, indentation, and the rest of the file."""
    with open(path) as f:
        lines = f.readlines()

    in_wind = False
    wind_indent = -1
    updated_speed = False
    updated_dir = False

    def replace_value(line: str, key: str, new_value: str) -> str:
        # Match: <indent><key>: <old_value>[  # comment]
        head, _, rest = line.partition(":")
        # Split rest into value vs trailing comment.
        comment_idx = rest.find("#")
        if comment_idx == -1:
            trailing = ""
        else:
            trailing = "  " + rest[comment_idx:].rstrip("\n")
        # Preserve newline if present
        newline = "\n" if line.endswith("\n") else ""
        return f"{head}: {new_value}{trailing}{newline}"

    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(stripped)

        if not in_wind:
            if stripped.startswith("wind:"):
                in_wind = True
                wind_indent = indent
            continue

        # We're inside the wind: block. Leave on the next top-level key
        # (indent <= wind_indent and the line is a key).
        if indent <= wind_indent and ":" in stripped:
            break

        if stripped.startswith("speed_ms:"):
            lines[i] = replace_value(line, "speed_ms", f"{speed_ms:.2f}")
            updated_speed = True
        elif stripped.startswith("direction_deg:"):
            lines[i] = replace_value(line, "direction_deg", f"{direction_deg:.1f}")
            updated_dir = True

    if not (updated_speed and updated_dir):
        missing = []
        if not updated_speed:
            missing.append("speed_ms")
        if not updated_dir:
            missing.append("direction_deg")
        raise RuntimeError(
            f"could not find {', '.join(missing)} under wind: in {path}"
        )

    with open(path, "w") as f:
        f.writelines(lines)


def main() -> int:
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else CONFIG_DEFAULT

    cfg = {}
    if os.path.exists(cfg_path):
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f) or {}

    pos = cfg.get("position", {}) or {}
    default_lat = pos.get("lat")
    default_lon = pos.get("lon")

    print("fetch_wind.py — Open-Meteo current 10 m wind")
    print(f"config: {cfg_path}" + ("  (not found, will only print)" if not cfg else ""))
    print()

    lat = prompt_float("latitude  (deg)", default_lat)
    lon = prompt_float("longitude (deg)", default_lon)

    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        print(f"  lat/lon out of range: {lat}, {lon}", file=sys.stderr)
        return 2

    print(f"  → fetching Open-Meteo for {lat:.5f}, {lon:.5f} …")
    try:
        report = fetch_open_meteo(lat, lon)
    except Exception as e:
        print(f"  fetch failed: {e}", file=sys.stderr)
        return 2

    print_wind(report, lat, lon)

    if not cfg:
        print("(no YAML loaded — nothing to update)")
        return 0

    if not prompt_yes(f"write speed/direction into {os.path.basename(cfg_path)}?", True):
        print("not updated.")
        return 0

    try:
        update_yaml_wind(cfg_path, report["speed_ms"], report["direction_deg"])
    except Exception as e:
        print(f"  update failed: {e}", file=sys.stderr)
        return 2

    print(f"  ✓ wrote speed_ms={report['speed_ms']:.2f}  "
          f"direction_deg={report['direction_deg']:.1f}  to {cfg_path}")
    print("  next: ./init_nogps.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
