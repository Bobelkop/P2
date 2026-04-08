import FreeSimpleGUI as sg
import Rasp as rasp


def _to_float(value, default):
    value = (value or "").strip()
    if value == "":
        return default
    return float(value)


def _linkbudget_from_gui(values):
    carrier_frequency = _to_float(values["-CF-"], float(rasp.Carrier_Frequency))
    gnb_tx_power = _to_float(values["-TXP-"], float(rasp.gNB_transmit_power))
    antenna_gain = _to_float(values["-GAIN-"], float(rasp.Antenne_gain))
    bw_mhz = _to_float(values["-BW-"], float(rasp.BW))
    scs_khz = _to_float(values["-SCS-"], float(rasp.Sub_carrier_spacing))
    thermal_noise = _to_float(values["-TN-"], float(rasp.Thermal_Noise))
    noise_figure = _to_float(values["-NF-"], float(rasp.NoiseFigure))

    tx_eirp = gnb_tx_power + antenna_gain
    re_power = 10 * __import__("numpy").log10(10 ** (tx_eirp / 10) * (scs_khz) / (bw_mhz * 0.9 * 1000))

    return {
        "carrier_frequency": carrier_frequency,
        "bw_mhz": bw_mhz,
        "scs_khz": scs_khz,
        "thermal_noise": thermal_noise,
        "noise_figure": noise_figure,
        "re_power": re_power,
    }


def _run_t_mode(values):
    afstand = _to_float(values["-AFSTAND-T-"], 1.0)
    lb = _linkbudget_from_gui(values)

    fspl = rasp.Teoretisk_RASP_FSPL(afstand, lb["carrier_frequency"], lb["re_power"])
    hata = rasp.Teoretisk_RASP_Hata(afstand, lb["carrier_frequency"], lb["re_power"])
    snr_fspl = rasp.Teoretisk_SNR(fspl[1], lb["thermal_noise"], lb["noise_figure"], lb["scs_khz"])
    snr_hata = rasp.Teoretisk_SNR(hata[1], lb["thermal_noise"], lb["noise_figure"], lb["scs_khz"])

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
        "Hata:",
        f"Pathloss: {hata[0]:.2f} dB",
        f"RSRP: {hata[1]:.2f} dBm",
        f"Teoretisk SNR: {snr_hata:.2f} dB",
    ]
    return "\n".join(lines)


def _measurement_defaults_from_files():
    resultater = rasp.alle_målinger_fra_json()
    if not resultater:
        return "", ""

    rsrp_ref = sum(item["rsrp"] for item in resultater.values()) / len(resultater)
    snr_ref = sum(item["snr"] for item in resultater.values()) / len(resultater)
    return f"{rsrp_ref:.2f}", f"{snr_ref:.2f}"


