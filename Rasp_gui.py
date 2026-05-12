import FreeSimpleGUI as sg
import Rasp as rasp
import Datarater as datarater
import os
import numpy as np
import matplotlib.pyplot as plt



FARVE_BAGGRUND = "#F5F7FA"
FARVE_PANEL = "#FFFFFF"
FARVE_FELT = "#EAF4FF"
FARVE_KNAP = "#007AFF"
FARVE_TEKST = "#1D1D1F"
FARVE_KANT = "#D6EAFB"

LB_C = 3e8
LB_D0 = 1.0

LB_UPLINK_FELTER = [
    ("Tx power", "-LB-UL-TX-", 35.0, "dBm"),
    ("Tx ant. gain", "-LB-UL-TX-GAIN-", 11.0, "dBi"),
    ("Tx kabeltab", "-LB-UL-TX-LOSS-", 2.0, "dB"),
    ("Rx ant. gain", "-LB-UL-RX-GAIN-", -5.0, "dBi"),
    ("Rx kabeltab", "-LB-UL-RX-LOSS-", 0.5, "dB"),
    ("Sensitivity", "-LB-UL-SENS-", -102.0, "dBm"),
]

LB_DOWNLINK_FELTER = [
    ("Tx power", "-LB-DL-TX-", 23.0, "dBm"),
    ("Tx ant. gain", "-LB-DL-TX-GAIN-", -5.0, "dBi"),
    ("Tx kabeltab", "-LB-DL-TX-LOSS-", 0.5, "dB"),
    ("Rx ant. gain", "-LB-DL-RX-GAIN-", 11.0, "dBi"),
    ("Rx kabeltab", "-LB-DL-RX-LOSS-", 2.0, "dB"),
    ("Sensitivity", "-LB-DL-SENS-", -102.0, "dBm"),
]

LB_FAELLES_FELTER = [
    ("Øvrige tab", "-LB-MISC-", 0.0, "dB"),
    ("Fade margin", "-LB-FADE-", 10.0, "dB"),
    ("Frekvens", "-LB-FREQ-", 3779.0, "MHz"),
    ("Min. afstand", "-LB-MIN-DIST-", 118.0, "m"),
    ("Plotafstand", "-LB-PLOT-KM-", 50.0, "km"),
    ("gNB-højde h_t", "-LB-H-GNB-", 1.5, "m"),
    ("UE-højde h_r", "-LB-H-UE-", 120.0, "m"),
    ("Bygningshøjde h", "-LB-H-BLD-", 5.0, "m"),
    ("CI n", "-LB-CI-N-", 2.0, "-"),
    ("Shadow fading", "-LB-SHADOW-", 0.0, "dB"),
    ("CIH b_tx", "-LB-CIH-BTX-", 0.03, "-"),
    ("CIH h_B0", "-LB-CIH-HB0-", 35.0, "m"),
]

GRAF_KNAPPER = {
    "-VIS-GRAF-RSRP-": "rsrp",
    "-VIS-GRAF-SNR-": "snr",
    "-VIS-GRAF-PATHLOSS-": "pathloss",
    "-VIS-GRAF-RSRP-15-": "rsrp_15m",
    "-VIS-GRAF-SNR-15-": "snr_15m",
    "-VIS-GRAF-PATHLOSS-15-": "pathloss_15m",
    "-VIS-GRAF-RSRP-120-": "rsrp_120m",
    "-VIS-GRAF-SNR-120-": "snr_120m",
    "-VIS-GRAF-PATHLOSS-120-": "pathloss_120m",
}

DATA_HEADINGS = [
    "Test",
    "Koordinater",
    "Afstand (km)",
    "Målt RSRP",
    "Målt SNR",
    "Teoretisk RSRP",
    "Teoretisk SNR",
    "Afvigelse SNR",
    "Teoretisk afvigelse RSRP (dB)",
]

DATA_COL_WIDTHS = [13, 16, 10, 10, 9, 11, 11, 12, 20]


def _to_float(value, default):
    value = str(value if value is not None else "").strip().replace(",", ".")
    if value == "":
        return default
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"Ugyldigt tal: {value}") from None


def _skal_vaere_positiv(value, label):
    if not np.isfinite(value) or value <= 0:
        raise ValueError(f"{label} skal være større end 0")


def _linkbudget_from_gui(values):
    carrier_frequency = _to_float(values["-CF-"], float(rasp.Carrier_Frequency))
    gnb_tx_power = _to_float(values["-TXP-"], float(rasp.gNB_transmit_power))
    antenna_gain = _to_float(values["-GAIN-"], float(rasp.Antenne_gain))
    bw_mhz = _to_float(values["-BW-"], float(rasp.BW))
    scs_khz = _to_float(values["-SCS-"], float(rasp.Sub_carrier_spacing))
    thermal_noise = _to_float(values["-TN-"], float(rasp.Thermal_Noise))
    noise_figure = _to_float(values["-NF-"], float(rasp.NoiseFigure))

    _skal_vaere_positiv(carrier_frequency, "Carrier MHz")
    _skal_vaere_positiv(bw_mhz, "BW MHz")
    _skal_vaere_positiv(scs_khz, "SCS kHz")
    if not np.isfinite(gnb_tx_power) or not np.isfinite(antenna_gain):
        raise ValueError("Tx power og gain skal være gyldige tal")
    if not np.isfinite(thermal_noise) or not np.isfinite(noise_figure):
        raise ValueError("Thermal noise og noise figure skal være gyldige tal")

    tx_eirp = gnb_tx_power + antenna_gain
    re_power = 10 * np.log10(10 ** (tx_eirp / 10) * (scs_khz) / (bw_mhz * 0.9 * 1000))

    return {
        "carrier_frequency": carrier_frequency,
        "bw_mhz": bw_mhz,
        "scs_khz": scs_khz,
        "thermal_noise": thermal_noise,
        "noise_figure": noise_figure,
        "re_power": re_power,
    }


