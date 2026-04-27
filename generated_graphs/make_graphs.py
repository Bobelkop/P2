import os
import re
import csv
import json
import math
import glob
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


# --------------------------------------------------
# Indstillinger
# --------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "DATA")
OUTPUT_DIR = SCRIPT_DIR

# Link budget værdier
Carrier_Frequency = 3779  # MHz
gNB_transmit_power = 35   # dBm
Antenne_gain = 10         # dB
BW = 20                   # MHz
Sub_carrier_spacing = 30  # kHz
Thermal_Noise = -174      # dBm/Hz
NoiseFigure = 5           # dB

TX_EIRP = gNB_transmit_power + Antenne_gain
RE_Power = 10 * math.log10(
    10 ** (TX_EIRP / 10) * Sub_carrier_spacing / (BW * 0.9 * 1000)
)

# Reference-lokation fra jeres eksisterende kode
Drone_Lokation = (57.026180, 9.747177)


# --------------------------------------------------
# Teoretiske modeller
# --------------------------------------------------

def Teoretisk_RASP_FSPL(afstand_km, carrier_frequency_mhz, re_power):
    if afstand_km <= 0:
        raise ValueError("Afstand skal være større end 0 km")

    pathloss = (
        20 * math.log10(afstand_km)
        + 20 * math.log10(carrier_frequency_mhz)
        + 32.44
    )
    rsrp = re_power - pathloss
    return pathloss, rsrp


def Teoretisk_SNR(rsrp, thermal_noise, noise_figure, scs_khz):
    scs_hz = scs_khz * 1000
    noise_floor = thermal_noise + noise_figure + 10 * math.log10(scs_hz)
    return rsrp - noise_floor


# --------------------------------------------------
# Hjælpefunktioner
# --------------------------------------------------

def afstand_km(coord1, coord2):
    lat1, lon1 = coord1
    lat2, lon2 = coord2

    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def float_sikkert(value):
    if value is None:
        raise ValueError("Tom værdi")

    text = str(value).strip()
    text = text.replace(",", ".")
    text = text.split()[0]

    return float(text)