def _run_m_mode(values):
    drone_input = (values["-DRONE-M-"] or "").strip()
    drone_lokation = drone_input if drone_input else f"{rasp.Drone_Lokation[0]},{rasp.Drone_Lokation[1]}"

    gnb_input = (values["-GNB-M-"] or "").strip()
    gnb_lokation = gnb_input if gnb_input else "57.0180391,9.7602773"
    lb = _linkbudget_from_gui(values)
    afstand_manual = rasp.Afstandsformel(drone_lokation, gnb_lokation)

    # Brug gennemsnit af filer som standard, men lad manuel input overstyre.
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
    hata = rasp.Teoretisk_RASP_Hata(afstand_manual, lb["carrier_frequency"], lb["re_power"])
    snr_fspl = rasp.Teoretisk_SNR(fspl[1], lb["thermal_noise"], lb["noise_figure"], lb["scs_khz"])
    snr_hata = rasp.Teoretisk_SNR(hata[1], lb["thermal_noise"], lb["noise_figure"], lb["scs_khz"])
    afv_rsrp_fspl = rasp.Afvigelse_Af_Målinger_På_Teori_RSRP(målt_rsrp, fspl[1])
    afv_rsrp_hata = rasp.Afvigelse_Af_Målinger_På_Teori_RSRP(målt_rsrp, hata[1])
    afv_snr_fspl = snr_fspl - målt_snr
    afv_snr_hata = snr_hata - målt_snr

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
        f"  Afvigelse ift. RSRP-måling: {afv_rsrp_fspl:.2f} %",
        "",
        "Hata",
        f"  Pathloss: {hata[0]:.2f} dB",
        f"  RSRP: {hata[1]:.2f} dBm",
        f"  SNR: {snr_hata:.2f} dB",
        f"  Afvigelse ift SNR: {afv_snr_hata:.2f} dB",
        f"  Afvigelse ift. RSRP-måling: {afv_rsrp_hata:.2f} %",
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
        "15m": {"fspl": [], "hata": []},
        "120m": {"fspl": [], "hata": []},
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

        if lat_lon is not None:
            afstand = data.get("afstand")
            if afstand is None:
                afstand = rasp.Afstandsformel(rasp.Drone_Lokation, lat_lon)
            coord_txt = f"{lat_lon[0]:.6f},{lat_lon[1]:.6f}"
        else:
            afstand = 0.0
            coord_txt = "-"

        fspl = rasp.Teoretisk_RASP_FSPL(afstand, lb["carrier_frequency"], lb["re_power"])
        hata = rasp.Teoretisk_RASP_Hata(afstand, lb["carrier_frequency"], lb["re_power"])
        snr_fspl = rasp.Teoretisk_SNR(fspl[1], lb["thermal_noise"], lb["noise_figure"], lb["scs_khz"])
        snr_hata = rasp.Teoretisk_SNR(hata[1], lb["thermal_noise"], lb["noise_figure"], lb["scs_khz"])

        målt_rsrp = data["rsrp"]
        målt_snr = data["snr"]

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

        rows_by_height[group_key]["hata"].append([
            test_label,
            coord_txt,
            f"{afstand:.2f}",
            f"{målt_rsrp:.2f}",
            f"{målt_snr:.2f}",
            f"{hata[1]:.2f}",
            f"{snr_hata:.2f}",
            f"{snr_hata - målt_snr:.2f}",
            f"{rasp.Afvigelse_Af_Målinger_På_Teori_RSRP(målt_rsrp, hata[1]):.2f}",
        ])

    count_15 = len(rows_by_height["15m"]["fspl"])
    count_120 = len(rows_by_height["120m"]["fspl"])
    status = f"Viser {count_15} testfiler på 15 m og {count_120} testfiler på 120 m."
    return rows_by_height, status