def _rapport_3gpp(values, afstand, height_m=None):
    lb = _linkbudget_from_gui(values)
    h_ue = height_m if height_m is not None else _to_float(values.get("-LB-H-UE-"), 120.0)
    p = {
        "freq_mhz": lb["carrier_frequency"],
        "h_gnb": _to_float(values.get("-LB-H-GNB-"), 1.5),
        "h_ue": float(h_ue),
        "h_bld": _to_float(values.get("-LB-H-BLD-"), 5.0),
    }
    _skal_vaere_positiv(p["h_gnb"], "gNB-højde")
    _skal_vaere_positiv(p["h_ue"], "UE-højde")
    _skal_vaere_positiv(p["h_bld"], "Bygningshøjde")
    pathloss = float(_link_3gpp(np.array([afstand]), p)[0])
    rsrp = lb["re_power"] - pathloss
    return pathloss, rsrp


def _run_t_mode(values):
    afstand = _to_float(values["-AFSTAND-T-"], 1.0)
    _skal_vaere_positiv(afstand, "Afstand")
    lb = _linkbudget_from_gui(values)

    fspl = rasp.Teoretisk_RASP_FSPL(afstand, lb["carrier_frequency"], lb["re_power"])
    rma = _rapport_3gpp(values, afstand)
    snr_fspl = rasp.Teoretisk_SNR(fspl[1], lb["thermal_noise"], lb["noise_figure"], lb["scs_khz"])
    snr_rma = rasp.Teoretisk_SNR(rma[1], lb["thermal_noise"], lb["noise_figure"], lb["scs_khz"])

    lines = [
        "Teoretisk mode",
        "--------------------------------------------------",
        f"Afstand: {afstand:.2f} km",
        f"Carrier: {lb['carrier_frequency']:.0f} MHz | BW: {lb['bw_mhz']:.1f} MHz | SCS: {lb['scs_khz']:.1f} kHz",
        "",
        "FSPL:",
        f"Pathloss: {fspl[0]:.2f} dB",
        f"RSRP: {fspl[1]:.2f} dBm",
        f"Teoretisk SNR: {snr_fspl:.2f} dB",
        "",
        "3GPP RMa LOS:",
        f"Pathloss: {rma[0]:.2f} dB",
        f"RSRP: {rma[1]:.2f} dBm",
        f"Teoretisk SNR: {snr_rma:.2f} dB",
    ]
    return "\n".join(lines)


def _run_m_mode(values):
    drone_input = (values["-DRONE-M-"] or "").strip()
    drone_lokation = drone_input if drone_input else f"{rasp.Drone_Lokation[0]},{rasp.Drone_Lokation[1]}"

    gnb_input = (values["-GNB-M-"] or "").strip()
    gnb_lokation = gnb_input if gnb_input else "57.0180391,9.7602773"
    lb = _linkbudget_from_gui(values)
    afstand_manual = rasp.Afstandsformel(drone_lokation, gnb_lokation)

    resultater = rasp.alle_målinger_fra_json()
    if not resultater:
        raise ValueError("Ingen måledata fundet til standard RSRP/SNR")

    rsrp_ref = sum(item["rsrp"] for item in resultater.values()) / len(resultater)
    snr_ref = sum(item["snr"] for item in resultater.values()) / len(resultater)

    målt_rsrp_txt = (values.get("-M-RSRP-") or "").strip()
    målt_snr_txt = (values.get("-M-SNR-") or "").strip()
    målt_rsrp = _to_float(målt_rsrp_txt, rsrp_ref)
    målt_snr = _to_float(målt_snr_txt, snr_ref)
    manuel_input = (målt_rsrp_txt != "") or (målt_snr_txt != "")

    fspl = rasp.Teoretisk_RASP_FSPL(afstand_manual, lb["carrier_frequency"], lb["re_power"])
    rma = _rapport_3gpp(values, afstand_manual)
    snr_fspl = rasp.Teoretisk_SNR(fspl[1], lb["thermal_noise"], lb["noise_figure"], lb["scs_khz"])
    snr_rma = rasp.Teoretisk_SNR(rma[1], lb["thermal_noise"], lb["noise_figure"], lb["scs_khz"])
    afv_rsrp_fspl = rasp.Afvigelse_Af_Målinger_På_Teori_RSRP(målt_rsrp, fspl[1])
    afv_rsrp_rma = rasp.Afvigelse_Af_Målinger_På_Teori_RSRP(målt_rsrp, rma[1])
    afv_snr_fspl = snr_fspl - målt_snr
    afv_snr_rma = snr_rma - målt_snr

    lines = [
        "Måle-mode",
        "=============================================================",
        f"Drone lokation (manuel): ({drone_lokation})",
        f"gNB lokation (manuel): ({gnb_lokation})",
        f"Afstand (manuel): {afstand_manual:.2f} km",
        f"Carrier: {lb['carrier_frequency']:.0f} MHz | BW: {lb['bw_mhz']:.1f} MHz | SCS: {lb['scs_khz']:.1f} kHz",
        (
            f"Målt reference (manuel): RSRP {målt_rsrp:.2f} dBm | SNR {målt_snr:.2f} dB"
            if manuel_input
            else f"Målt reference (fra fil): RSRP {målt_rsrp:.2f} dBm | SNR {målt_snr:.2f} dB"
        ),
        "=============================================================",
        "FSPL",
        f"  Pathloss: {fspl[0]:.2f} dB",
        f"  RSRP: {fspl[1]:.2f} dBm",
        f"  SNR: {snr_fspl:.2f} dB",
        f"  Afvigelse ift SNR: {afv_snr_fspl:.2f} dB",
        f"  Afvigelse ift. RSRP-måling: {afv_rsrp_fspl:.2f} dB",
        "",
        "3GPP RMa LOS",
        f"  Pathloss: {rma[0]:.2f} dB",
        f"  RSRP: {rma[1]:.2f} dBm",
        f"  SNR: {snr_rma:.2f} dB",
        f"  Afvigelse ift SNR: {afv_snr_rma:.2f} dB",
        f"  Afvigelse ift. RSRP-måling: {afv_rsrp_rma:.2f} dB",
        "",
    ]

    return "\n".join(lines)


