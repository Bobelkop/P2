# =========================================================
# ANALYSE & PLOTS
# - Elevation vs distance
# - RSRP vs distance
# - Antenne-korrigeret RSRP
# (linje + datapunkter langs linjen)
# =========================================================

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ---------------------------------------------------------
# LOAD DATA
# ---------------------------------------------------------
CSV_FILE = "antenna_3d_analysis_outgoing.csv"
df = pd.read_csv(CSV_FILE)

# Brug absolut elevation (vinkel fra horisontal)
df["elevation_abs_deg"] = np.abs(df["elevation_geom_deg"])

# ---------------------------------------------------------
# ANTENNEMØNSTER (fra din tabel)
# ---------------------------------------------------------
antenna_pattern = {
    0: 0,
    5: 0,
    10: 0,
    15: 0,
    20: 2,
    25: 4,
    30: 6,
    35: 10,
    40: 14,
    45: 18,
    50: 17,
    55: 16,
    60: 15,
}

def antenna_correction(angle_deg):
    angle_deg = min(max(angle_deg, 0), 60)
    rounded = int(5 * round(angle_deg / 5))
    return antenna_pattern.get(rounded, 0)

df["antenna_corr_db"] = df["elevation_abs_deg"].apply(antenna_correction)

# Korrigeret RSRP
df["rsrp_corrected_dbm"] = df["rsrp_dbm"] + df["antenna_corr_db"]

# ---------------------------------------------------------
# PLOT 1: Elevation vs Distance (LINJE + PUNKTER)
# ---------------------------------------------------------
plt.figure(figsize=(8, 5))

plt.plot(
    df["distance_ground_m"],
    df["elevation_abs_deg"],
    linewidth=2,
    label="Geometrisk sammenhæng"
)

plt.scatter(
    df["distance_ground_m"],
    df["elevation_abs_deg"],
    s=20,
    alpha=0.8,
    zorder=3,
    label="Målepunkter"
)

plt.xlabel("Afstand fra drone [m]")
plt.ylabel("Absolut elevationsvinkel [°]")
plt.title("Elevationsvinkel som funktion af afstand")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.show()

# ---------------------------------------------------------
# PLOT 2: RSRP vs Distance (LINJE + PUNKTER)
# ---------------------------------------------------------
plt.figure(figsize=(8, 5))

plt.plot(
    df["distance_ground_m"],
    df["rsrp_dbm"],
    linewidth=2,
    label="RSRP (trend)"
)

plt.scatter(
    df["distance_ground_m"],
    df["rsrp_dbm"],
    s=20,
    alpha=0.7,
    zorder=3,
    label="RSRP (målinger)"
)

plt.xlabel("Afstand fra drone [m]")
plt.ylabel("RSRP [dBm]")
plt.title("RSRP som funktion af afstand")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.show()

# ---------------------------------------------------------
# PLOT 3: Korrigeret RSRP vs Distance (LINJE + PUNKTER)
# ---------------------------------------------------------
plt.figure(figsize=(8, 5))

plt.plot(
    df["distance_ground_m"],
    df["rsrp_corrected_dbm"],
    linewidth=2,
    color="darkred",
    label="RSRP (antennerektion)"
)

plt.scatter(
    df["distance_ground_m"],
    df["rsrp_corrected_dbm"],
    s=20,
    color="darkred",
    alpha=0.7,
    zorder=3,
    label="Målepunkter (korrigeret)"
)

plt.xlabel("Afstand fra drone [m]")
plt.ylabel("RSRP [dBm]")
plt.title("Antennemønster-korrigeret RSRP")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.show()

print("✅ Analyse og plots færdige (linje + datapunkter)")