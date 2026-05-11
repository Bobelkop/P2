import numpy as np
from geopy.distance import geodesic
import json
import glob
import os
import csv
import re

script_dir = os.path.dirname(os.path.abspath(__file__))
_mpl_config_dir = os.path.join(script_dir, ".matplotlib")
os.makedirs(_mpl_config_dir, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", _mpl_config_dir)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

#Link budget beregninger for RASP
Afstand = 0  # kmpd
Carrier_Frequency = 3779  # MHz
gNB_transmit_power = 35  # dBm
Antenne_gain = 10  # dB
TX_EIRP = gNB_transmit_power + Antenne_gain  # dBm
BW = 20  # MHz
Sub_carrier_spacing = 30  # kHz
RE_Power = 10 * np.log10(10 ** (TX_EIRP / 10) * (Sub_carrier_spacing) / (BW * 0.9 * 1000))  # dBm

# Målinger
målinger = 0

#SNR
Thermal_Noise = -174   # dBm/Hz
NoiseFigure = 5     # dB

# Drone lokation
Drone_Lokation = (57.026180, 9.747177)  # Koordinater: (breddegrad, længdegrad)
# gNB lokation
gNB_Lokation = (0, 0)  # Koordinater: (breddegrad, længdegrad)

# Data fra JSON log og definere hvor målingerne ligger
root_dir = os.path.join(script_dir, "DATA")
rows = []
# Til at finde alle relevante målefiler i undermapperne
# Only consider measurement files (cell_log.json and *-radio.log) to speed parsing
measurement_file_paths = []
measurement_file_paths.extend(glob.glob(os.path.join(root_dir, "**", "cell_log.json"), recursive=True))
measurement_file_paths.extend(glob.glob(os.path.join(root_dir, "**", "*-radio.log"), recursive=True))

# Keep a cache of parsed measurements to avoid re-parsing on every UI action
_MEASUREMENT_CACHE = None

def clear_measurement_cache():
    global _MEASUREMENT_CACHE
    _MEASUREMENT_CACHE = None
testlist_csv_path = os.path.join(root_dir, "testlist.csv")

#print(f"Debug: Fundet {len(file_paths)} JSON filer")
#for fp in file_paths:
#    print(f"  - {fp}")

# Teoretisk RASP FSPL (Free Space Path Loss)
def Teoretisk_RASP_FSPL(data, Carrier_Frequency, RE_Power):
    Afstand = data  # km
    # Undgå fejl ved distance 0: brug lille epsilon i stedet
    if Afstand <= 0:
        Afstand = 0.001
    pathloss = 20 * np.log10(Afstand) + 20 * np.log10(Carrier_Frequency) + 32.44  # dB
    RSRP = RE_Power - pathloss  # dBm
    return pathloss, RSRP


def Teoretisk_RASP_3GPP(data, Carrier_Frequency, RE_Power, h_gnb=1.5, h_ue=120.0, h_bld=5.0):
    afstand_km = data
    if afstand_km <= 0:
        afstand_km = 0.001

    d2d_m = afstand_km * 1000
    d3d_m = np.sqrt(d2d_m ** 2 + (h_gnb - h_ue) ** 2)
    d3d_m = max(d3d_m, 1.0)
    fc_ghz = Carrier_Frequency / 1000
    fc_hz = Carrier_Frequency * 1000000

    d_bp = max(4 * h_gnb * h_ue * fc_hz / 3e8, 1.0)
    c1 = min(0.03 * h_bld ** 1.72, 10.0)
    c2 = min(0.044 * h_bld ** 1.72, 14.77)

    def pl1(d):
        return (
            20 * np.log10(40 * np.pi * d * fc_ghz / 3)
            + c1 * np.log10(d)
            - c2
            + 0.002 * np.log10(h_bld) * d
        )

    if d3d_m <= d_bp:
        pathloss = pl1(d3d_m)
    else:
        pathloss = pl1(d_bp) + 40 * np.log10(d3d_m / d_bp)

    RSRP = RE_Power - pathloss
    return pathloss, RSRP

def Afvigelse_Af_Målinger_På_Teori_RSRP(målinger,RSRP):
    Målt_RSRP = målinger
    if RSRP == 0:
        raise ValueError("RSRP maa ikke vaere 0 ved afvigelsesberegning")
    Afvigelse = Målt_RSRP - RSRP
    return Afvigelse



def Afstandsformel(Drone_Lokation, gNB_Lokation):
    if isinstance(Drone_Lokation, str):
        x1, y1 = map(float, Drone_Lokation.split(","))
    else:
        x1, y1 = map(float, Drone_Lokation)

    if isinstance(gNB_Lokation, str):
        x2, y2 = map(float, gNB_Lokation.split(","))
    else:
        x2, y2 = map(float, gNB_Lokation)

    Afstand = geodesic((x1, y1), (x2, y2)).kilometers
    return Afstand

def Teoretisk_SNR(RSRP, Thermal_Noise, NoiseFigure,Sub_carrier_spacing):
    Sub_carrier_spacing_Hz = Sub_carrier_spacing *1000
    Noise_Floor = Thermal_Noise + NoiseFigure + 10 * np.log10(Sub_carrier_spacing_Hz)
    SNR=(RSRP - Noise_Floor)
    
    return SNR

#def Data_Fra_Json(rows):
   # with open("cell_log.json", "r") as file:
   #    for line in file:
   #      if not line:
   #            continue
   #        object = json.loads(line)
   #        object["rsrp.number"] = float(object["rsrp"])
   #        object["snr.number"] = float(object["snr"])
   #        rows.append(object)
   #
   #        Rsrp_Gennemsnit = (sum(r["rsrp.number"] for r in rows) / len(rows))
   #        SNR_Gennemsnit = (sum(r["snr.number"] for r in rows) / len(rows))
   #
   #return Rsrp_Gennemsnit, SNR_Gennemsnit


def Data_Fra_Json(rows, file_path):
    rows.clear()  # Tøm listen FØR vi læser på ny fil
    # Støtt både JSON-linjer og ikke-JSON .test filer ved regex-udtræk
    rsrp_values = []
    snr_values = []

    with open(file_path, "r", encoding="utf-8-sig", errors="ignore") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue

            # Forsøg JSON først
            parsed = False
            try:
                obj = json.loads(line)
                if isinstance(obj, dict) and "rsrp" in obj and "snr" in obj:
                    try:
                        rsrp_values.append(float(str(obj["rsrp"]).replace(",", ".").split()[0]))
                        snr_values.append(float(str(obj["snr"]).replace(",", ".").split()[0]))
                        parsed = True
                    except Exception:
                        parsed = False
            except Exception:
                parsed = False

            if parsed:
                continue

            # Fallback: regex-søg efter rsrp/snr i linjen (som i make_graphs)
            rsrp_match = re.search(r'"?rsrp"?\s*[:=]\s*"?(-?\d+(?:[.,]\d+)?)', line, re.IGNORECASE)
            snr_match = re.search(r'"?snr"?\s*[:=]\s*"?(-?\d+(?:[.,]\d+)?)', line, re.IGNORECASE)

            if rsrp_match and snr_match:
                try:
                    rsrp_values.append(float(rsrp_match.group(1).replace(",", ".")))
                    snr_values.append(float(snr_match.group(1).replace(",", ".")))
                except Exception:
                    continue

    if not rsrp_values or not snr_values:
        raise ValueError("Ingen gyldige rsrp/snr-linjer i filen")

    rsrp_mean = sum(rsrp_values) / len(rsrp_values)
    snr_mean = sum(snr_values) / len(snr_values)

    return rsrp_mean, snr_mean

    if not rows:
        raise ValueError("Ingen gyldige rsrp/snr-linjer i filen")

    # Gennemsnit pr. FIL (én måling)
    Rsrp_Gennemsnit = (sum(r["rsrp.number"] for r in rows) / len(rows))
    SNR_Gennemsnit = (sum(r["snr.number"] for r in rows) / len(rows))
            
    return Rsrp_Gennemsnit, SNR_Gennemsnit

def Hent_Test_Metadata(csv_path):
    metadata = {}
    if not os.path.exists(csv_path):
        return metadata
    
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            try:
                testnr = int(str(row.get("testnr", "")).strip())
                latitude = float(str(row.get("latitude", "")).strip())
                longitude = float(str(row.get("longitude", "")).strip())
            except ValueError:
                continue

            height_raw = str(row.get("height", "")).strip()
            try:
                height_m = float(height_raw) if height_raw != "" else None
            except ValueError:
                height_m = None
            
            # Læs drone-koordinater hvis de findes
            drone_lat_raw = str(row.get("drone_latitude", "")).strip()
            drone_lon_raw = str(row.get("drone_longitude", "")).strip()
            try:
                drone_lat = float(drone_lat_raw) if drone_lat_raw != "" else None
                drone_lon = float(drone_lon_raw) if drone_lon_raw != "" else None
                drone_location = (drone_lat, drone_lon) if (drone_lat is not None and drone_lon is not None) else None
            except ValueError:
                drone_location = None

            metadata[testnr] = {
                "lat_lon": (latitude, longitude),
                "height_m": height_m,
                "drone_location": drone_location,
            }
    return metadata


def Hent_Koordinater(csv_path):
    koordinater = {}
    metadata = Hent_Test_Metadata(csv_path)
    for testnr, item in metadata.items():
        koordinater[testnr] = item["lat_lon"]
    return koordinater

def hent_nummer_fra_path(file_path):
    match = re.search(r"test(\d+)", file_path, re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))