def _build_data_tables(values):
    lb = _linkbudget_from_gui(values)
    resultater = rasp.alle_målinger_fra_json()
    sorteret = sorted(
        resultater.items(),
        key=lambda item: (
            item[1]["testnr"] is None,
            item[1]["testnr"] if item[1]["testnr"] is not None else 9999,
            item[0],
        ),
    )

    rows_by_height = {
        "15m": {"fspl": [], "rma": []},
        "120m": {"fspl": [], "rma": []},
    }

    def _height_group(height_value):
        if height_value is None:
            return "120m"
        h = float(height_value)
        if abs(h - 15.0) < 0.6:
            return "15m"
        return "120m"

    for filnavn, data in sorteret:
        lat_lon = data.get("lat_lon")
        group_key = _height_group(data.get("height_m"))

        if data.get("testnr") is not None:
            testnr = data["testnr"]
            height = data.get("height_m")
            if height is not None:
                if float(height).is_integer():
                    test_label = f"test{testnr} {int(height)}m"
                else:
                    test_label = f"test{testnr} {height:.1f}m"
            else:
                test_label = f"test{testnr}"
        else:
            test_label = filnavn

        målt_rsrp = data["rsrp"]
        målt_snr = data["snr"]

        if lat_lon is None:
            row = [
                test_label,
                "-",
                "-",
                f"{målt_rsrp:.2f}",
                f"{målt_snr:.2f}",
                "-",
                "-",
                "-",
                "-",
            ]
            rows_by_height[group_key]["fspl"].append(row)
            rows_by_height[group_key]["rma"].append(row.copy())
            continue

        afstand = data.get("afstand")
        if afstand is None:
            afstand = rasp.Afstandsformel(rasp.Drone_Lokation, lat_lon)
        coord_txt = f"{lat_lon[0]:.6f},{lat_lon[1]:.6f}"
        fspl = rasp.Teoretisk_RASP_FSPL(afstand, lb["carrier_frequency"], lb["re_power"])
        rma = _rapport_3gpp(values, afstand, data.get("height_m"))
        snr_fspl = rasp.Teoretisk_SNR(fspl[1], lb["thermal_noise"], lb["noise_figure"], lb["scs_khz"])
        snr_rma = rasp.Teoretisk_SNR(rma[1], lb["thermal_noise"], lb["noise_figure"], lb["scs_khz"])

        rows_by_height[group_key]["fspl"].append([
            test_label,
            coord_txt,
            f"{afstand:.2f}",
            f"{målt_rsrp:.2f}",
            f"{målt_snr:.2f}",
            f"{fspl[1]:.2f}",
            f"{snr_fspl:.2f}",
            f"{snr_fspl - målt_snr:.2f}",
            f"{rasp.Afvigelse_Af_Målinger_På_Teori_RSRP(målt_rsrp, fspl[1]):.2f}",
        ])

        rows_by_height[group_key]["rma"].append([
            test_label,
            coord_txt,
            f"{afstand:.2f}",
            f"{målt_rsrp:.2f}",
            f"{målt_snr:.2f}",
            f"{rma[1]:.2f}",
            f"{snr_rma:.2f}",
            f"{snr_rma - målt_snr:.2f}",
            f"{rasp.Afvigelse_Af_Målinger_På_Teori_RSRP(målt_rsrp, rma[1]):.2f}",
        ])

    count_15 = len(rows_by_height["15m"]["fspl"])
    count_120 = len(rows_by_height["120m"]["fspl"])
    status = f"Viser {count_15} testfiler på 15 m og {count_120} testfiler på 120 m."
    return rows_by_height, status


