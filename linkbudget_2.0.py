"""
5G Link Budget GUI — Group 230, AAU P2 2026
============================================
Pathloss-modeller fra rapporten:
  FSPL  : Ligning 3.5  — 20log10(d) + 20log10(f) + 32.45   (d i km, f i MHz)
  CI    : Ligning 3.10 — 32.45 + 20log10(fc[GHz]) + 10n*log10(d[m]) + χ
  CIH   : Ligning 3.11 — CI med højdekorrektion af n via b_tx og h_B0
  3GPP  : Ligning 3.6/3.7 — RMa LOS med breakpoint (fc i GHz, d i m)

Uplink   = van (gNB) → drone (UE)
Downlink = drone (UE) → van (gNB)

Default-værdier fra mail (Miguel) og SCU2070-datablade:
  Tx power gNB  : 35 dBm   (uplink sender, fra mailen)
  Tx power UE   : 23 dBm   (downlink sender, fra mailen)
  gNB ant. gain : 11 dBi   (SCU2070: ANT1≈11.5 dBi @ 3700 MHz,
                              ANT2≈11.0 dBi @ 3700–3800 MHz; fra databladet)
  UE  ant. gain : -5 dBi   (2JW1183-C952B @ 3780 MHz; ikke optimeret til
                              n78-båndet — fra mailen)
  Kabeltab gNB  : 2  dB    (lange kabler, fra mailen)
  Kabeltab UE   : 0.5 dB   (korte kabler, fra mailen)
  Frekvens      : 3780 MHz  (n78-bånd, fra mailen)
  Sensitivity   : -102 dBm  (Teltonika 5G modem; termisk støjgulv
                              20 MHz + NF≈7 dB + SNR_min≈-6 dB ≈ -100 dBm.
                              NB: -120/-125 dBm er RSRP-threshold per
                              subcarrier (Ligning 3.19), IKKE Prx-sensitivity)
  Fade margin   : 10 dB
  gNB-højde     : 1.5 m     (på mast ved bil, fra test-design)
  UE-højde      : 120 m     (max dronealtitude i testen)
  Bygningshøjde : 5 m
  CI n          : 2.0
  Shadow fading : 0 dB
  CIH b_tx      : 0.03
  CIH h_B0      : 35 m

FSPL-modellen er rent n=2 uden breakpoint — Ligning 3.5:
  PL = 20·log10(d[km]) + 20·log10(f[MHz]) + 32.45
Two-ray ground-reflection antages først at dominere ved ~70 km
(uden for scenariets relevante rækkevidde).
"""

import tkinter as tk
from tkinter import ttk, messagebox

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


# ── Farver til graferne ───────────────────────────────────────────────────────
CLR = {
    "uplink"  : "#2196F3",
    "downlink": "#E91E63",
    "zero"    : "#F44336",
}

C = 3e8          # lysets hastighed [m/s]
D0 = 1.0         # CI-referenceafstand [m]