def alle_målinger_fra_json(drone_lokation=None, force_reload=False):
    global _MEASUREMENT_CACHE
    if _MEASUREMENT_CACHE is not None and not force_reload:
        return _MEASUREMENT_CACHE

    resultater = {}
    test_metadata = Hent_Test_Metadata(testlist_csv_path)

    for file_path in measurement_file_paths:
        try:
            rsrp_mean, snr_mean = Data_Fra_Json([], file_path)
            filnavn = os.path.relpath(file_path, root_dir)
            testnr = hent_nummer_fra_path(file_path)
            meta = test_metadata.get(testnr, {})
            lat_lon = meta.get("lat_lon")
            height_m = meta.get("height_m")

            # Brug drone-lokation fra CSV hvis den findes, ellers brug parameter, ellers global
            test_drone_loc = meta.get("drone_location")
            if test_drone_loc is None:
                test_drone_loc = drone_lokation if drone_lokation else Drone_Lokation

            resultater[filnavn] = {
                'rsrp': rsrp_mean,
                'snr': snr_mean,
                'path': file_path,
                "testnr": testnr,
                "lat_lon": lat_lon,
                "height_m": height_m,
                "afstand": Afstandsformel(test_drone_loc, lat_lon) if lat_lon else None
            }
            #if lat_lon is None:
               #print(f"✓ {filnavn}: RSRP={rsrp_mean:.2f} dBm, SNR={snr_mean:.2f} dB")
            #else:
             #   print(
             #       f"✓ {filnavn}: RSRP={rsrp_mean:.2f} dBm, SNR={snr_mean:.2f} dB, "
             #       f"Koordinater=({lat_lon[0]:.7f},{lat_lon[1]:.7f})"
             #       )
        except Exception as e:
            print(f"✗ Fejl ved læsning af {file_path}: {e}")
    
    _MEASUREMENT_CACHE = resultater
    return resultater