def _run_graph_mode(values):
    lb = _linkbudget_from_gui(values)
    graf_stier = rasp.Lav_Grafer(
        carrier_frequency=lb["carrier_frequency"],
        re_power=lb["re_power"],
        thermal_noise=lb["thermal_noise"],
        noise_figure=lb["noise_figure"],
        scs_khz=lb["scs_khz"],
    )

    lines = [
        "Grafer opdateret",
        "--------------------------------------------------",
        f"RSRP graf: {graf_stier['rsrp']}",
        f"SNR graf: {graf_stier['snr']}",
        f"Pathloss graf: {graf_stier['pathloss']}",
        f"RSRP 15 m graf: {graf_stier['rsrp_15m']}",
        f"SNR 15 m graf: {graf_stier['snr_15m']}",
        f"Pathloss 15 m graf: {graf_stier['pathloss_15m']}",
        f"RSRP 120 m graf: {graf_stier['rsrp_120m']}",
        f"SNR 120 m graf: {graf_stier['snr_120m']}",
        f"Pathloss 120 m graf: {graf_stier['pathloss_120m']}",
        "",
        "Der er lavet grafer for alle data samlet, 15 m og 120 m.",
    ]

    return graf_stier, "\n".join(lines)


def _hent_link_input(values):
    p = {
        "ul_tx": _to_float(values["-LB-UL-TX-"], 35.0),
        "ul_tx_gain": _to_float(values["-LB-UL-TX-GAIN-"], 11.0),
        "ul_tx_loss": _to_float(values["-LB-UL-TX-LOSS-"], 2.0),
        "ul_rx_gain": _to_float(values["-LB-UL-RX-GAIN-"], -5.0),
        "ul_rx_loss": _to_float(values["-LB-UL-RX-LOSS-"], 0.5),
        "ul_sens": _to_float(values["-LB-UL-SENS-"], -102.0),
        "dl_tx": _to_float(values["-LB-DL-TX-"], 23.0),
        "dl_tx_gain": _to_float(values["-LB-DL-TX-GAIN-"], -5.0),
        "dl_tx_loss": _to_float(values["-LB-DL-TX-LOSS-"], 0.5),
        "dl_rx_gain": _to_float(values["-LB-DL-RX-GAIN-"], 11.0),
        "dl_rx_loss": _to_float(values["-LB-DL-RX-LOSS-"], 2.0),
        "dl_sens": _to_float(values["-LB-DL-SENS-"], -102.0),
        "misc_loss": _to_float(values["-LB-MISC-"], 0.0),
        "fade_margin": _to_float(values["-LB-FADE-"], 10.0),
        "freq_mhz": _to_float(values["-LB-FREQ-"], 3779.0),
        "min_dist_m": _to_float(values["-LB-MIN-DIST-"], 118.0),
        "plot_km": _to_float(values["-LB-PLOT-KM-"], 50.0),
        "h_gnb": _to_float(values["-LB-H-GNB-"], 1.5),
        "h_ue": _to_float(values["-LB-H-UE-"], 120.0),
        "h_bld": _to_float(values["-LB-H-BLD-"], 5.0),
        "ci_n": _to_float(values["-LB-CI-N-"], 2.0),
        "shadow_db": _to_float(values["-LB-SHADOW-"], 0.0),
        "cih_btx": _to_float(values["-LB-CIH-BTX-"], 0.03),
        "cih_hb0": _to_float(values["-LB-CIH-HB0-"], 35.0),
    }

    if p["freq_mhz"] <= 0:
        raise ValueError("Frekvens skal være større end 0 MHz")
    if p["plot_km"] <= 0:
        raise ValueError("Plotafstand skal være større end 0 km")
    if p["min_dist_m"] <= 0:
        raise ValueError("Min. afstand skal være større end 0 m")
    if p["h_gnb"] <= 0 or p["h_ue"] <= 0:
        raise ValueError("Antennehøjder skal være større end 0 m")
    if p["h_bld"] <= 0:
        raise ValueError("Bygningshøjde skal være større end 0 m")
    if p["ci_n"] <= 0:
        raise ValueError("CI n skal være større end 0")
    if p["cih_hb0"] <= 0:
        raise ValueError("CIH h_B0 skal være større end 0 m")

    return p


def _link_3d_afstand(d2d_km, p):
    d2d_m = np.asarray(d2d_km) * 1000
    dh = p["h_gnb"] - p["h_ue"]
    return np.sqrt(d2d_m ** 2 + dh ** 2)


def _link_fspl(d2d_km, p):
    d3d_km = np.maximum(_link_3d_afstand(d2d_km, p), 1.0) / 1000
    return 20 * np.log10(d3d_km) + 20 * np.log10(p["freq_mhz"]) + 32.45


def _link_ci(d2d_km, p):
    d3d_m = np.maximum(_link_3d_afstand(d2d_km, p), LB_D0)
    fc_ghz = p["freq_mhz"] / 1000
    fspl_1m = 32.45 + 20 * np.log10(fc_ghz)
    return fspl_1m + 10 * p["ci_n"] * np.log10(d3d_m) + p["shadow_db"]


def _link_cih(d2d_km, p):
    d3d_m = np.maximum(_link_3d_afstand(d2d_km, p), LB_D0)
    fc_ghz = p["freq_mhz"] / 1000
    fspl_1m = 32.45 + 20 * np.log10(fc_ghz)
    n_eff = p["ci_n"] * ((1 - p["cih_btx"]) + p["cih_btx"] * p["h_gnb"] / p["cih_hb0"])
    return fspl_1m + 10 * n_eff * np.log10(d3d_m) + p["shadow_db"]