class LinkBudgetGUI:
    """Simpel 5G-linkbudget-GUI med uplink og downlink."""

    MAX_SEARCH_KM = 10_000.0

    # ── Felter: (label, nøgle, default, enhed) ────────────────────────────────
    UL_FIELDS = [
        ("Tx power",         "ul_tx_dbm",   35.0,  "dBm"),
        ("Tx ant. gain",     "ul_tx_dbi",   11.0,  "dBi"),
        ("Tx kabeltab",      "ul_tx_loss",   2.0,  "dB"),
        ("Rx ant. gain",     "ul_rx_dbi",   -5.0,  "dBi"),
        ("Rx kabeltab",      "ul_rx_loss",   0.5,  "dB"),
        ("Sensitivity",      "ul_sens_dbm", -102.0,"dBm"),
    ]

    DL_FIELDS = [
        ("Tx power",         "dl_tx_dbm",   23.0,  "dBm"),
        ("Tx ant. gain",     "dl_tx_dbi",   -5.0,  "dBi"),
        ("Tx kabeltab",      "dl_tx_loss",   0.5,  "dB"),
        ("Rx ant. gain",     "dl_rx_dbi",   11.0,  "dBi"),
        ("Rx kabeltab",      "dl_rx_loss",   2.0,  "dB"),
        ("Sensitivity",      "dl_sens_dbm", -102.0,"dBm"),
    ]

    COMMON_FIELDS = [
        ("Øvrige tab",       "misc_loss",    0.0,  "dB"),
        ("Fade margin",      "fade_margin", 10.0,  "dB"),
        ("Frekvens",         "freq_mhz",  3780.0,  "MHz"),
        ("Min. afstand",     "min_dist_m", 118.0,  "m"),
        ("Plotafstand",      "plot_km",     50.0,  "km"),
        ("gNB-højde h_t",    "h_gnb",        1.5,  "m"),
        ("UE-højde h_r",     "h_ue",       120.0,  "m"),
        ("Bygningshøjde h",  "h_bld",        5.0,  "m"),
        ("CI n",             "ci_n",         2.0,  "-"),
        ("Shadow fading σ",  "shadow_db",    0.0,  "dB"),
        ("CIH b_tx",         "cih_btx",     0.03,  "-"),
        ("CIH h_B0",         "cih_hb0",     35.0,  "m"),
    ]

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("5G Link Budget — AAU Gruppe 230")
        self.root.geometry("1380x800")

        self.model_var = tk.StringVar(value="FSPL")
        self.vars: dict[str, tk.StringVar] = {}
        self.result_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Klar")
        self._busy = False          # forhindrer rekursion ved auto-plot

        self._build_gui()
        self._attach_traces()
        self._auto_plot_distance()
        self._calculate()

    # ── GUI-opbygning ─────────────────────────────────────────────────────────

    def _build_gui(self):
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # Venstre inputpanel
        left = ttk.LabelFrame(main, text="Input", padding=10)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        # Modelvalg
        ttk.Label(left, text="Pathloss-model").grid(row=0, column=0, sticky="w")
        cb = ttk.Combobox(left, textvariable=self.model_var,
                          values=["FSPL", "CI", "CIH", "3GPP RMa LOS"],
                          state="readonly", width=18)
        cb.grid(row=0, column=1, columnspan=3, sticky="ew", padx=5)
        cb.bind("<<ComboboxSelected>>", lambda _: self._calculate())

        # Uplink / Downlink kolonner
        link_frame = ttk.Frame(left)
        link_frame.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(8, 4))
        self._build_dir_col(link_frame, "Uplink  van → drone", self.UL_FIELDS, col=0)
        self._build_dir_col(link_frame, "Downlink  drone → van", self.DL_FIELDS, col=1)

        # Fælles parametre
        com = ttk.LabelFrame(left, text="Fælles parametre", padding=8)
        com.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        for r, (lbl, key, default, unit) in enumerate(self.COMMON_FIELDS):
            ttk.Label(com, text=lbl).grid(row=r, column=0, sticky="w", pady=2)
            v = tk.StringVar(value=str(default))
            self.vars[key] = v
            ttk.Entry(com, textvariable=v, width=10).grid(row=r, column=1, padx=5)
            ttk.Label(com, text=unit).grid(row=r, column=2, sticky="w")

        # Knapper
        for i, (txt, cmd) in enumerate([
            ("Beregn",          self._calculate),
            ("Auto plotafstand",self._auto_plot_distance),
            ("Nulstil",         self._reset),
        ]):
            ttk.Button(left, text=txt, command=cmd).grid(
                row=3 + i, column=0, columnspan=4, sticky="ew", pady=(6 if i == 0 else 2, 2))

        ttk.Label(left, textvariable=self.result_var, justify="left",
                  font=("Segoe UI", 8), wraplength=370).grid(
            row=6, column=0, columnspan=4, sticky="w", pady=(10, 0))

        # Højre: Matplotlib-figur
        right = ttk.Frame(main)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.fig, (self.ax_ul, self.ax_dl) = plt.subplots(2, 1, figsize=(9, 6.5), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        ttk.Label(self.root, textvariable=self.status_var,
                  relief=tk.SUNKEN, anchor="w").pack(side=tk.BOTTOM, fill=tk.X)

    def _build_dir_col(self, parent, title, fields, col):
        """Byg én inputkolonne (uplink eller downlink)."""
        pad = (0, 8) if col == 0 else (8, 0)
        frame = ttk.LabelFrame(parent, text=title, padding=8)
        frame.grid(row=0, column=col, sticky="n", padx=pad)
        for r, (lbl, key, default, unit) in enumerate(fields):
            ttk.Label(frame, text=lbl).grid(row=r, column=0, sticky="w", pady=2)
            v = tk.StringVar(value=str(default))
            self.vars[key] = v
            ttk.Entry(frame, textvariable=v, width=9).grid(row=r, column=1, padx=4)
            ttk.Label(frame, text=unit).grid(row=r, column=2, sticky="w")

    def _attach_traces(self):
        for v in self.vars.values():
            v.trace_add("write", lambda *_: self._calculate())

    # ── Inputlæsning og validering ────────────────────────────────────────────

    def _all_fields(self):
        return self.UL_FIELDS + self.DL_FIELDS + self.COMMON_FIELDS

    def _read(self) -> dict:
        """Læs alle inputfelter som float (komma → punktum)."""
        p = {}
        for _, key, _, _ in self._all_fields():
            p[key] = float(self.vars[key].get().replace(",", ".").strip())
        return p

    def _validate(self, p: dict):
        if p["freq_mhz"] <= 0:
            raise ValueError("Frekvens > 0 MHz krævet")
        if p["plot_km"] <= 0:
            raise ValueError("Plotafstand > 0 km krævet")
        if p["h_gnb"] <= 0 or p["h_ue"] <= 0:
            raise ValueError("Antennehøjder > 0 m krævet")
        if p["ci_n"] <= 0:
            raise ValueError("CI pathloss-eksponent n > 0 krævet")
        if p["h_bld"] <= 0:
            raise ValueError("Bygningshøjde > 0 m krævet")
        if p["cih_hb0"] <= 0:
            raise ValueError("CIH h_B0 > 0 m krævet")

    # ── 3D-afstand ────────────────────────────────────────────────────────────

    def _d3d_m(self, d2d_km, p: dict) -> np.ndarray:
        """
        3D-afstand [m] fra 2D-afstand [km].
        d3D = sqrt(d2D² + Δh²)
        """
        d2d_m = np.asarray(d2d_km) * 1e3
        dh = p["h_gnb"] - p["h_ue"]
        return np.sqrt(d2d_m**2 + dh**2)

    # ── Pathloss-modeller ─────────────────────────────────────────────────────

    def _pl_fspl(self, d2d_km, p: dict) -> np.ndarray:
        """
        Rent FSPL, n=2 — Ligning 3.5:
          PL = 20*log10(d[km]) + 20*log10(f[MHz]) + 32.45
        """
        d3d_km = np.maximum(self._d3d_m(d2d_km, p), 1.0) / 1e3
        return 20*np.log10(d3d_km) + 20*np.log10(p["freq_mhz"]) + 32.45

    def _pl_ci(self, d2d_km, p: dict) -> np.ndarray:
        """
        CI-modellen — Ligning 3.10:
          PL = 32.45 + 20*log10(fc[GHz]) + 10*n*log10(d[m]) + σ
        Referenceafstand d0 = 1 m.
        """
        d3d_m  = np.maximum(self._d3d_m(d2d_km, p), D0)
        fc_ghz = p["freq_mhz"] / 1e3
        fspl_1m = 32.45 + 20*np.log10(fc_ghz)          # FSPL ved 1 m, fc i GHz
        return fspl_1m + 10*p["ci_n"]*np.log10(d3d_m) + p["shadow_db"]

    def _pl_cih(self, d2d_km, p: dict) -> np.ndarray:
        """
        CIH-modellen — Ligning 3.11:
          PL = FSPL(1m) + 10 * n_eff * log10(d[m]) + σ
        n_eff = n * [ (1 - b_tx) + b_tx * h_BS / h_B0 ]
        Korrektion gælder h_BS ∈ [10, 150] m ifølge rapporten.
        """
        d3d_m   = np.maximum(self._d3d_m(d2d_km, p), D0)
        fc_ghz  = p["freq_mhz"] / 1e3
        fspl_1m = 32.45 + 20*np.log10(fc_ghz)
        n_eff   = p["ci_n"] * ((1 - p["cih_btx"]) + p["cih_btx"] * p["h_gnb"] / p["cih_hb0"])
        return fspl_1m + 10*n_eff*np.log10(d3d_m) + p["shadow_db"]

    def _pl_3gpp(self, d2d_km, p: dict) -> np.ndarray:
        """
        3GPP RMa LOS — Ligning 3.6 / 3.7:
          PL1 (d ≤ d_BP):
            20*log10(40π*d3D*fc/3) + min(0.03*h^1.72, 10)*log10(d3D)
            - min(0.044*h^1.72, 14.77) + 0.002*log10(h)*d3D
          PL2 (d > d_BP):
            PL1(d_BP) + 40*log10(d3D / d_BP)

        fc i GHz, d i m, h = bygningshøjde [m].
        Breakpoint (Ligning 3.14, Rappaport):
          d_BP = 4 * h_t * h_r * f / c
        """
        d3d_m  = np.maximum(self._d3d_m(d2d_km, p), 1.0)
        fc_ghz = p["freq_mhz"] / 1e3
        fc_hz  = p["freq_mhz"] * 1e6
        h      = p["h_bld"]

        # Breakpoint-afstand [m] — Ligning 3.14
        d_bp = max(4 * p["h_gnb"] * p["h_ue"] * fc_hz / C, 1.0)

        c1 = min(0.03 * h**1.72, 10.0)
        c2 = min(0.044 * h**1.72, 14.77)

        def pl1(d):
            return (20*np.log10(40*np.pi * d * fc_ghz / 3)
                    + c1 * np.log10(d)
                    - c2
                    + 0.002 * np.log10(h) * d)

        pl_bp = pl1(d_bp)

        return np.where(
            d3d_m <= d_bp,
            pl1(d3d_m),
            pl_bp + 40*np.log10(d3d_m / d_bp),
        )

    def _pathloss(self, d2d_km, p: dict) -> np.ndarray:
        m = self.model_var.get()
        if m == "FSPL":          return self._pl_fspl(d2d_km, p)
        if m == "CI":            return self._pl_ci(d2d_km, p)
        if m == "CIH":           return self._pl_cih(d2d_km, p)
        if m == "3GPP RMa LOS":  return self._pl_3gpp(d2d_km, p)
        raise ValueError(f"Ukendt model: {m}")

    # ── Link-budget for én retning ────────────────────────────────────────────

    def _link(self, direction: str, d_km, pl_db, p: dict) -> dict:
        """
        Beregn EIRP, Prx og link margin for uplink eller downlink.

        EIRP  = P_tx + G_tx - L_tx                        [dBm]
        Prx   = EIRP + G_rx - L_rx - misc_loss - PL       [dBm]  (Ligning 3.20 udvidet)
        Margin = Prx - sensitivity - fade_margin           [dB]
        """
        if direction == "uplink":
            tx, g_tx, l_tx = p["ul_tx_dbm"], p["ul_tx_dbi"], p["ul_tx_loss"]
            g_rx, l_rx     = p["ul_rx_dbi"],  p["ul_rx_loss"]
            sens           = p["ul_sens_dbm"]
        else:
            tx, g_tx, l_tx = p["dl_tx_dbm"], p["dl_tx_dbi"], p["dl_tx_loss"]
            g_rx, l_rx     = p["dl_rx_dbi"],  p["dl_rx_loss"]
            sens           = p["dl_sens_dbm"]

        eirp   = tx + g_tx - l_tx
        prx    = eirp + g_rx - l_rx - p["misc_loss"] - pl_db
        margin = prx - sens - p["fade_margin"]

        rng_km, limited = self._find_range(d_km, margin)
        return {"eirp": eirp, "prx": prx, "margin": margin,
                "range_km": rng_km, "limited": limited}

    # ── Rækkevidde-interpolation ──────────────────────────────────────────────

    def _find_range(self, d_km, margin):
        """
        Find den interpolerede afstand [km] hvor link margin = 0 dB.
        Returnerer (rækkevidde_km, er_begrænset_af_plotafstand).
        """
        if not np.any(margin >= 0):
            return 0.0, False
        if margin[-1] >= 0:
            return float(d_km[-1]), True

        idx = np.where(margin >= 0)[0][-1]
        # Lineær interpolation i log10(d)-domænet
        x1, x2 = np.log10(d_km[idx]), np.log10(d_km[idx + 1])
        y1, y2 = margin[idx],          margin[idx + 1]
        x0 = x1 + (0 - y1) * (x2 - x1) / (y2 - y1)
        return float(10**x0), False

    # ── Afstandsarray ─────────────────────────────────────────────────────────

    def _distances(self, max_km: float, min_km: float = 0.118) -> np.ndarray:
        """1200 logaritmisk fordelte punkter fra min_km til max_km."""
        return np.logspace(np.log10(max(min_km, 1e-6)),
                           np.log10(max(float(max_km), min_km * 1.01)),
                           1200)

    # ── Auto plotafstand ──────────────────────────────────────────────────────

    def _full_range_km(self, direction: str, p: dict) -> float:
        """Udvid søgeafstand til link margin krydser 0 dB."""
        max_km = 1.0
        min_km = p.get("min_dist_m", 118.0) / 1000
        while max_km <= self.MAX_SEARCH_KM:
            d = self._distances(max_km, min_km)
            pl = self._pathloss(d, p)
            res = self._link(direction, d, pl, p)
            if not res["limited"]:
                return res["range_km"]
            max_km *= 2.0
        return self.MAX_SEARCH_KM

    def _auto_plot_distance(self):
        """Sæt plotafstand = 1.5 × uplink-rækkevidde."""
        try:
            self._busy = True
            p = self._read()
            p["plot_km"] = max(p.get("plot_km", 1.0), 1.0)
            self._validate(p)
            ul_range = self._full_range_km("uplink", p)
            self.vars["plot_km"].set(f"{max(ul_range * 1.5, 1.0):.2f}")
        except Exception:
            pass
        finally:
            self._busy = False
            self._calculate()

    # ── Hoved-beregning og plot ───────────────────────────────────────────────

    def _calculate(self):
        if self._busy:
            return
        try:
            p = self._read()
            self._validate(p)

            d_km = self._distances(p["plot_km"], p["min_dist_m"] / 1000)
            pl   = self._pathloss(d_km, p)

            ul = self._link("uplink",   d_km, pl, p)
            dl = self._link("downlink", d_km, pl, p)

            ul_eff = p["plot_km"] if ul["limited"] else ul["range_km"]
            dl_eff = p["plot_km"] if dl["limited"] else dl["range_km"]
            sys_range = min(ul_eff, dl_eff)

            self._update_text(ul, dl, sys_range, p)
            self._plot(d_km, ul, dl)
            self.status_var.set(f"Systemrækkevidde: {sys_range:.2f} km")

        except ValueError as e:
            self.status_var.set(f"Inputfejl: {e}")
        except Exception as e:
            self.status_var.set(f"Fejl: {e}")
            messagebox.showerror("Fejl", str(e))

    # ── Resultattekst ─────────────────────────────────────────────────────────

    def _fmt_range(self, res: dict) -> str:
        prefix = "≥ " if res["limited"] else ""
        return f"{prefix}{res['range_km']:.2f} km"

    def _update_text(self, ul, dl, sys_range, p):
        txt = (
            f"Systemrækkevidde   : {sys_range:.2f} km\n"
            f"Plotafstand        : {p['plot_km']:.2f} km\n\n"
            f"Uplink  (van→drone): {self._fmt_range(ul)}\n"
            f"  EIRP = {ul['eirp']:.1f} dBm\n"
            f"Downlink(drone→van): {self._fmt_range(dl)}\n"
            f"  EIRP = {dl['eirp']:.1f} dBm"
        )
        if p["ul_sens_dbm"] < -110 or p["dl_sens_dbm"] < -110:
            txt += "\n\n⚠ Sensitivity < -110 dBm: tjek at det er Prx-sensitivity,\n  ikke RSRP-threshold (Ligning 3.19)"
        self.result_var.set(txt)

    # ── Plot ──────────────────────────────────────────────────────────────────

    def _plot(self, d_km, ul, dl):
        self.ax_ul.clear()
        self.ax_dl.clear()
        self._plot_dir(self.ax_ul, d_km, ul, CLR["uplink"],   "Uplink: van → drone")
        self._plot_dir(self.ax_dl, d_km, dl, CLR["downlink"], "Downlink: drone → van")
        self.fig.tight_layout(pad=2.0)
        self.canvas.draw()

    def _plot_dir(self, ax, d_km, res, color, title):
        margin  = res["margin"]
        rng_km  = res["range_km"]
        limited = res["limited"]

        ax.plot(d_km, margin, color=color, lw=2, label="Link margin")
        ax.axhline(0, color=CLR["zero"], ls="--", label="0 dB")

        if rng_km > 0:
            ax.axvline(rng_km, color=color, ls=":", label="Rækkevidde")
            ax.scatter([rng_km], [0], color=color, s=30, zorder=5)

        ax.fill_between(d_km, margin, 0, where=margin >= 0,
                        color=color, alpha=0.12)

        if rng_km > 0:
            lbl = f"Rækkevidde: {'≥ ' if limited else ''}{rng_km:.2f} km"
            ax.text(0.02, 0.95, lbl, transform=ax.transAxes, fontsize=6,
                    va="top", bbox=dict(boxstyle="round,pad=0.2",
                                        facecolor="white", alpha=0.8, edgecolor="none"))

        ax.set_xscale("log")
        ax.set_xlim(d_km[0], d_km[-1])
        ax.set_title(title, fontsize=7)
        ax.set_xlabel("Afstand [km]", fontsize=8)
        ax.set_ylabel("Link margin [dB]", fontsize=8)
        ax.tick_params(axis="both", labelsize=7)
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(fontsize=6)

    # ── Nulstil ───────────────────────────────────────────────────────────────

    def _reset(self):
        self.model_var.set("FSPL")
        self._busy = True
        for _, key, default, _ in self._all_fields():
            self.vars[key].set(str(default))
        self._busy = False
        self._auto_plot_distance()


if __name__ == "__main__":
    root = tk.Tk()
    LinkBudgetGUI(root)
    root.mainloop()