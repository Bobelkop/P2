from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt


# Constant EIRP in dBm used for pathloss calculation: pathloss = RE_power - rsrp
DEFAULT_SNR_MIN_DB = 10.0
TARGET_PLMN = "99970"
MIN_DISTANCE_M = 100.0
REGRESSION_SPLIT_DISTANCE_M = 1000.0

Carrier_Frequency = 3779  # MHz
gNB_transmit_power = 35  # dBm
Antenne_gain = 10  # dB
TX_EIRP = gNB_transmit_power + Antenne_gain  # dBm
BW = 20  # MHz
Sub_carrier_spacing = 30  # kHz
RE_Power = 10 * np.log10(10 ** (TX_EIRP / 10) * (Sub_carrier_spacing) / (BW * 0.9 * 1000))  # dBm


def parse_snr_db(snr_text: str) -> float | None:
    cleaned = snr_text.replace("dB", "").strip().replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def load_data(
	log_path: Path,
	snr_min_db: float,
) -> tuple[list[float], list[float], list[dict[str, float | str]]]:
	distances_m: list[float] = []
	rsrp_dbm_list: list[float] = []
	filtered_points: list[dict[str, float | str]] = []

	with log_path.open("r", encoding="utf-8", newline="") as f:
		reader = csv.DictReader(f)
		required_columns = {
			"timestamp",
			"rsrp_dbm",
			"distance_m",
			"snr",
			"plmn",
			"latitude",
			"longitude",
		}
		if not reader.fieldnames or not required_columns.issubset(set(reader.fieldnames)):
			raise ValueError(
				"Inputfil mangler en eller flere af kolonnerne: "
				"'timestamp', 'rsrp_dbm', 'distance_m', 'snr', 'plmn', 'latitude', 'longitude'."
			)

		for row in reader:
			timestamp_text = (row.get("timestamp") or "").strip()
			rsrp_text = (row.get("rsrp_dbm") or "").strip()
			distance_text = (row.get("distance_m") or "").strip()
			snr_text = (row.get("snr") or "").strip()
			plmn_text = (row.get("plmn") or "").strip()
			lat_text = (row.get("latitude") or "").strip()
			lon_text = (row.get("longitude") or "").strip()

			if (
				not timestamp_text
				or not rsrp_text
				or not distance_text
				or not snr_text
				or not plmn_text
				or not lat_text
				or not lon_text
			):
				continue

			if plmn_text != TARGET_PLMN:
				continue

			snr_db = parse_snr_db(snr_text)
			if snr_db is None or snr_db <= snr_min_db:
				continue

			try:
				rsrp_dbm = float(rsrp_text)
				distance_m = float(distance_text)
				latitude = float(lat_text)
				longitude = float(lon_text)
			except ValueError:
				continue

			# Filter: distance must be >= MIN_DISTANCE_M.
			if distance_m < MIN_DISTANCE_M:
				continue

			pathloss = RE_Power - rsrp_dbm
			distances_m.append(distance_m)
			rsrp_dbm_list.append(rsrp_dbm)
			filtered_points.append(
				{
					"timestamp": timestamp_text,
					"longitude": longitude,
					"latitude": latitude,
					"rsrp_dbm": rsrp_dbm,
					"snr_db": snr_db,
					"plmn": plmn_text,
					"distance_m": distance_m,
					"pathloss_db": pathloss,
				}
			)

	if not distances_m:
		raise ValueError("Ingen gyldige datapunkter fundet til plotting.")

	return distances_m, rsrp_dbm_list, filtered_points


def save_filtered_points_log(
	points: list[dict[str, float | str]],
	output_path: Path,
) -> None:
	with output_path.open("w", encoding="utf-8", newline="") as f:
		writer = csv.writer(f)
		writer.writerow([
			"timestamp",
			"longitude",
			"latitude",
			"rsrp_dbm",
			"snr_db",
			"plmn",
			"distance_m",
			"pathloss_db",
		])

		for point in points:
			writer.writerow(
				[
					point["timestamp"],
					f"{float(point['longitude']):.8f}",
					f"{float(point['latitude']):.8f}",
					f"{float(point['rsrp_dbm']):.1f}",
					f"{float(point['snr_db']):.1f}",
					point["plmn"],
					f"{float(point['distance_m']):.2f}",
					f"{float(point['pathloss_db']):.2f}",
				]
			)


def fspl_db(distance_m: float) -> float:
	return 32.45 + 20 * math.log10(3.7) + 20 * math.log10(distance_m)


def fit_log_regression(
	distances_m: list[float],
	y_values: list[float],
) -> tuple[float, float] | None:
	if len(distances_m) < 2:
		return None

	x_values = [math.log10(distance_m) for distance_m in distances_m]
	n = len(x_values)
	mean_x = sum(x_values) / n
	mean_y = sum(y_values) / n

	sxx = sum((x - mean_x) ** 2 for x in x_values)
	if sxx == 0:
		return None

	sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_values, y_values))
	slope = sxy / sxx
	intercept = mean_y - slope * mean_x
	return intercept, slope


def regression_log(distance_m: float, intercept: float, slope: float) -> float:
	return intercept + slope * math.log10(distance_m)


