import numpy as np
from geopy.distance import geodesic
import json
import glob
import os
import csv
import re
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
script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.join(script_dir, "DATA")
rows = []
# Til at finde alle JSON filer i undermapperne
file_paths = glob.glob(os.path.join(root_dir, "**", "*.json"), recursive=True)
testlist_csv_path = os.path.join(root_dir, "testlist.csv")

#print(f"Debug: Fundet {len(file_paths)} JSON filer")
#for fp in file_paths:
#    print(f"  - {fp}")

# Teoretisk RASP Hata 
def Teoretisk_RASP_Hata(data, Carrier_Frequency, RE_Power):
    Afstand = data #km
    if Afstand <= 0:
        raise ValueError("Afstand skal vaere stoerre end 0 km")
    pathloss =69.55 + 26.16 * np.log10(Carrier_Frequency) - 13.82 * np.log10(12) - 0.1 + ((44.9 - 6.55 * np.log10(12)) * np.log10(Afstand))  # dB
    RSRP = RE_Power - pathloss  # dBm
    return pathloss, RSRP


# Teoretisk RASP FSPL (Free Space Path Loss)
def Teoretisk_RASP_FSPL(data, Carrier_Frequency, RE_Power):
    Afstand = data  # km
    if Afstand <= 0:
        raise ValueError("Afstand skal vaere stoerre end 0 km")
    pathloss = 20 * np.log10(Afstand) + 20 * np.log10(Carrier_Frequency) + 32.44  # dB
    RSRP = RE_Power - pathloss  # dBm
    return pathloss, RSRP

def Afvigelse_Af_Målinger_På_Teori_RSRP(målinger,RSRP):
    Målt_RSRP = målinger
    if RSRP == 0:
        raise ValueError("RSRP maa ikke vaere 0 ved afvigelsesberegning")
    Afvigelse = ((Målt_RSRP - RSRP)/abs(RSRP))*100
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
    
    with open(file_path, "r", encoding="utf-8-sig") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                object = json.loads(line)
            except json.JSONDecodeError:
                # Spring ugyldige linjer over i stedet for at kassere hele filen.
                continue

            # Konverter rsrp og snr til float og tilføj til rows
            if "rsrp" not in object or "snr" not in object:
                continue

            rsrp_str = str(object["rsrp"]).replace(",", ".").split()[0]
            snr_str = str(object["snr"]).replace(",", ".").split()[0]

            try:
                object["rsrp.number"] = float(rsrp_str)
                object["snr.number"] = float(snr_str)
            except ValueError:
                continue

            rows.append(object)

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

            metadata[testnr] = {
                "lat_lon": (latitude, longitude),
                "height_m": height_m,
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

def alle_målinger_fra_json():
    resultater = {}
    test_metadata = Hent_Test_Metadata(testlist_csv_path)
    
    for file_path in file_paths:
        try:
            rsrp_mean, snr_mean = Data_Fra_Json([], file_path)
            filnavn = os.path.relpath(file_path, root_dir)
            testnr = hent_nummer_fra_path(file_path)
            meta = test_metadata.get(testnr, {})
            lat_lon = meta.get("lat_lon")
            height_m = meta.get("height_m")
            resultater[filnavn] = {
                'rsrp': rsrp_mean,
                'snr': snr_mean,
                'path': file_path,
                "testnr": testnr,
                "lat_lon": lat_lon,
                "height_m": height_m,
                "afstand": Afstandsformel(Drone_Lokation, lat_lon) if lat_lon else None
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
    
    return resultater


def _height_group(height_value):
    if height_value is None:
        return "120m"
    if abs(float(height_value) - 15.0) < 0.6:
        return "15m"
    return "120m"


def Lav_Grafer(carrier_frequency=None, re_power=None, thermal_noise=None, noise_figure=None, scs_khz=None):
    carrier_frequency = float(Carrier_Frequency if carrier_frequency is None else carrier_frequency)
    re_power = float(RE_Power if re_power is None else re_power)
    thermal_noise = float(Thermal_Noise if thermal_noise is None else thermal_noise)
    noise_figure = float(NoiseFigure if noise_figure is None else noise_figure)
    scs_khz = float(Sub_carrier_spacing if scs_khz is None else scs_khz)

    resultater = alle_målinger_fra_json()
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
        kurve_x = np.linspace(min_afstand, max_afstand, 250)
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

        plt.plot(kurve_x_meter, kurve_y, label="FSPL", color="#2ca02c", linewidth=2)
        plt.title(figur_navn)
        plt.xlabel("Afstand (m)")
        plt.ylabel(y_label)
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
        result_Hata = Teoretisk_RASP_Hata(afstand_input, Carrier_Frequency, RE_Power)
        print("--------------------------------------------------")
        print(f"Teoretisk RASP FSPL for {afstand_input} km:")
        print(f"Pathloss: {result_fspl[0]:.2f} dB")
        print(f"RSRP: {result_fspl[1]:.2f} dBm")
        print(f"Teoretisk SNR: {Teoretisk_SNR(result_fspl[1], Thermal_Noise, BW, NoiseFigure):.2f} dB")
        print("--------------------------------------------------")
        print(f"Teoretisk RASP Hata for {afstand_input} km:")
        print(f"Pathloss: {result_Hata[0]:.2f} dB")
        print(f"RSRP: {result_Hata[1]:.2f} dBm")
        print(f"Teoretisk SNR: {Teoretisk_SNR(result_Hata[1], Thermal_Noise, BW, NoiseFigure):.2f} dB")
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
            result_Hata = Teoretisk_RASP_Hata(afstand_fil, Carrier_Frequency, RE_Power)
            snr_fspl = Teoretisk_SNR(result_fspl[1], Thermal_Noise, NoiseFigure, Sub_carrier_spacing)
            snr_hata = Teoretisk_SNR(result_Hata[1], Thermal_Noise, NoiseFigure, Sub_carrier_spacing)

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

            print("Hata")
            print(f"  Teoretisk RSRP        : {result_Hata[1]:.2f} dBm")
            print(f"  Teoretisk SNR         : {snr_hata:.2f} dB")
            print(f"  Afvigelse RSRP        : {Afvigelse_Af_Målinger_På_Teori_RSRP(målt_rsrp, result_Hata[1]):.2f} %")
            print(f"  Afvigelse SNR         : {snr_hata - målt_snr:.2f} dB")

        print("=" * 62)







    else:
        print("Ugyldigt valg: vælg 'T' for teoretisk måling eller 'M' for sammenligning med målinger")




   



if __name__ == "__main__":
    main()