def _height_group(height_value):
    if height_value is None:
        return "120m"
    if abs(float(height_value) - 15.0) < 0.6:
        return "15m"
    return "120m"


def Lav_Grafer(carrier_frequency=None, re_power=None, thermal_noise=None, noise_figure=None, scs_khz=None, drone_lokation=None):
    from scipy.stats import linregress
    
    carrier_frequency = float(Carrier_Frequency if carrier_frequency is None else carrier_frequency)
    re_power = float(RE_Power if re_power is None else re_power)
    thermal_noise = float(Thermal_Noise if thermal_noise is None else thermal_noise)
    noise_figure = float(NoiseFigure if noise_figure is None else noise_figure)
    scs_khz = float(Sub_carrier_spacing if scs_khz is None else scs_khz)
    if drone_lokation is None:
        drone_lokation = Drone_Lokation

    resultater = alle_målinger_fra_json(drone_lokation)
    if not resultater:
        raise ValueError(f"Ingen måledata fundet i {root_dir}")

    datapunkter = []
    for data in resultater.values():
        afstand = data.get("afstand")
        if afstand is None or afstand <= 0:
            continue

        datapunkter.append(
            {
                "afstand": float(afstand),
                "rsrp": float(data["rsrp"]),
                "snr": float(data["snr"]),
                "pathloss": float(re_power - data["rsrp"]),
                "gruppe": _height_group(data.get("height_m")),
            }
        )

    if not datapunkter:
        raise ValueError("Ingen gyldige målepunkter med afstand fundet til grafer")

    datapunkter.sort(key=lambda item: item["afstand"])

    grupper = {
        "15m": {"farve": "#1f77b4", "markor": "o", "label": "Målt 15 m"},
        "120m": {"farve": "#d62728", "markor": "^", "label": "Målt 120 m"},
    }

    output_dir = os.path.join(script_dir, "generated_graphs")
    os.makedirs(output_dir, exist_ok=True)

    def _plot_målinger(figur_navn, y_nøgle, y_label, filnavn, gruppe_filter=None):
        plot_punkter = []
        for item in datapunkter:
            if gruppe_filter is None or item["gruppe"] == gruppe_filter:
                plot_punkter.append(item)

        if not plot_punkter:
            return None

        afstande = [item["afstand"] for item in plot_punkter]
        min_afstand = max(min(afstande), 0.001)
        max_afstand = max(max(afstande), min_afstand + 0.001)
        kurve_x = np.logspace(np.log10(min_afstand), np.log10(max_afstand), 250)
        kurve_y = []

        for afstand in kurve_x:
            fspl = Teoretisk_RASP_FSPL(afstand, carrier_frequency, re_power)
            if y_nøgle == "rsrp":
                kurve_y.append(fspl[1])
            elif y_nøgle == "snr":
                kurve_y.append(Teoretisk_SNR(fspl[1], thermal_noise, noise_figure, scs_khz))
            else:
                kurve_y.append(fspl[0])

        kurve_x_meter = kurve_x * 1000

        # Beregn regression for alle målepunkter
        måle_x = np.array([item["afstand"] * 1000 for item in plot_punkter])  # meter (log scale)
        måle_y = np.array([item[y_nøgle] for item in plot_punkter])
        
        # Brug log(afstand) til regression (lineær i log-scale)
        måle_x_log = np.log10(måle_x)
        slope, intercept, r_value, p_value, std_err = linregress(måle_x_log, måle_y)
        r_squared = r_value ** 2
        
        # Regress linje
        regression_y = slope * måle_x_log + intercept

        plt.figure(figsize=(10, 5))
        for gruppe, style in grupper.items():
            if gruppe_filter is not None and gruppe != gruppe_filter:
                continue

            gruppe_punkter = [item for item in plot_punkter if item["gruppe"] == gruppe]
            if not gruppe_punkter:
                continue
            plt.scatter(
                [item["afstand"] * 1000 for item in gruppe_punkter],
                [item[y_nøgle] for item in gruppe_punkter],
                label=style["label"],
                color=style["farve"],
                marker=style["markor"],
                s=55,
            )

        plt.plot(kurve_x_meter, kurve_y, label="FSPL teoretisk", color="#2ca02c", linewidth=2)
        plt.plot(måle_x, regression_y, label=f"Regression (R² = {r_squared:.3f})", 
                color="#ff7f0e", linewidth=2, linestyle="--")
        plt.title(figur_navn)
        plt.xlabel("Afstand (m)")
        plt.ylabel(y_label)
        plt.xscale("log")
        plt.grid(True, alpha=0.3)
        plt.legend()
        plt.tight_layout()
        sti = os.path.join(output_dir, filnavn)
        plt.savefig(sti, dpi=110)
        plt.close()
        return sti

    return {
        "rsrp": _plot_målinger("RSRP vs afstand - alle højder", "rsrp", "RSRP (dBm)", "rsrp_plot.png"),
        "snr": _plot_målinger("SNR vs afstand - alle højder", "snr", "SNR (dB)", "snr_plot.png"),
        "pathloss": _plot_målinger("Pathloss vs afstand - alle højder", "pathloss", "Pathloss (dB)", "pathloss_plot.png"),
        "rsrp_15m": _plot_målinger("RSRP vs afstand - 15 m", "rsrp", "RSRP (dBm)", "rsrp_plot_15m.png", "15m"),
        "snr_15m": _plot_målinger("SNR vs afstand - 15 m", "snr", "SNR (dB)", "snr_plot_15m.png", "15m"),
        "pathloss_15m": _plot_målinger("Pathloss vs afstand - 15 m", "pathloss", "Pathloss (dB)", "pathloss_plot_15m.png", "15m"),
        "rsrp_120m": _plot_målinger("RSRP vs afstand - 120 m", "rsrp", "RSRP (dBm)", "rsrp_plot_120m.png", "120m"),
        "snr_120m": _plot_målinger("SNR vs afstand - 120 m", "snr", "SNR (dB)", "snr_plot_120m.png", "120m"),
        "pathloss_120m": _plot_målinger("Pathloss vs afstand - 120 m", "pathloss", "Pathloss (dB)", "pathloss_plot_120m.png", "120m"),
    }