def format_regression_expression(name: str, coeffs: tuple[float, float] | None) -> str:
	if coeffs is None:
		return f"{name}: utilstraekkeligt datagrundlag til regression"

	intercept, slope = coeffs
	return f"{name}: RSRP(d) = {intercept:.2f} + {slope:.2f}*log10(d)"


def plot_rsrp(
	distances_m: list[float],
	rsrp_dbm_list: list[float],
	below_coeffs: tuple[float, float] | None,
	above_coeffs: tuple[float, float] | None,
) -> None:
	plt.figure(figsize=(10, 6))
	plt.scatter(distances_m, rsrp_dbm_list, s=16, alpha=0.75, edgecolors="none", label="Målt RSRP")
	fspl_distances = sorted(set(distances_m))
	# Theoretical RSRP = RE_Power - FSPL
	fspl_values_rsrp = [RE_Power - fspl_db(distance_m) for distance_m in fspl_distances]
	plt.plot(fspl_distances, fspl_values_rsrp, color="tab:red", linewidth=2.0, label="Teoretisk RSRP (FSPL)")

	below_distances = sorted({d for d in distances_m if d < REGRESSION_SPLIT_DISTANCE_M})
	above_distances = sorted({d for d in distances_m if d > REGRESSION_SPLIT_DISTANCE_M})

	if below_coeffs is not None and below_distances:
		below_values = [regression_log(d, below_coeffs[0], below_coeffs[1]) for d in below_distances]
		plt.plot(
			below_distances,
			below_values,
			color="tab:green",
			linewidth=2.0,
			label=f"Regression d < {REGRESSION_SPLIT_DISTANCE_M:.0f} m",
		)

	if above_coeffs is not None and above_distances:
		above_values = [regression_log(d, above_coeffs[0], above_coeffs[1]) for d in above_distances]
		plt.plot(
			above_distances,
			above_values,
			color="tab:orange",
			linewidth=2.0,
			label=f"Regression d > {REGRESSION_SPLIT_DISTANCE_M:.0f} m",
		)

	plt.xscale("log")
	# Ensure distance=1 is included on the x-axis
	try:
		max_d = max(distances_m) if distances_m else REGRESSION_SPLIT_DISTANCE_M
	except Exception:
		max_d = REGRESSION_SPLIT_DISTANCE_M
	plt.xlim(1.0, max_d * 1.05)
	plt.grid(True, which="both", linestyle="--", linewidth=0.7, alpha=0.5)
	plt.legend()

	plt.title(f"RSRP ift. afstand (EIRP inkl. gain = {TX_EIRP:.1f} dBm)")
	plt.xlabel("Afstand [m] (log-skala)")
	plt.ylabel("RSRP [dBm]")
	plt.tight_layout()
	plt.show()


def main() -> None:
	parser = argparse.ArgumentParser(
		description="Plot pathloss ift. afstand med filter på SNR og PLMN."
	)
	parser.add_argument(
		"--snr-min",
		type=float,
		default=DEFAULT_SNR_MIN_DB,
		help=f"Minimum SNR i dB (default: {DEFAULT_SNR_MIN_DB})",
	)
	parser.add_argument(
		"--points-log",
		type=Path,
		default=None,
		help="Output .log-fil med filtrerede koordinatpunkter til QGIS.",
	)
	parser.add_argument(
		"--no-regression",
		action="store_true",
		help="Disable regression lines on the plot.",
	)
	args = parser.parse_args()

	script_dir = Path(__file__).resolve().parent
	input_path = script_dir / "gps_rsrp_samlet.log"
	points_log_path = args.points_log or (script_dir / "filtrerede_punkter_qgis.log")

	if not input_path.exists():
		raise FileNotFoundError(f"Filen blev ikke fundet: {input_path}")

	distances_m, rsrp_dbm_list, filtered_points = load_data(
		input_path,
		snr_min_db=args.snr_min,
	)
	save_filtered_points_log(filtered_points, points_log_path)
	print(f"Filtrerede punkter gemt: {len(filtered_points)}")
	print(f"Punkt-log gemt i: {points_log_path.resolve()}")
	if args.no_regression:
		below_coeffs = None
		above_coeffs = None
		print("Regression lines disabled by --no-regression flag.")
	else:
		below_distances = [d for d in distances_m if d < REGRESSION_SPLIT_DISTANCE_M]
		below_rsrp = [p for d, p in zip(distances_m, rsrp_dbm_list) if d < REGRESSION_SPLIT_DISTANCE_M]
		above_distances = [d for d in distances_m if d > REGRESSION_SPLIT_DISTANCE_M]
		above_rsrp = [p for d, p in zip(distances_m, rsrp_dbm_list) if d > REGRESSION_SPLIT_DISTANCE_M]

		below_coeffs = fit_log_regression(below_distances, below_rsrp)
		above_coeffs = fit_log_regression(above_distances, above_rsrp)

		print(format_regression_expression(f"d < {REGRESSION_SPLIT_DISTANCE_M:.0f} m", below_coeffs))
		print(format_regression_expression(f"d > {REGRESSION_SPLIT_DISTANCE_M:.0f} m", above_coeffs))

	plot_rsrp(distances_m, rsrp_dbm_list, below_coeffs, above_coeffs)


if __name__ == "__main__":
	main()
	