from __future__ import annotations

import json
import re
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from pathlib import Path
from geopy.distance import geodesic
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

# ============================================================
# KONFIGURATION
# ============================================================

REFERENCE_DATE = "2026-05-01"
UTC_OFFSET_HOURS = 2

DRONE_HEIGHT_M = 120.0
ANTENNA_HEIGHT_M = 4.0

MANUAL_BP_3D_M = 450.0      # manuelt breakpoint (3D)
AUTO_BP_MIN_H_M = 30.0      # auto BP må ikke før 30 m horisontalt
MIN_3D_SPAN_M = 40.0        # min 3D-spænd for før-BP regression
MIN_POINTS = 10

# ============================================================
# TID
# ============================================================

def gps_hhmmss_to_epoch(hhmmss):
    hh, mm, ss = int(hhmmss[:2]), int(hhmmss[2:4]), int(hhmmss[4:6])
    dt = datetime.fromisoformat(f"{REFERENCE_DATE}T{hh:02d}:{mm:02d}:{ss:02d}")
    return int((dt + timedelta(hours=UTC_OFFSET_HOURS)).timestamp())

def radio_ts_to_epoch(ts):
    return int(datetime.fromisoformat(ts).timestamp())

# ============================================================
# GPS + RADIO
# ============================================================

def parse_gpgga(line):
    if "$GPGGA" not in line:
        return None
    p = line.split("$GPGGA,")[1].split(",")
    hhmmss = p[0][:6]
    lat = float(p[1][:2]) + float(p[1][2:]) / 60
    lon = float(p[3][:3]) + float(p[3][3:]) / 60
    if p[2] == "S": lat = -lat
    if p[4] == "W": lon = -lon
    return gps_hhmmss_to_epoch(hhmmss), (lat, lon)

def load_gps(path):
    d = {}
    with path.open(errors="ignore") as f:
        for line in f:
            p = parse_gpgga(line)
            if p:
                d[p[0]] = p[1]
    return d

def load_radio(path):
    d = {}
    with path.open(errors="ignore") as f:
        for line in f:
            if not line.startswith("{"):
                continue
            obj = json.loads(line)
            ts = obj.get("timestamp")
            m = re.search(r"-?\d+\.?\d*", str(obj.get("rsrp")))
            if ts and m:
                d[radio_ts_to_epoch(ts)] = float(m.group())
    return d

# ============================================================
# AFSTAND (3D)
# ============================================================

def distance_3d(p1, p2):
    d_h = geodesic(p1, p2).meters
    dz = DRONE_HEIGHT_M - ANTENNA_HEIGHT_M
    return np.sqrt(d_h**2 + dz**2)

# ============================================================
# REGRESSION (LOG-3D)
# ============================================================

def log_reg_3d(d3, r):
    X = np.log10(d3).reshape(-1,1)
    reg = LinearRegression().fit(X, r)
    y = reg.predict(X)
    n = -reg.coef_[0] / 10
    return reg, n, r2_score(r, y)

# ============================================================
# AUTO BP (3D, NÆRFELT BLOKERET)
# ============================================================

def find_auto_bp_3d(d3, r):
    dz = DRONE_HEIGHT_M - ANTENNA_HEIGHT_M
    min_d3 = np.sqrt(AUTO_BP_MIN_H_M**2 + dz**2)

    idx = np.argsort(d3)
    d3 = d3[idx]
    r  = r[idx]

    valid = d3 >= min_d3
    d3 = d3[valid]
    r  = r[valid]

    if len(d3) < 40:
        return np.median(d3)

    r_sm = np.convolve(r, np.ones(25)/25, mode="valid")
    d3_sm = d3[:len(r_sm)]

    slope = np.diff(r_sm) / np.diff(d3_sm)
    for i, s in enumerate(slope):
        if s < -0.05:
            return d3_sm[i]

    return np.median(d3)

# ============================================================
# PLOT
# ============================================================

def make_plot(d3, r, bp3, title, path):
    mask_near = d3 <= bp3
    mask_far  = d3 >  bp3

    plt.figure(figsize=(9,6))
    plt.scatter(d3, r, s=20, alpha=0.35, label="Målt RSRP")

    # ---------- FØR BP (3D, KONTROLLERET) ----------
    if mask_near.sum() >= MIN_POINTS:
        span = d3[mask_near].max() - d3[mask_near].min()
        if span >= MIN_3D_SPAN_M:
            reg1, n1, r21 = log_reg_3d(d3[mask_near], r[mask_near])
            x1 = np.logspace(np.log10(d3[mask_near].min()),
                             np.log10(d3[mask_near].max()), 200)
            plt.plot(
                x1,
                reg1.predict(np.log10(x1).reshape(-1,1)),
                color="green",
                label=f"Før BP (3D): n={n1:.2f}"
            )

    # ---------- EFTER BP (3D) ----------
    if mask_far.sum() >= MIN_POINTS:
        reg2, n2, r22 = log_reg_3d(d3[mask_far], r[mask_far])
        x2 = np.logspace(np.log10(d3[mask_far].min()),
                         np.log10(d3[mask_far].max()), 300)
        plt.plot(
            x2,
            reg2.predict(np.log10(x2).reshape(-1,1)),
            color="orange",
            label=f"Efter BP (3D): n={n2:.2f}"
        )

    plt.axvline(bp3, color="black", ls="--", label=f"BP ≈ {bp3:.1f} m")
    plt.xscale("log")
    plt.xlabel("3D‑afstand (m) [log]")
    plt.ylabel("RSRP (dBm)")
    plt.title(title)
    plt.grid(True, which="both", ls="--", alpha=0.4)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path)
    plt.close()

# ============================================================
# KØR
# ============================================================

def analyze_site(site, root):
    gps_pc = load_gps(root / "pc_thy" / f"{site}.log")
    gps_pi = load_gps(list((root / "pi_thy" / site).glob("*gps.log"))[0])
    radio  = load_radio(list((root / "pi_thy" / site).glob("*radio.log"))[0])

    d3, r = [], []
    for t in gps_pc:
        if t in gps_pi and t in radio:
            d3.append(distance_3d(gps_pc[t], gps_pi[t]))
            r.append(radio[t])

    d3 = np.array(d3)
    r  = np.array(r)

    auto_bp3 = find_auto_bp_3d(d3, r)

    make_plot(d3, r, auto_bp3,
              f"{site} – Automatisk BP (3D)",
              root / f"{site}_AUTO_BP_3D_BOTH.png")

    make_plot(d3, r, MANUAL_BP_3D_M,
              f"{site} – Manuelt BP (3D)",
              root / f"{site}_MANUAL_BP_3D_BOTH.png")

    print(f"{site}: auto BP ≈ {auto_bp3:.1f} m | manuel BP = {MANUAL_BP_3D_M:.1f} m")

if __name__ == "__main__":
    ROOT = Path("DATA/meas_thy")
    for site in ["thy_1", "thy_2", "thy_3"]:
        analyze_site(site, ROOT)