def _link_3gpp(d2d_km, p):
    d3d_m = np.maximum(_link_3d_afstand(d2d_km, p), 1.0)
    fc_ghz = p["freq_mhz"] / 1000
    fc_hz = p["freq_mhz"] * 1000000
    h = p["h_bld"]

    d_bp = max(4 * p["h_gnb"] * p["h_ue"] * fc_hz / LB_C, 1.0)
    c1 = min(0.03 * h ** 1.72, 10.0)
    c2 = min(0.044 * h ** 1.72, 14.77)

    def pl1(d):
        return (
            20 * np.log10(40 * np.pi * d * fc_ghz / 3)
            + c1 * np.log10(d)
            - c2
            + 0.002 * np.log10(h) * d
        )

    pl_bp = pl1(d_bp)
    return np.where(d3d_m <= d_bp, pl1(d3d_m), pl_bp + 40 * np.log10(d3d_m / d_bp))


def _link_pathloss(model, d2d_km, p):
    if model == "FSPL":
        return _link_fspl(d2d_km, p)
    if model == "CI":
        return _link_ci(d2d_km, p)
    if model == "CIH":
        return _link_cih(d2d_km, p)
    if model == "3GPP RMa LOS":
        return _link_3gpp(d2d_km, p)
    raise ValueError(f"Ukendt model: {model}")


def _find_raekkevidde(d_km, margin):
    if not np.any(margin >= 0):
        return 0.0, False
    if margin[-1] >= 0:
        return float(d_km[-1]), True

    idx = np.where(margin >= 0)[0][-1]
    x1 = np.log10(d_km[idx])
    x2 = np.log10(d_km[idx + 1])
    y1 = margin[idx]
    y2 = margin[idx + 1]

    if y2 == y1:
        return float(d_km[idx]), False

    x0 = x1 + (0 - y1) * (x2 - x1) / (y2 - y1)
    return float(10 ** x0), False


def _beregn_link_retning(direction, d_km, pathloss, p):
    if direction == "uplink":
        eirp = p["ul_tx"] + p["ul_tx_gain"] - p["ul_tx_loss"]
        prx = eirp + p["ul_rx_gain"] - p["ul_rx_loss"] - p["misc_loss"] - pathloss
        sens = p["ul_sens"]
    else:
        eirp = p["dl_tx"] + p["dl_tx_gain"] - p["dl_tx_loss"]
        prx = eirp + p["dl_rx_gain"] - p["dl_rx_loss"] - p["misc_loss"] - pathloss
        sens = p["dl_sens"]

    margin = prx - sens - p["fade_margin"]
    range_km, limited = _find_raekkevidde(d_km, margin)
    return {"eirp": eirp, "prx": prx, "margin": margin, "range_km": range_km, "limited": limited}


def _link_afstande(max_km, min_km):
    min_km = max(min_km, 0.000001)
    max_km = max(max_km, min_km * 1.01)
    return np.logspace(np.log10(min_km), np.log10(max_km), 1200)


def _format_raekkevidde(result):
    prefix = ">= " if result["limited"] else ""
    return f"{prefix}{result['range_km']:.2f} km"


def _gem_link_graf(d_km, uplink, downlink, model):
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated_graphs")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "linkbudget_margin.png")

    plt.figure(figsize=(10, 5))
    plt.plot(d_km, uplink["margin"], label="Uplink van -> drone", color="#2196F3", linewidth=2)
    plt.plot(d_km, downlink["margin"], label="Downlink drone -> van", color="#E91E63", linewidth=2)
    plt.axhline(0, color="#F44336", linestyle="--", label="0 dB")
    if uplink["range_km"] > 0:
        plt.axvline(uplink["range_km"], color="#2196F3", linestyle=":")
    if downlink["range_km"] > 0:
        plt.axvline(downlink["range_km"], color="#E91E63", linestyle=":")
    plt.xscale("log")
    plt.xlabel("Afstand (km)")
    plt.ylabel("Link margin (dB)")
    plt.title(f"Linkbudget - {model}")
    plt.grid(True, which="both", alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=110)
    plt.close()
    return output_path


def _run_linkbudget_mode(values):
    model = values["-LB-MODEL-"]
    p = _hent_link_input(values)
    d_km = _link_afstande(p["plot_km"], p["min_dist_m"] / 1000)
    pathloss = _link_pathloss(model, d_km, p)
    uplink = _beregn_link_retning("uplink", d_km, pathloss, p)
    downlink = _beregn_link_retning("downlink", d_km, pathloss, p)

    ul_eff = p["plot_km"] if uplink["limited"] else uplink["range_km"]
    dl_eff = p["plot_km"] if downlink["limited"] else downlink["range_km"]
    system_range = min(ul_eff, dl_eff)
    image_path = _gem_link_graf(d_km, uplink, downlink, model)

    lines = [
        "Linkbudget",
        "--------------------------------------------------",
        f"Model: {model}",
        f"Frekvens: {p['freq_mhz']:.0f} MHz",
        f"Plotafstand: {p['plot_km']:.2f} km",
        f"Systemrækkevidde: {system_range:.2f} km",
        "",
        "Uplink (van -> drone)",
        f"  EIRP: {uplink['eirp']:.1f} dBm",
        f"  Rækkevidde: {_format_raekkevidde(uplink)}",
        f"  Margin ved min. afstand: {uplink['margin'][0]:.1f} dB",
        "",
        "Downlink (drone -> van)",
        f"  EIRP: {downlink['eirp']:.1f} dBm",
        f"  Rækkevidde: {_format_raekkevidde(downlink)}",
        f"  Margin ved min. afstand: {downlink['margin'][0]:.1f} dB",
    ]

    return image_path, "\n".join(lines)


