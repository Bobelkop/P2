# =========================================================
# RSRP vs log(distance)
# - Antenne-gain korrektion
# - Fjerner KUN den sidste kraftige opadgående hale (~2.2 km)
# - Regression + path-loss eksponent n
# =========================================================

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ---------------------------------------------------------
# LOAD DATA
# ---------------------------------------------------------
df = pd.read_csv("antenna_3d_analysis_binned.csv")

# Absolut elevationsvinkel
df["elevation_abs_deg"] = np.abs(df["elevation_geom_deg"])

# ---------------------------------------------------------
# ANTENNEMØNSTER (0–90°)
# ---------------------------------------------------------
antenna_pattern = {
    0: 0,   5: 0,   10: 0,  15: 0,
    20: 2,  25: 4,  30: 6,  35: 10,
    40: 14, 45: 18, 50: 17, 55: 16,
    60: 15, 65: 15, 70: 15, 75: 15,
    80: 16, 85: 17, 90: 18,
}

def antenna_correction(angle_deg):
    angle_deg = min(max(angle_deg, 0), 90)
    rounded = int(5 * round(angle_deg / 5))
    return antenna_pattern.get(rounded, 0)

df["antenna_corr_db"] = df["elevation_abs_deg"].apply(antenna_correction)
df["rsrp_corrected_dbm"] = df["rsrp_dbm"] + df["antenna_corr_db"]

# ---------------------------------------------------------
# SORTÉR EFTER AFSTAND
# ---------------------------------------------------------
df = df.sort_values("distance_ground_m").reset_index(drop=True)

# ---------------------------------------------------------
# IDENTIFICÉR OG FJERN KUN DEN SIDSTE OPADGÅENDE HALE
# ---------------------------------------------------------
window = 25  # glidende middel (passer til dit dataset)

df["rsrp_smooth"] = (
    df["rsrp_corrected_dbm"]
    .rolling(window=window, center=True)
    .mean()
)

# Find index for sidste minimum i den glatte kurve
last_min_idx = df["rsrp_smooth"].idxmin()

# Behold ALT frem til sidste minimum
df_fit = df.loc[:last_min_idx].copy()

print(
    f"✅ Fjernet {len(df) - len(df_fit)} sidste punkter "
    f"(cut ved {df.loc[last_min_idx, 'distance_ground_m']:.0f} m)"
)

# ---------------------------------------------------------
# REGRESSION: RSRP = a * log10(d) + b
# ---------------------------------------------------------
x = np.log10(df_fit["distance_ground_m"].values)
y = df_fit["rsrp_corrected_dbm"].values

a, b = np.polyfit(x, y, 1)
n = -a / 10

x_fit = np.linspace(x.min(), x.max(), 300)
y_fit = a * x_fit + b

# ---------------------------------------------------------
# PLOT
# ---------------------------------------------------------
plt.figure(figsize=(9, 6))

# Alle punkter (inkl. dem der fjernes)
plt.scatter(
    df["distance_ground_m"],
    df["rsrp_corrected_dbm"],
    s=30,
    alpha=0.35,
    label="Alle målinger"
)

# Punkter brugt til regression
plt.scatter(
    df_fit["distance_ground_m"],
    df_fit["rsrp_corrected_dbm"],
    s=40,
    alpha=0.9,
    label="Anvendt til regression"
)

# Regressionslinje
plt.plot(
    10**x_fit,
    y_fit,
    color="red",
    linewidth=2.5,
    label=f"Regression (n = {n:.2f})"
)

plt.xscale("log")
plt.xlabel("Horisontal afstand [m] (log)")
plt.ylabel("RSRP [dBm]")
plt.title(
    "RSRP som funktion af log‑afstand\n"
    "korrigeret for antenne‑gain\n"
    "(kun sidste interferensdominerede hale fjernet)"
)

plt.grid(True, which="both", linestyle="--", alpha=0.5)
plt.legend()
plt.tight_layout()
plt.show()

print(f"✅ Path-loss eksponent n = {n:.2f}")