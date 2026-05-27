# tools/init — companion-side no-GPS init

Three files:

- `init_nogps.yaml` — edit lat/lon/wind/etc. for the flight
- `init_nogps.py`   — reads the YAML and runs the 5-step init
- `send_wind_in_air.py` — resends external wind after takeoff

## Usage

```sh
pip install pymavlink pyyaml
chmod +x init_nogps.py send_wind_in_air.py
./init_nogps.py                 # uses ./init_nogps.yaml
./init_nogps.py /path/to/other.yaml
```

Exit 0 = bootstrapped, safe to arm. Exit 1 = check STATUSTEXTs.

Send wind after takeoff:

```sh
./send_wind_in_air.py --speed-ms 6 --direction-deg 270
./send_wind_in_air.py --duration-s 30 --rate-hz 2 --speed-ms 8 --direction-deg 300
```

Direction is the direction wind is coming from, clockwise from north. Example:
wind from west is `270`.

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