def _build_netvaerk_tables():
    tables = datarater.lav_tabeller()
    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "netvaerk_analyse.txt")

    with open(report_path, "w", encoding="utf-8") as file:
        file.write(datarater.lav_rapport(tables))

    rows = {
        "downlink_15": datarater.tabel_rows(tables["downlink_15"]),
        "downlink_120": datarater.tabel_rows(tables["downlink_120"]),
        "uplink_15": datarater.tabel_rows(tables["uplink_15"]),
        "uplink_120": datarater.tabel_rows(tables["uplink_120"]),
    }
    status = (
        f"Netværksdata opdateret. Rapport gemt i {report_path}"
    )
    return rows, status


def _data_table(key, expand_y=False):
    return sg.Table(
        values=[],
        headings=DATA_HEADINGS,
        key=key,
        auto_size_columns=False,
        col_widths=DATA_COL_WIDTHS,
        justification="left",
        num_rows=5,
        expand_x=True,
        expand_y=expand_y,
        text_color=FARVE_TEKST,
        background_color=FARVE_PANEL,
        alternating_row_color=FARVE_FELT,
        selected_row_colors=("white", FARVE_KNAP),
        header_text_color=FARVE_TEKST,
        header_background_color=FARVE_KANT,
    )


def _net_table(key, headings, col_widths):
    return sg.Table(
        values=[],
        headings=headings,
        key=key,
        auto_size_columns=False,
        col_widths=col_widths,
        justification="left",
        num_rows=5,
        expand_x=True,
        text_color=FARVE_TEKST,
        background_color=FARVE_PANEL,
        alternating_row_color=FARVE_FELT,
        selected_row_colors=("white", FARVE_KNAP),
        header_text_color=FARVE_TEKST,
        header_background_color=FARVE_KANT,
    )