def main():
    menu_input = input("Teoretisk måling eller sammenligning med målinger? (T/M) [T]: ").strip().upper()
    menuvalg = menu_input if menu_input else "T"

    if menuvalg == "T":
        try:
            afstand_txt = input("Indtast afstand i km [1.0]: ").strip()
            afstand_input = float(afstand_txt) if afstand_txt else 1.0


        except ValueError:
            print("Ugyldigt input: brug tal (fx 1.2 for afstand i km)")
            return

        result_fspl = Teoretisk_RASP_FSPL(afstand_input, Carrier_Frequency, RE_Power)
        result_3gpp = Teoretisk_RASP_3GPP(afstand_input, Carrier_Frequency, RE_Power)
        print("--------------------------------------------------")
        print(f"Teoretisk RASP FSPL for {afstand_input} km:")
        print(f"Pathloss: {result_fspl[0]:.2f} dB")
        print(f"RSRP: {result_fspl[1]:.2f} dBm")
        print(f"Teoretisk SNR: {Teoretisk_SNR(result_fspl[1], Thermal_Noise, NoiseFigure, Sub_carrier_spacing):.2f} dB")
        print("--------------------------------------------------")
        print(f"Teoretisk RASP 3GPP RMa LOS for {afstand_input} km:")
        print(f"Pathloss: {result_3gpp[0]:.2f} dB")
        print(f"RSRP: {result_3gpp[1]:.2f} dBm")
        print(f"Teoretisk SNR: {Teoretisk_SNR(result_3gpp[1], Thermal_Noise, NoiseFigure, Sub_carrier_spacing):.2f} dB")
        print("--------------------------------------------------")
    elif menuvalg == "M":
        try:
            gNB_input = input("Indtast gNB lokation (breddegrad, længdegrad) [57.0180391,9.7602773]: ").strip()
            gNB_Lokation = gNB_input if gNB_input else "57.0180391,9.7602773"
        except ValueError:
            print("Ugyldigt input: brug tal (fx 57.026180 for breddegrad og 9.747177 for længd" \
            "egrad)")
            return
        
        # Hent alle målinger fra JSON filerne
        resultater = alle_målinger_fra_json()

        sorteret = sorted(
            resultater.items(),
            key=lambda item: (
                item[1]["testnr"] is None,
                item[1]["testnr"] if item[1]["testnr"] is not None else 9999,
                item[0],
            ),
        )
        
        Afstand = Afstandsformel(Drone_Lokation, gNB_Lokation)
        print(f"Afstand mellem drone og gNB (manuel): {Afstand:.2f} km")
        print("Målinger pr. testfil")
        print("=" * 62)
        for filnavn, data in sorteret:
            if data.get('lat_lon') is not None:
                afstand_fil = Afstandsformel(Drone_Lokation, data['lat_lon'])
            else:
                afstand_fil = Afstand

            result_fspl = Teoretisk_RASP_FSPL(afstand_fil, Carrier_Frequency, RE_Power)
            result_3gpp = Teoretisk_RASP_3GPP(
                afstand_fil,
                Carrier_Frequency,
                RE_Power,
                h_ue=data.get("height_m") if data.get("height_m") is not None else 120.0
            )
            snr_fspl = Teoretisk_SNR(result_fspl[1], Thermal_Noise, NoiseFigure, Sub_carrier_spacing)
            snr_3gpp = Teoretisk_SNR(result_3gpp[1], Thermal_Noise, NoiseFigure, Sub_carrier_spacing)

            målt_rsrp = data['rsrp']
            målt_snr = data['snr']

            print(f"\nTestfil: {filnavn}")
            print("-" * 62)
            print(f"Afstand                 : {afstand_fil:.2f} km")
            print(f"Målt RSRP               : {data['rsrp']:.2f} dBm")
            print(f"Målt SNR                : {data['snr']:.2f} dB")
            if data.get('lat_lon') is not None:
                print(f"Koordinater             : {data['lat_lon'][0]:.7f}, {data['lat_lon'][1]:.7f}")

            print("FSPL")
            print(f"  Teoretisk RSRP        : {result_fspl[1]:.2f} dBm")
            print(f"  Teoretisk SNR         : {snr_fspl:.2f} dB")
            print(f"  Afvigelse RSRP        : {Afvigelse_Af_Målinger_På_Teori_RSRP(målt_rsrp, result_fspl[1]):.2f} %")
            print(f"  Afvigelse SNR         : {snr_fspl - målt_snr:.2f} dB")

            print("3GPP RMa LOS")
            print(f"  Teoretisk RSRP        : {result_3gpp[1]:.2f} dBm")
            print(f"  Teoretisk SNR         : {snr_3gpp:.2f} dB")
            print(f"  Afvigelse RSRP        : {Afvigelse_Af_Målinger_På_Teori_RSRP(målt_rsrp, result_3gpp[1]):.2f} %")
            print(f"  Afvigelse SNR         : {snr_3gpp - målt_snr:.2f} dB")

        print("=" * 62)







    else:
        print("Ugyldigt valg: vælg 'T' for teoretisk måling eller 'M' for sammenligning med målinger")




   



if __name__ == "__main__":
    main()
