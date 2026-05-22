# tools/init — companion-side no-GPS init

Two files:

- `init_nogps.yaml` — edit lat/lon/wind/etc. for the flight
- `init_nogps.py`   — reads the YAML and runs the 5-step init

## Usage

```sh
pip install pymavlink pyyaml
chmod +x init_nogps.py
./init_nogps.py                 # uses ./init_nogps.yaml
./init_nogps.py /path/to/other.yaml
```

Exit 0 = bootstrapped, safe to arm. Exit 1 = check STATUSTEXTs.

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
