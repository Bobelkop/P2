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

# ===================== KONFIGURATION =====================

REFERENCE_DATE = "2026-05-01"
UTC_OFFSET_HOURS = 2

DRONE_HEIGHT_M = 120.0
ANTENNA_HEIGHT_M = 4.0

MIN_CONSEC_RISE = 3        # stop udflyvning hvis RSRP stiger så mange gange i træk
MIN_POINTS = 20            # minimum datapunkter til regression

# ===================== ANTENNE-GAIN (KUN FRA DIN TABEL) =====================
# Kolonnen "Korrektion" (dB) trækkes FRA RSRP.

ANGLE_DEG = np.array([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60])
GAIN_CORR_DB = np.array([0, 0,  0,  0,  2,  4,  6, 10, 14, 18, 17, 16, 15])

def antenna_gain_correction(theta_deg: np.ndarray) -> np.ndarray:
    theta = np.clip(theta_deg, ANGLE_DEG.min(), ANGLE_DEG.max())
    return np.interp(theta, ANGLE_DEG, GAIN_CORR_DB)

# ===================== TID =====================

def gps_hhmmss_to_epoch(hhmmss: str) -> int:
    hh, mm, ss = int(hhmmss[:2]), int(hhmmss[2:4]), int(hhmmss[4:6])
    dt = datetime.fromisoformat(f"{REFERENCE_DATE}T{hh:02d}:{mm:02d}:{ss:02d}")
    return int((dt + timedelta(hours=UTC_OFFSET_HOURS)).timestamp())

def radio_ts_to_epoch(ts: str) -> int:
    return int(datetime.fromisoformat(ts).timestamp())

# ===================== PARSING =====================

def parse_gpgga(line: str):
    if "$GPGGA" not in line:
        return None
    try:
        p = line.split("$GPGGA,")[1].split(",")
        hhmmss = p[0][:6]
        lat = float(p[1][:2]) + float(p[1][2:]) / 60
        lon = float(p[3][:3]) + float(p[3][3:]) / 60
        if p[2] == "S": lat = -lat
        if p[4] == "W": lon = -lon
        return gps_hhmmss_to_epoch(hhmmss), (lat, lon)
    except Exception:
        return None

def load_gps(path: Path):
    out = {}
    with path.open(errors="ignore") as f:
        for line in f:
            p = parse_gpgga(line)
            if p:
                out[p[0]] = p[1]
    return out

def load_radio(path: Path):
    out = {}
    with path.open(errors="ignore") as f:
        for line in f:
            if not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            ts = obj.get("timestamp")
            m = re.search(r"-?\d+\.?\d*", str(obj.get("rsrp")))
            if ts and m:
                out[radio_ts_to_epoch(ts)] = float(m.group())
    return out

# ===================== GEOMETRI =====================

def geometry(p_bs, p_dr):
    d_h = geodesic(p_bs, p_dr).meters
    dz = DRONE_HEIGHT_M - ANTENNA_HEIGHT_M
    d_3d = np.sqrt(d_h**2 + dz**2)
    theta = np.degrees(np.arctan2(dz, d_h))  # 0° = horisontal
    return d_h, d_3d, theta

# ===================== FILTRERING (KUN UDFLYVNING) =====================

def filter_outgoing(d3: np.ndarray, rsrp: np.ndarray) -> np.ndarray:
    keep = [0]
    rise = 0
    for i in range(1, len(d3)):
        if d3[i] >= d3[i-1]:           # stadig væk fra mast
            if rsrp[i] > rsrp[i-1]:    # link bliver bedre igen?
                rise += 1
                if rise >= MIN_CONSEC_RISE:
                    break
            else:
                rise = 0
            keep.append(i)
        else:
            break
    return np.array(keep)

# ===================== ANALYSE =====================

def analyze(site: str, root: Path):

    gps_bs = load_gps(root / "pc_thy" / f"{site}.log")
    gps_dr = load_gps(list((root / "pi_thy" / site).glob("*gps.log"))[0])
    radio  = load_radio(list((root / "pi_thy" / site).glob("*radio.log"))[0])

    d_h, d_3d, theta, rsrp = [], [], [], []

    for t in gps_bs:
        if t in gps_dr and t in radio:
            dh, d3, th = geometry(gps_bs[t], gps_dr[t])
            d_h.append(dh)
            d_3d.append(d3)
            theta.append(th)
            rsrp.append(radio[t])

    d_h = np.array(d_h)
    d_3d = np.array(d_3d)
    theta = np.array(theta)
    rsrp = np.array(rsrp)

    # sorter efter 3D-afstand
    idx = np.argsort(d_3d)
    d_h, d_3d, theta, rsrp = d_h[idx], d_3d[idx], theta[idx], rsrp[idx]

    # filtrer til kun udflyvning
    idx = filter_outgoing(d_3d, rsrp)
    d_h, d_3d, theta, rsrp = d_h[idx], d_3d[idx], theta[idx], rsrp[idx]

    if len(d_h) < MIN_POINTS:
        print(f"{site}: for få datapunkter")
        return

    # antenne-korrektion (fra tabel)
    G_corr = antenna_gain_correction(theta)
    rsrp_corr = rsrp - G_corr

    # ===================== REGRESSION =====================
    # Regression på HORISONTAL afstand (stabil X)
    X = np.log10(d_h).reshape(-1, 1)
    reg = LinearRegression().fit(X, rsrp_corr)
    n = -reg.coef_[0] / 10
    r2 = r2_score(rsrp_corr, reg.predict(X))

    # ===================== PLOT =====================

    xh = np.logspace(np.log10(d_h.min()), np.log10(d_h.max()), 300)

    plt.figure(figsize=(9,6))
    plt.scatter(d_h, rsrp, alpha=0.3, label="Målt RSRP")
    plt.scatter(d_h, rsrp_corr, alpha=0.6, label="Korrigeret (antenne‑gain)")
    plt.plot(xh, reg.predict(np.log10(xh).reshape(-1,1)),
             color="black", lw=2.5,
             label=f"Regression: n={n:.2f}, R²={r2:.2f}")

    plt.xscale("log")
    plt.xlabel("Horisontal afstand (m) [log]")
    plt.ylabel("RSRP (dBm)")
    plt.title(f"{site} – Udflyvning (3D geometri + antenne‑gain)")
    plt.grid(True, which="both", ls="--", alpha=0.4)
    plt.legend()
    plt.tight_layout()
    plt.savefig(root / f"{site}_FINAL_3D_GAIN_TABLE.png")
    plt.close()

    print(f"{site}: n={n:.2f}, R²={r2:.2f}")

# ===================== KØR =====================

if __name__ == "__main__":
    ROOT = Path("DATA/meas_thy")
    analyze("thy_1", ROOT)
