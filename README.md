# ArduPilot Patchsets

This repository contains independent ArduPilot patchsets. Pick the patchset
for the target customer/version; do not treat the directories as one combined
series.

## Patchsets

| Directory | Target | Purpose |
|---|---|---|
| `patchsets/plane-4.6.3-nogps-init` | `Plane-4.6.3` | Initialize and operate EKF3 without GPS using companion-provided external position fixes. |
| `patchsets/plane-4.3.8-mavlink-43003` | `Plane-4.3.8` | Add `MAV_CMD_EXTERNAL_POSITION_ESTIMATE` (`43003`) support to Plane 4.3.8 with a minimal MAVLink XML backport. |

## Apply

Use the patchset-local scripts:

```sh
patchsets/plane-4.6.3-nogps-init/apply.sh /path/to/ardupilot Plane-4.6.3
patchsets/plane-4.3.8-mavlink-43003/apply.sh /path/to/ardupilot Plane-4.3.8
```

Convenience wrappers are also available from the repository root:

```sh
./apply.sh plane-4.6.3-nogps-init /path/to/ardupilot
./apply.sh plane-4.3.8-mavlink-43003 /path/to/ardupilot
```

## Scope Separation

- `plane-4.6.3-nogps-init` changes EKF3 bootstrap behavior and is gated by
  `EK3_OPTIONS` bit 3. It is for no-GPS initialization and companion-driven
  navigation.
- `plane-4.3.8-mavlink-43003` only backports the MAVLink command definition
  and upstream ArduPilot handlers/tests for command `43003`. It does not add
  the no-GPS bootstrap behavior or `EK3_OPTIONS` changes.