def main():
    sg.theme("LightBlue1")
    sg.set_options(
        font=("Helvetica", 10),
        background_color=FARVE_BAGGRUND,
        text_color=FARVE_TEKST,
        input_elements_background_color=FARVE_FELT,
        input_text_color=FARVE_TEKST,
        button_color=("white", FARVE_KNAP),
        use_ttk_buttons=False,
    )
    tab_settings = [
        [sg.Text("Indstillinger", font=("Helvetica", 11, "bold"))],
        [
            sg.Text("Carrier MHz"), sg.Input(str(rasp.Carrier_Frequency), key="-CF-", size=(8, 1)),
            sg.Text("gNB Tx dBm"), sg.Input(str(rasp.gNB_transmit_power), key="-TXP-", size=(8, 1)),
            sg.Text("Gain dB"), sg.Input(str(rasp.Antenne_gain), key="-GAIN-", size=(8, 1)),
        ],
        [
            sg.Text("BW MHz"), sg.Input(str(rasp.BW), key="-BW-", size=(8, 1)),
            sg.Text("SCS kHz"), sg.Input(str(rasp.Sub_carrier_spacing), key="-SCS-", size=(8, 1)),
            sg.Text("Thermal"), sg.Input(str(rasp.Thermal_Noise), key="-TN-", size=(8, 1)),
            sg.Text("NF dB"), sg.Input(str(rasp.NoiseFigure), key="-NF-", size=(8, 1)),
        ],
        [sg.Text("Disse værdier bruges i både T- og M-beregninger.")],
    ]

    tab_t = [
        [sg.Text("Teoretisk mode", font=("Helvetica", 11, "bold"))],
        [sg.Text("Afstand i km"), sg.Input("1.0", key="-AFSTAND-T-", size=(18, 1))],
        [sg.Button("Beregn", key="-BEREGN-T-", bind_return_key=True)],
        [sg.Multiline("", key="-OUT-T-", size=(95, 22), disabled=True, autoscroll=True, expand_x=True, expand_y=True, background_color=FARVE_PANEL, text_color=FARVE_TEKST)],
    ]

    tab_m = [
        [sg.Text("Måling", font=("Helvetica", 11, "bold"))],
        [sg.Text("Drone lokation lat,lon"), sg.Input(f"{rasp.Drone_Lokation[0]},{rasp.Drone_Lokation[1]}", key="-DRONE-M-", size=(24, 1))],
        [sg.Text("gNB lokation lat,lon"), sg.Input("57.0180391,9.7602773", key="-GNB-M-", size=(24, 1))],
        [
            sg.Text("Målt RSRP (dBm)"), sg.Input("", key="-M-RSRP-", size=(12, 1)),
            sg.Text("Målt SNR (dB)"), sg.Input("", key="-M-SNR-", size=(12, 1)),
        ],
        [sg.Text("Tomme felter for Målt RSRP/SNR bruger standardværdier fra fil-data")],
        [sg.Button("Beregn", key="-BEREGN-M-")],
        [sg.Multiline("", key="-OUT-M-", size=(95, 22), disabled=True, autoscroll=True, expand_x=True, expand_y=True, background_color=FARVE_PANEL, text_color=FARVE_TEKST)],
    ]

    tab_data = [
        [sg.Text("Data", font=("Helvetica", 11, "bold"))],
        [sg.Button("Opdater Data", key="-OPDATER-DATA-")],
        [
            sg.TabGroup(
                [[
                    sg.Tab(
                        "15 m",
                        [
                            [sg.Text("FSPL", font=("Helvetica", 10, "bold"))],
                            [_data_table("-DATA-TABEL-FSPL-15-")],
                            [sg.Text("3GPP RMa LOS", font=("Helvetica", 10, "bold"))],
                            [_data_table("-DATA-TABEL-RMA-15-", expand_y=True)],
                        ],
                    ),
                    sg.Tab(
                        "120 m",
                        [
                            [sg.Text("FSPL", font=("Helvetica", 10, "bold"))],
                            [_data_table("-DATA-TABEL-FSPL-120-")],
                            [sg.Text("3GPP RMa LOS", font=("Helvetica", 10, "bold"))],
                            [_data_table("-DATA-TABEL-RMA-120-", expand_y=True)],
                        ],
                    ),
                ]],
                title_color=FARVE_TEKST,
                tab_background_color=FARVE_FELT,
                selected_title_color="white",
                selected_background_color=FARVE_KNAP,
                background_color=FARVE_BAGGRUND,
                focus_color=FARVE_KNAP,
                expand_x=True,
                expand_y=True,
            )
        ],
        [sg.Text("", key="-DATA-STATUS-")],
    ]

    tab_grafer = [
        [sg.Text("Grafer", font=("Helvetica", 11, "bold"))],
        [sg.Text("Viser måledata som grafer og sammenligner med FSPL.")],
        [sg.Button("Lav grafer", key="-LAV-GRAFER-")],
        [
            sg.Text("Alle data", size=(8, 1)),
            sg.Button("Vis RSRP", key="-VIS-GRAF-RSRP-"),
            sg.Button("Vis SNR", key="-VIS-GRAF-SNR-"),
            sg.Button("Vis Pathloss", key="-VIS-GRAF-PATHLOSS-"),
        ],
        [
            sg.Text("15 m", size=(8, 1)),
            sg.Button("Vis RSRP", key="-VIS-GRAF-RSRP-15-"),
            sg.Button("Vis SNR", key="-VIS-GRAF-SNR-15-"),
            sg.Button("Vis Pathloss", key="-VIS-GRAF-PATHLOSS-15-"),
        ],
        [
            sg.Text("120 m", size=(8, 1)),
            sg.Button("Vis RSRP", key="-VIS-GRAF-RSRP-120-"),
            sg.Button("Vis SNR", key="-VIS-GRAF-SNR-120-"),
            sg.Button("Vis Pathloss", key="-VIS-GRAF-PATHLOSS-120-"),
        ],
        [sg.Image("", key="-GRAF-IMAGE-", expand_x=True, expand_y=True)],
        [sg.Multiline("", key="-OUT-GRAFER-", size=(95, 6), disabled=True, autoscroll=True, expand_x=True, background_color=FARVE_PANEL, text_color=FARVE_TEKST)],
    ]

    lb_ul_rows = [
        [sg.Text(label, size=(12, 1)), sg.Input(str(default), key=key, size=(8, 1)), sg.Text(unit, size=(4, 1))]
        for label, key, default, unit in LB_UPLINK_FELTER
    ]
    lb_dl_rows = [
        [sg.Text(label, size=(12, 1)), sg.Input(str(default), key=key, size=(8, 1)), sg.Text(unit, size=(4, 1))]
        for label, key, default, unit in LB_DOWNLINK_FELTER
    ]
    lb_common_rows = [
        [sg.Text(label, size=(14, 1)), sg.Input(str(default), key=key, size=(8, 1)), sg.Text(unit, size=(4, 1))]
        for label, key, default, unit in LB_FAELLES_FELTER
    ]

    tab_linkbudget = [
        [sg.Text("Linkbudget", font=("Helvetica", 11, "bold"))],
        [
            sg.Text("Pathloss-model"),
            sg.Combo(["FSPL", "CI", "CIH", "3GPP RMa LOS"], default_value="FSPL", key="-LB-MODEL-", readonly=True, size=(18, 1)),
            sg.Button("Beregn linkbudget", key="-BEREGN-LINK-"),
        ],
        [
            sg.Frame("Uplink van -> drone", lb_ul_rows, background_color=FARVE_BAGGRUND),
            sg.Frame("Downlink drone -> van", lb_dl_rows, background_color=FARVE_BAGGRUND),
            sg.Frame("Fælles", lb_common_rows, background_color=FARVE_BAGGRUND),
        ],
        [sg.Image("", key="-LINK-IMAGE-", expand_x=True, expand_y=True)],
        [sg.Multiline("", key="-OUT-LINK-", size=(95, 8), disabled=True, autoscroll=True, expand_x=True, background_color=FARVE_PANEL, text_color=FARVE_TEKST)],
    ]

    net_headings = ["Afstand (m)"] + datarater.rates
    net_col_widths = [10, 16, 16, 16, 16, 16]

    tab_net = [
        [sg.Text("Netværksanalyse", font=("Helvetica", 11, "bold"))],
        [sg.Button("Opdater netværk", key="-OPDATER-NET-")],
        [
            sg.TabGroup(
                [[
                    sg.Tab(
                        "15 m",
                        [
                            [sg.Text("Downlink", font=("Helvetica", 10, "bold"))],
                            [_net_table("-NET-DL-15-", net_headings, net_col_widths)],
                            [sg.Text("Uplink", font=("Helvetica", 10, "bold"))],
                            [_net_table("-NET-UL-15-", net_headings, net_col_widths)],
                        ],
                    ),
                    sg.Tab(
                        "120 m",
                        [
                            [sg.Text("Downlink", font=("Helvetica", 10, "bold"))],
                            [_net_table("-NET-DL-120-", net_headings, net_col_widths)],
                            [sg.Text("Uplink", font=("Helvetica", 10, "bold"))],
                            [_net_table("-NET-UL-120-", net_headings, net_col_widths)],
                        ],
                    ),
                ]],
                title_color=FARVE_TEKST,
                tab_background_color=FARVE_FELT,
                selected_title_color="white",
                selected_background_color=FARVE_KNAP,
                background_color=FARVE_BAGGRUND,
                focus_color=FARVE_KNAP,
                expand_x=True,
                expand_y=True,
            )
        ],
        [sg.Text("", key="-NET-STATUS-")],
    ]

    layout = [
        [sg.Text("RSRP Beregner (GUI)", font=("Helvetica", 14, "bold"))],
        [
            sg.TabGroup(
                [[
                    sg.Tab("Teoretisk", tab_t),
                    sg.Tab("Måling", tab_m),
                    sg.Tab("Data", tab_data),
                    sg.Tab("Grafer", tab_grafer),
                    sg.Tab("Linkbudget", tab_linkbudget),
                    sg.Tab("Netværk", tab_net),
                    sg.Tab("Indstillinger", tab_settings),

                ]],
                title_color=FARVE_TEKST,
                tab_background_color=FARVE_FELT,
                selected_title_color="white",
                selected_background_color=FARVE_KNAP,
                background_color=FARVE_BAGGRUND,
                focus_color=FARVE_KNAP,
                expand_x=True,
                expand_y=True,
            )
        ],
        [sg.Button("Luk")],
    ]

    window = sg.Window("RSRP FreeSimpleGUI", layout, finalize=True, resizable=True, background_color=FARVE_BAGGRUND)

    window.maximize()

    graf_stier = {}

    while True:
        event, values = window.read()

        if event in (sg.WIN_CLOSED, "Luk"):
            break


        if event == "-BEREGN-T-":
            try:
                result_text = _run_t_mode(values)
                window["-OUT-T-"].update(result_text)
            except Exception as exc:
                window["-OUT-T-"].update(f"Fejl: {exc}")

        if event == "-BEREGN-M-":
            try:
                result_text = _run_m_mode(values)
                window["-OUT-M-"].update(result_text)
            except Exception as exc:
                window["-OUT-M-"].update(f"Fejl: {exc}")

        if event == "-OPDATER-DATA-":
            try:
                rasp.clear_measurement_cache()
                rows_by_height, status = _build_data_tables(values)
                window["-DATA-TABEL-FSPL-15-"].update(values=rows_by_height["15m"]["fspl"])
                window["-DATA-TABEL-RMA-15-"].update(values=rows_by_height["15m"]["rma"])
                window["-DATA-TABEL-FSPL-120-"].update(values=rows_by_height["120m"]["fspl"])
                window["-DATA-TABEL-RMA-120-"].update(values=rows_by_height["120m"]["rma"])
                window["-DATA-STATUS-"].update(status)
            except Exception as exc:
                window["-DATA-STATUS-"].update(f"Fejl i Data: {exc}")

        if event == "-LAV-GRAFER-":
            try:
                graf_stier, status = _run_graph_mode(values)
                window["-OUT-GRAFER-"].update(status)
                window["-GRAF-IMAGE-"].update(filename=graf_stier["rsrp"])
            except Exception as exc:
                window["-OUT-GRAFER-"].update(f"Fejl i grafer: {exc}")

        if event in GRAF_KNAPPER:
            try:
                if not graf_stier:
                    graf_stier, status = _run_graph_mode(values)
                    window["-OUT-GRAFER-"].update(status)

                window["-GRAF-IMAGE-"].update(filename=graf_stier[GRAF_KNAPPER[event]])
            except Exception as exc:
                window["-OUT-GRAFER-"].update(f"Fejl i visning af graf: {exc}")

        if event == "-BEREGN-LINK-":
            try:
                image_path, result_text = _run_linkbudget_mode(values)
                window["-OUT-LINK-"].update(result_text)
                window["-LINK-IMAGE-"].update(filename=image_path)
            except Exception as exc:
                window["-OUT-LINK-"].update(f"Fejl i linkbudget: {exc}")

        if event == "-OPDATER-NET-":
            try:
                rows, status = _build_netvaerk_tables()
                window["-NET-DL-15-"].update(values=rows["downlink_15"])
                window["-NET-DL-120-"].update(values=rows["downlink_120"])
                window["-NET-UL-15-"].update(values=rows["uplink_15"])
                window["-NET-UL-120-"].update(values=rows["uplink_120"])
                window["-NET-STATUS-"].update(status)
            except Exception as exc:
                window["-NET-STATUS-"].update(f"Fejl i netværksanalyse: {exc}")

    window.close()


if __name__ == "__main__":
    main()