def hent_testnr_fra_path(file_path):
    match = re.search(r"test(\d+)", file_path, re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def height_group(height_value):
    if height_value is None:
        return "120m"

    try:
        h = float(height_value)
    except ValueError:
        return "120m"

    if abs(h - 15.0) < 0.6:
        return "15m"

    return "120m"


# --------------------------------------------------
# Læs testlist.csv
# --------------------------------------------------

def læs_test_metadata():
    csv_path = os.path.join(DATA_DIR, "testlist.csv")
    metadata = {}

    if not os.path.exists(csv_path):
        print(f"ADVARSEL: testlist.csv blev ikke fundet: {csv_path}")
        return metadata

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as csv_file:
        sample = csv_file.read(4096)
        csv_file.seek(0)

        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;")
        except csv.Error:
            dialect = csv.excel

        reader = csv.DictReader(csv_file, dialect=dialect)

        for row in reader:
            clean_row = {}
            for key, value in row.items():
                if key is not None:
                    clean_row[key.strip().lower()] = value

            try:
                testnr = int(str(clean_row.get("testnr", "")).strip())
                latitude = float_sikkert(clean_row.get("latitude"))
                longitude = float_sikkert(clean_row.get("longitude"))
            except Exception:
                continue

            height_raw = clean_row.get("height")
            height_m = None

            if height_raw not in (None, ""):
                try:
                    height_m = float_sikkert(height_raw)
                except Exception:
                    height_m = None

            metadata[testnr] = {
                "lat_lon": (latitude, longitude),
                "height_m": height_m,
            }

    return metadata


# --------------------------------------------------
# Læs målefiler
# --------------------------------------------------

def læs_rsrp_snr_fra_fil(file_path):
    rsrp_values = []
    snr_values = []

    with open(file_path, "r", encoding="utf-8-sig", errors="ignore") as file:
        for line in file:
            line = line.strip()

            if not line:
                continue

            try:
                obj = json.loads(line)

                if "rsrp" in obj and "snr" in obj:
                    rsrp_values.append(float_sikkert(obj["rsrp"]))
                    snr_values.append(float_sikkert(obj["snr"]))
                    continue

            except Exception:
                pass

            rsrp_match = re.search(r'"?rsrp"?\s*[:=]\s*"?(-?\d+(?:[.,]\d+)?)', line, re.IGNORECASE)
            snr_match = re.search(r'"?snr"?\s*[:=]\s*"?(-?\d+(?:[.,]\d+)?)', line, re.IGNORECASE)

            if rsrp_match and snr_match:
                rsrp_values.append(float_sikkert(rsrp_match.group(1)))
                snr_values.append(float_sikkert(snr_match.group(1)))

    if not rsrp_values or not snr_values:
        raise ValueError("Ingen RSRP/SNR fundet")

    rsrp_mean = sum(rsrp_values) / len(rsrp_values)
    snr_mean = sum(snr_values) / len(snr_values)

    return rsrp_mean, snr_mean


def læs_alle_målinger():
    metadata = læs_test_metadata()

    file_paths = []
    file_paths.extend(glob.glob(os.path.join(DATA_DIR, "**", "*.json"), recursive=True))
    file_paths.extend(glob.glob(os.path.join(DATA_DIR, "**", "*.test"), recursive=True))

    resultater = []

    for file_path in file_paths:
        try:
            rsrp_mean, snr_mean = læs_rsrp_snr_fra_fil(file_path)
            testnr = hent_testnr_fra_path(file_path)

            meta = metadata.get(testnr, {})
            lat_lon = meta.get("lat_lon")
            height_m = meta.get("height_m")

            if lat_lon is None:
                continue

            afstand = afstand_km(Drone_Lokation, lat_lon)

            resultater.append({
                "filnavn": os.path.relpath(file_path, DATA_DIR),
                "testnr": testnr,
                "afstand": afstand,
                "rsrp": rsrp_mean,
                "snr": snr_mean,
                "height_m": height_m,
                "gruppe": height_group(height_m),
            })

        except Exception as exc:
            print(f"Springer over: {os.path.relpath(file_path, DATA_DIR)} ({exc})")

    resultater.sort(key=lambda item: (item["afstand"], item["filnavn"]))
    return resultater


# --------------------------------------------------
# Lav grafer
# --------------------------------------------------

def lav_grafer():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    målinger = læs_alle_målinger()

    if not målinger:
        raise ValueError(
            "Ingen gyldige målinger fundet.\n"
            f"Tjek at DATA-folderen findes her: {DATA_DIR}\n"
            "Tjek også at testlist.csv indeholder testnr, latitude, longitude og height."
        )

    afstande = [item["afstand"] for item in målinger]
    min_afstand = max(min(afstande), 0.001)
    max_afstand = max(max(afstande), min_afstand + 0.1)

    kurve_x = [
        min_afstand + (max_afstand - min_afstand) * i / 249
        for i in range(250)
    ]

    fspl_rsrp = []
    fspl_snr = []
    fspl_pathloss = []

    for afstand in kurve_x:
        fspl = Teoretisk_RASP_FSPL(afstand, Carrier_Frequency, RE_Power)

        fspl_pathloss.append(fspl[0])
        fspl_rsrp.append(fspl[1])
        fspl_snr.append(
            Teoretisk_SNR(fspl[1], Thermal_Noise, NoiseFigure, Sub_carrier_spacing)
        )

    for item in målinger:
        item["pathloss"] = RE_Power - item["rsrp"]

    def plot_graf(titel, y_key, y_label, filnavn, fspl_y):
        plt.figure(figsize=(10, 6))

        for gruppe, marker in [("15m", "o"), ("120m", "^")]:
            punkter = [item for item in målinger if item["gruppe"] == gruppe]

            if not punkter:
                continue

            plt.scatter(
                [item["afstand"] for item in punkter],
                [item[y_key] for item in punkter],
                marker=marker,
                s=55,
                label=f"Målt {gruppe}",
            )

        plt.plot(kurve_x, fspl_y, linewidth=2, label="FSPL")

        plt.title(titel)
        plt.xlabel("Afstand (km)")
        plt.ylabel(y_label)
        plt.grid(True, alpha=0.3)
        plt.legend()
        plt.tight_layout()

        output_path = os.path.join(OUTPUT_DIR, filnavn)
        plt.savefig(output_path, dpi=150)
        plt.close()

        return output_path

    rsrp_path = plot_graf(
        "RSRP som funktion af afstand",
        "rsrp",
        "RSRP (dBm)",
        "rsrp_plot.png",
        fspl_rsrp,
    )

    snr_path = plot_graf(
        "SNR som funktion af afstand",
        "snr",
        "SNR (dB)",
        "snr_plot.png",
        fspl_snr,
    )

    pathloss_path = plot_graf(
        "Pathloss som funktion af afstand",
        "pathloss",
        "Pathloss (dB)",
        "pathloss_plot.png",
        fspl_pathloss,
    )

    print("")
    print("Grafer lavet:")
    print(f"RSRP     : {rsrp_path}")
    print(f"SNR      : {snr_path}")
    print(f"Pathloss : {pathloss_path}")
    print("")
    print(f"Antal målinger brugt: {len(målinger)}")
    print(f"Output-folder: {OUTPUT_DIR}")


if __name__ == "__main__":
    lav_grafer()
