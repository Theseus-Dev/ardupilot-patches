# tools/init — companion-side no-GPS init

Four files:

- `init_nogps.yaml` — edit lat/lon/wind/etc. for the flight
- `init_nogps.py`   — reads the YAML and runs the 5-step init
- `fetch_wind.py`   — pulls current wind from Open-Meteo and writes it into the YAML
- `send_wind.py`    — sends only the wind estimate (useful after fetch_wind.py)

## Usage

```sh
pip install pymavlink pyyaml
chmod +x init_nogps.py fetch_wind.py send_wind.py
./fetch_wind.py                 # interactive: lat/lon defaults from YAML
./init_nogps.py                 # uses ./init_nogps.yaml
./init_nogps.py /path/to/other.yaml
./send_wind.py                  # just push the YAML's wind block to the plane
```

Exit 0 = bootstrapped, safe to arm. Exit 1 = check STATUSTEXTs.

## fetch_wind.py

Hits the Open-Meteo free API (no key) for current 10 m wind at a given
lat/lon and offers to write `speed_ms` / `direction_deg` into
`init_nogps.yaml` in place, preserving comments. Open-Meteo's wind
direction is already meteorological (0° = from N, clockwise), the same
convention `MAV_CMD_EXTERNAL_WIND_ESTIMATE` expects, so the number drops
straight through to the EKF.

## send_wind.py

Sends a single `MAV_CMD_EXTERNAL_WIND_ESTIMATE` using the `wind:` block
in the YAML — no origin / home / position. Pair with `fetch_wind.py`
when you want to update the EKF's wind state without re-running the
full bootstrap.

## What it sends

| step | MAVLink command | purpose |
|---|---|---|
| 1 | `SET_GPS_GLOBAL_ORIGIN` | EKF reference frame |
| 2 | `MAV_CMD_DO_SET_HOME` | AHRS home (AUTO mission needs it) |
| 3 | `MAV_CMD_EXTERNAL_POSITION_ESTIMATE` | EKF: AID_NONE → AID_ABSOLUTE |
| 4 | `MAV_CMD_EXTERNAL_WIND_ESTIMATE` | EKF wind state |

After this, the vehicle can be armed and taken off in any mode. The
companion is responsible for re-sending
`MAV_CMD_EXTERNAL_POSITION_ESTIMATE` at its cruise cadence in flight.
