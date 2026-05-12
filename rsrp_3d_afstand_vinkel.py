# =========================================================
# RSRP + GPS -> 3D afstand, azimuth, elevation
# ENDELIG VERSION
#
# - Kun udadkørsel
# - Stopper ved FØRSTE gang maksimal afstand nås
# - Fjerner falsk "stand‑still" hale
# - Stabiliserer slut‑området
# =========================================================

import os
import math
import re
import pandas as pd

# ---------------------------------------------------------
# STIER
# ---------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DRONE_GPS_FILE = os.path.join(
    BASE_DIR, "data", "meas_thy", "pi_thy", "thy_3",
    "1777634872-teltonika-gps.log"
)

ANTENNA_GPS_FILE = os.path.join(
    BASE_DIR, "data", "meas_thy", "pc_thy", "thy_3.log"
)

RADIO_FILE = os.path.join(
    BASE_DIR, "data", "meas_thy", "pi_thy", "thy_3",
    "1777634872-radio.log"
)

# ---------------------------------------------------------
# PARAMETRE
# ---------------------------------------------------------
DRONE_HEIGHT_M = 120.0
ANTENNA_HEIGHT_M = 4.0
DZ = ANTENNA_HEIGHT_M - DRONE_HEIGHT_M  # -116 m

ANTENNA_TILT_DEG = 5.0
EARTH_RADIUS = 6371000.0

MIN_DISTANCE_STEP = 5.0  # meter – dæmper over-sampling

# ---------------------------------------------------------
# HJÆLPEFUNKTIONER
# ---------------------------------------------------------
def nmea_to_decimal(value, direction):
    if not value:
        return None
    deg = int(value[:2])
    minutes = float(value[2:])
    coord = deg + minutes / 60.0
    return -coord if direction in ("S", "W") else coord

def haversine(lat1, lon1, lat2, lon2):
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return 2 * EARTH_RADIUS * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def azimuth(lat1, lon1, lat2, lon2):
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(math.radians(lat2))
    y = (
        math.cos(math.radians(lat1)) * math.sin(math.radians(lat2))
        - math.sin(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.cos(dlon)
    )
    return (math.degrees(math.atan2(x, y)) + 360) % 360

# ---------------------------------------------------------
# DRONE GPS (STATIONÆR – MIDDEL)
# ---------------------------------------------------------
drone_lats, drone_lons = [], []

with open(DRONE_GPS_FILE, encoding="utf-8", errors="ignore") as f:
    for line in f:
        if "$GPGGA" in line:
            try:
                p = line.split("$GPGGA,")[1].split(",")
                drone_lats.append(nmea_to_decimal(p[1], p[2]))
                drone_lons.append(nmea_to_decimal(p[3], p[4]))
            except:
                pass

if not drone_lats:
    raise RuntimeError("Ingen gyldige GPS-punkter i dronelog")

DRONE_LAT = sum(drone_lats) / len(drone_lats)
DRONE_LON = sum(drone_lons) / len(drone_lons)

# ---------------------------------------------------------
# ANTENNE GPS (BIL)
# ---------------------------------------------------------
antenna_rows = []

with open(ANTENNA_GPS_FILE, encoding="utf-8", errors="ignore") as f:
    for line in f:
        if "$GPGGA" in line:
            try:
                p = line.split("$GPGGA,")[1].split(",")
                antenna_rows.append({
                    "lat": nmea_to_decimal(p[1], p[2]),
                    "lon": nmea_to_decimal(p[3], p[4])
                })
            except:
                pass

antenna_df = pd.DataFrame(antenna_rows)

if antenna_df.empty:
    raise RuntimeError("Ingen gyldige GPS-punkter i antennelog")

# ---------------------------------------------------------
# RSRP
# ---------------------------------------------------------
radio_rows = []
rsrp_pattern = re.compile(r'"rsrp"\s*:\s*"(-?\d+[.,]\d+)\s*dBm"', re.I)

with open(RADIO_FILE, encoding="utf-8", errors="ignore") as f:
    for line in f:
        m = rsrp_pattern.search(line)
        if m:
            radio_rows.append(
                float(m.group(1).replace(",", "."))
            )

radio_df = pd.DataFrame({"rsrp_dbm": radio_rows})

if radio_df.empty:
    raise RuntimeError("Ingen RSRP-målinger fundet")

# ---------------------------------------------------------
# BEREGNING – STABILISERET UDADKØRSEL
# ---------------------------------------------------------
rows = []
last_distance = None
count = min(len(antenna_df), len(radio_df))

for i in range(count):
    a = antenna_df.iloc[i]
    r = radio_df.iloc[i]

    ground = haversine(DRONE_LAT, DRONE_LON, a.lat, a.lon)

    # Skip over-sampling (forhindrer "står stille"-artefakter)
    if last_distance is not None and ground - last_distance < MIN_DISTANCE_STEP:
        continue

    last_distance = ground

    dist_3d = math.sqrt(ground**2 + DZ**2)
    az = azimuth(DRONE_LAT, DRONE_LON, a.lat, a.lon)
    elev_geom = math.degrees(math.atan2(DZ, ground))
    elev_ant = elev_geom + ANTENNA_TILT_DEG

    rows.append({
        "antenna_lat": a.lat,
        "antenna_lon": a.lon,
        "distance_ground_m": ground,
        "distance_3d_m": dist_3d,
        "azimuth_from_drone_deg": az,
        "elevation_geom_deg": elev_geom,
        "elevation_in_antenna_frame_deg": elev_ant,
        "rsrp_dbm": r.rsrp_dbm
    })

df = pd.DataFrame(rows)

# ---------------------------------------------------------
# AFGRÆNS UDADKØRSEL KORREKT
# Stop ved FØRSTE gang maksimal afstand nås
# ---------------------------------------------------------
start_idx = df["distance_ground_m"].idxmin()
df = df.loc[start_idx:].reset_index(drop=True)

max_dist = df["distance_ground_m"].max()

# Find første forekomst af maksimal afstand (GPS-tolerant)
idx_first_max = df[df["distance_ground_m"] >= max_dist * 0.999].index[0]

df_outgoing = df.loc[:idx_first_max].reset_index(drop=True)

print(
    f"Bruger {len(df_outgoing)} målinger "
    f"(~0 m → første maxafstand: {max_dist:.0f} m)"
)

# ---------------------------------------------------------
# OUTPUT
# ---------------------------------------------------------
OUT_FILE = os.path.join(
    BASE_DIR, "antenna_3d_analysis_outgoing.csv"
)
df_outgoing.to_csv(OUT_FILE, index=False)

print("FÆRDIG")
print(f"Output gemt: {OUT_FILE}")
