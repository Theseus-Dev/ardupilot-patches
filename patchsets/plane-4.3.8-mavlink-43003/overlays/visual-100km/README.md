# Visual 100 km Overlay

Optional validation overlay for `plane-4.3.8-mavlink-43003`.

This is not part of the production backport. It changes only
`Tools/autotest/arduplane.py` so the accepted no-GPS
`MAV_CMD_EXTERNAL_POSITION_ESTIMATE` command injects a 100 km north position
offset. The large offset makes the estimator reset obvious in the MAVProxy map.

Use:

```sh
patchsets/plane-4.3.8-mavlink-43003/visual-map-test.sh /path/to/ardupilot
```

