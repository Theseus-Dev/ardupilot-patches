#!/usr/bin/env python3
"""
MAVLink client that verifies the AUTO-takeoff-without-GPS patch in SITL.

Usage:
  # 1. Build SITL from a checkout with this patch applied:
  #      ./waf configure --board sitl && ./waf plane
  # 2. Launch SITL with GPS disabled, e.g.:
  #      build/sitl/bin/arduplane --model plane -w \
  #         --defaults <case>.parm --home -35.363261,149.165230,584,353 -I0
  #    where <case>.parm sets FLIGHT_OPTIONS 0 (negative) or 32768 (positive),
  #    plus ARMING_CHECK 0, SIM_GPS_DISABLE 1, TKOFF_THR_MINACC 0, etc.
  # 3. Run this client:
  #      PYMAVLINK=<ap>/modules/mavlink python3 sitl_nogps_tkoff_client.py 5760 launch
  #      PYMAVLINK=<ap>/modules/mavlink python3 sitl_nogps_tkoff_client.py 5760 nolaunch
  #
  # Expected: bit set (32768) -> LAUNCHED ; bit clear (0) -> NO-LAUNCH.
  # Both cases must ARM without GPS (force-arm); only launch differs.
"""
import os, sys, time
_pml = os.environ.get("PYMAVLINK")
if _pml:
    sys.path.insert(0, _pml)
from pymavlink import mavutil

PORT = int(sys.argv[1])
EXPECT = sys.argv[2]   # "launch" or "nolaunch"
HOME_LAT, HOME_LON, HOME_ALT = -35.363261, 149.165230, 584.0

m = mavutil.mavlink_connection(f"tcp:127.0.0.1:{PORT}")
m.wait_heartbeat()
print(f"connected, sys {m.target_system}", flush=True)

def set_param(name, value, ptype=mavutil.mavlink.MAV_PARAM_TYPE_INT32):
    m.mav.param_set_send(m.target_system, m.target_component,
                         name.encode(), float(value), ptype)
    t0 = time.time()
    while time.time() - t0 < 4:
        msg = m.recv_match(type="PARAM_VALUE", blocking=True, timeout=1)
        if msg and msg.param_id == name:
            return msg.param_value
    return None

def cmd_long(cmd, *p):
    p = list(p) + [0]*(7-len(p))
    m.mav.command_long_send(m.target_system, m.target_component, cmd, 0, *p)

fo = set_param("FLIGHT_OPTIONS", 32768 if EXPECT=="launch" else 0)
set_param("SIM_GPS_DISABLE", 1)
set_param("ARMING_CHECK", 0)
print(f"FLIGHT_OPTIONS now {fo}", flush=True)
time.sleep(2)

g = m.recv_match(type="GPS_RAW_INT", blocking=True, timeout=5)
print(f"GPS fix_type = {g.fix_type if g else 'n/a'}", flush=True)

# origin + home so AUTO mission can run without GPS
m.mav.set_gps_global_origin_send(m.target_system,
        int(HOME_LAT*1e7), int(HOME_LON*1e7), int(HOME_ALT*1000))
cmd_long(mavutil.mavlink.MAV_CMD_DO_SET_HOME, 0,0,0,0, HOME_LAT, HOME_LON, HOME_ALT)
time.sleep(1)

# mission: wp(home) + takeoff
items = [(mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, HOME_LAT, HOME_LON, 0),
         (mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,  HOME_LAT, HOME_LON, 40)]
m.mav.mission_count_send(m.target_system, m.target_component, len(items))
for _ in items:
    req = m.recv_match(type=["MISSION_REQUEST","MISSION_REQUEST_INT"], blocking=True, timeout=5)
    i = req.seq
    cmd, lat, lon, alt = items[i]
    m.mav.mission_item_int_send(m.target_system, m.target_component, i,
        mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT, cmd, 0, 1, 0,0,0,0,
        int(lat*1e7), int(lon*1e7), float(alt))
ack = m.recv_match(type="MISSION_ACK", blocking=True, timeout=5)
print(f"mission ack: {ack.type if ack else 'none'}", flush=True)

# AUTO + arm
cmd_long(mavutil.mavlink.MAV_CMD_DO_SET_MODE,
         mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, 10)
time.sleep(1)

def drain_statustext():
    while True:
        s = m.recv_match(type="STATUSTEXT", blocking=False)
        if not s: break
        print(f"  STATUSTEXT: {s.text}", flush=True)

# arm with retries, confirm via heartbeat
armed = False
for attempt in range(8):
    cmd_long(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1, 21196)
    t0 = time.time()
    while time.time()-t0 < 2:
        hb = m.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
        if hb and (hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED):
            armed = True; break
    drain_statustext()
    if armed: break
hb = m.recv_match(type="HEARTBEAT", blocking=True, timeout=3)
mode = mavutil.mode_string_v10(hb) if hb else "?"
print(f"armed={armed} mode={mode}", flush=True)
if not armed:
    print("ABORT: could not arm without GPS (separate from takeoff gate)", flush=True)
    sys.exit(2)

t0 = time.time(); alt0=None; max_thr=0; max_climb=0.0
while time.time()-t0 < 35:
    v = m.recv_match(type="VFR_HUD", blocking=True, timeout=2)
    if not v: continue
    if alt0 is None: alt0 = v.alt
    max_thr = max(max_thr, v.throttle)
    max_climb = max(max_climb, v.alt-alt0)
launched = (max_thr > 40 and max_climb > 15)
print(f"RESULT max_throttle={max_thr}% max_climb={max_climb:.1f}m -> {'LAUNCHED' if launched else 'NO-LAUNCH'}", flush=True)
ok = (launched and EXPECT=="launch") or (not launched and EXPECT=="nolaunch")
print(f"EXPECT={EXPECT} VERDICT={'PASS' if ok else 'FAIL'}", flush=True)
sys.exit(0 if ok else 1)