def main():
    default_m_rsrp, default_m_snr = _measurement_defaults_from_files()

    tab_settings = [
        [sg.Text("Indstillinger", font=("Segoe UI", 11, "bold"))],
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
        [sg.Text("Teoretisk mode", font=("Segoe UI", 11, "bold"))],
        [sg.Text("Afstand i km"), sg.Input("1.0", key="-AFSTAND-T-", size=(18, 1))],
        [sg.Button("Beregn", key="-BEREGN-T-", bind_return_key=True)],
        [sg.Multiline("", key="-OUT-T-", size=(95, 22), disabled=True, autoscroll=True, expand_x=True, expand_y=True)],
    ]

    tab_m = [
        [sg.Text("Måling", font=("Segoe UI", 11, "bold"))],
        [sg.Text("Drone lokation lat,lon"), sg.Input(f"{rasp.Drone_Lokation[0]},{rasp.Drone_Lokation[1]}", key="-DRONE-M-", size=(24, 1))],
        [sg.Text("gNB lokation lat,lon"), sg.Input("57.0180391,9.7602773", key="-GNB-M-", size=(24, 1))],
        [
            sg.Text("Målt RSRP (dBm)"), sg.Input(default_m_rsrp, key="-M-RSRP-", size=(12, 1)),
            sg.Text("Målt SNR (dB)"), sg.Input(default_m_snr, key="-M-SNR-", size=(12, 1)),
        ],
        [sg.Text("Tomme felter for Målt RSRP/SNR bruger standardværdier fra fil-data")],
        [sg.Button("Beregn", key="-BEREGN-M-")],
        [sg.Multiline("", key="-OUT-M-", size=(95, 22), disabled=True, autoscroll=True, expand_x=True, expand_y=True)],
    ]

    tab_data = [
        [sg.Text("Data", font=("Segoe UI", 11, "bold"))],
        [sg.Button("Opdater Data", key="-OPDATER-DATA-")],
        [
            sg.TabGroup(
                [[
                    sg.Tab(
                        "15 m",
                        [
                            [sg.Text("FSPL", font=("Segoe UI", 10, "bold"))],
                            [
                                sg.Table(
                                    values=[],
                                    headings=[
                                        "Test",
                                        "Koordinater",
                                        "Afstand (km)",
                                        "Målt RSRP",
                                        "Målt SNR",
                                        "Teoretisk RSRP",
                                        "Teoretisk SNR",
                                        "Afvigelse SNR",
                                        "Teoretisk afvigelse RSRP (%)",
                                    ],
                                    key="-DATA-TABEL-FSPL-15-",
                                    auto_size_columns=False,
                                    col_widths=[13, 16, 10, 10, 9, 11, 11, 12, 20],
                                    justification="left",
                                    num_rows=5,
                                    expand_x=True,
                                )
                            ],
                            [sg.Text("Hata", font=("Segoe UI", 10, "bold"))],
                            [
                                sg.Table(
                                    values=[],
                                    headings=[
                                        "Test",
                                        "Koordinater",
                                        "Afstand (km)",
                                        "Målt RSRP",
                                        "Målt SNR",
                                        "Teoretisk RSRP",
                                        "Teoretisk SNR",
                                        "Afvigelse SNR",
                                        "Teoretisk afvigelse RSRP (%)",
                                    ],
                                    key="-DATA-TABEL-HATA-15-",
                                    auto_size_columns=False,
                                    col_widths=[13, 16, 10, 10, 9, 11, 11, 12, 20],
                                    justification="left",
                                    num_rows=5,
                                    expand_x=True,
                                    expand_y=True,
                                )
                            ],
                        ],
                    ),
                    sg.Tab(
                        "120 m",
                        [
                            [sg.Text("FSPL", font=("Segoe UI", 10, "bold"))],
                            [
                                sg.Table(
                                    values=[],
                                    headings=[
                                        "Test",
                                        "Koordinater",
                                        "Afstand (km)",
                                        "Målt RSRP",
                                        "Målt SNR",
                                        "Teoretisk RSRP",
                                        "Teoretisk SNR",
                                        "Afvigelse SNR",
                                        "Teoretisk afvigelse RSRP (%)",
                                    ],
                                    key="-DATA-TABEL-FSPL-120-",
                                    auto_size_columns=False,
                                    col_widths=[13, 16, 10, 10, 9, 11, 11, 12, 20],
                                    justification="left",
                                    num_rows=5,
                                    expand_x=True,
                                )
                            ],
                            [sg.Text("Hata", font=("Segoe UI", 10, "bold"))],
                            [
                                sg.Table(
                                    values=[],
                                    headings=[
                                        "Test",
                                        "Koordinater",
                                        "Afstand (km)",
                                        "Målt RSRP",
                                        "Målt SNR",
                                        "Teoretisk RSRP",
                                        "Teoretisk SNR",
                                        "Afvigelse SNR",
                                        "Teoretisk afvigelse RSRP (%)",
                                    ],
                                    key="-DATA-TABEL-HATA-120-",
                                    auto_size_columns=False,
                                    col_widths=[13, 16, 10, 10, 9, 11, 11, 12, 20],
                                    justification="left",
                                    num_rows=5,
                                    expand_x=True,
                                    expand_y=True,
                                )
                            ],
                        ],
                    ),
                ]],
                expand_x=True,
                expand_y=True,
            )
        ],
        [sg.Text("", key="-DATA-STATUS-")],
    ]

    layout = [
        [sg.Text("RSRP Beregner (GUI)", font=("Segoe UI", 14, "bold"))],
        [
            sg.TabGroup(
                [[
                    sg.Tab("Teoretisk", tab_t),
                    sg.Tab("Måling", tab_m),
                    sg.Tab("Data", tab_data),
                    sg.Tab("Indstillinger", tab_settings),
                ]],
                expand_x=True,
            )
        ],
        [sg.Button("Luk")],
    ]

    window = sg.Window("RSRP FreeSimpleGUI", layout, finalize=True, resizable=True)
    try:
        window.maximize()
    except Exception:
        pass

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
                rows_by_height, status = _build_data_tables(values)
                window["-DATA-TABEL-FSPL-15-"].update(values=rows_by_height["15m"]["fspl"])
                window["-DATA-TABEL-HATA-15-"].update(values=rows_by_height["15m"]["hata"])
                window["-DATA-TABEL-FSPL-120-"].update(values=rows_by_height["120m"]["fspl"])
                window["-DATA-TABEL-HATA-120-"].update(values=rows_by_height["120m"]["hata"])
                window["-DATA-STATUS-"].update(status)
            except Exception as exc:
                window["-OUT-M-"].update(f"Fejl i Data: {exc}")

    window.close()


if __name__ == "__main__":
    main()
