from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path
import os

from geopy.distance import geodesic
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score, mean_squared_error

from scipy.signal import find_peaks


def parse_gpgga_line(line: str):
	"""Parse GPGGA line and return (hhmmss, lat, lon) or None."""
	if "$GPGGA" not in line:
		return None

	body = line.strip().split("$GPGGA,")[-1]
	parts = body.split(",")
	if len(parts) < 5:
		return None

	time_raw = parts[0].strip()
	lat_raw = parts[1].strip()
	lat_dir = parts[2].strip()
	lon_raw = parts[3].strip()
	lon_dir = parts[4].strip()

	if len(time_raw) < 6 or not lat_raw or not lon_raw:
		return None

	hhmmss = time_raw.split(".")[0][:6]

	try:
		lat = float(lat_raw[:2]) + float(lat_raw[2:]) / 60.0
		if lat_dir.upper() == "S":
			lat = -lat

		lon = float(lon_raw[:3]) + float(lon_raw[3:]) / 60.0
		if lon_dir.upper() == "W":
			lon = -lon
	except Exception:
		return None

	return hhmmss, lat, lon


def load_first_point_per_timestamp(path: Path) -> dict[str, tuple[float, float]]:
	"""Load GPS points keyed by HHMMSS; keep first point for each timestamp."""
	points: dict[str, tuple[float, float]] = {}
	with path.open("r", encoding="utf-8", errors="ignore") as f:
		for line in f:
			parsed = parse_gpgga_line(line)
			if not parsed:
				continue
			ts, lat, lon = parsed
			if ts not in points:
				points[ts] = (lat, lon)
	return points


def build_distance_by_timestamp(thy_log_path: Path, teltonika_log_path: Path) -> dict[str, float]:
	"""Build HHMMSS -> distance_m from matched thy/teltonika GPS points."""
	thy_points = load_first_point_per_timestamp(thy_log_path)
	tel_points = load_first_point_per_timestamp(teltonika_log_path)

	common_timestamps = sorted(set(thy_points.keys()) & set(tel_points.keys()))
	distance_by_ts: dict[str, float] = {}
	for ts in common_timestamps:
		thy_lat, thy_lon = thy_points[ts]
		tel_lat, tel_lon = tel_points[ts]
		distance_by_ts[ts] = float(geodesic((thy_lat, thy_lon), (tel_lat, tel_lon)).meters)

	return distance_by_ts


def parse_rsrp_dbm(value) -> float | None:
	if value is None:
		return None
	s = str(value).replace("dBm", "").replace("dB", "").replace(",", ".").strip()
	m = re.search(r"[-+]?[0-9]*\.?[0-9]+", s)
	if not m:
		return None
	try:
		return float(m.group(0))
	except Exception:
		return None


def hhmmss_from_iso_timestamp(ts: str) -> str | None:
	try:
		dt = datetime.fromisoformat(ts)
		return dt.strftime("%H%M%S")
	except Exception:
		return None


def load_rsrp_by_timestamp(radio_log_path: Path) -> dict[str, float]:
	"""Load first RSRP value per HHMMSS from JSON radio log."""
	rsrp_by_ts: dict[str, float] = {}
	with radio_log_path.open("r", encoding="utf-8", errors="ignore") as f:
		for line in f:
			line = line.strip()
			if not line.startswith("{"):
				continue
			try:
				obj = json.loads(line)
			except Exception:
				continue

			timestamp = obj.get("timestamp")
			rsrp_val = parse_rsrp_dbm(obj.get("rsrp"))
			if not timestamp or rsrp_val is None:
				continue

			hhmmss = hhmmss_from_iso_timestamp(timestamp)
			if not hhmmss:
				continue

			if hhmmss not in rsrp_by_ts:
				rsrp_by_ts[hhmmss] = rsrp_val

	return rsrp_by_ts


def hhmmss_to_seconds(hhmmss: str) -> int | None:
	if len(hhmmss) != 6 or not hhmmss.isdigit():
		return None
	hh = int(hhmmss[0:2])
	mm = int(hhmmss[2:4])
	ss = int(hhmmss[4:6])
	return hh * 3600 + mm * 60 + ss


def seconds_to_hhmmss(sec: int) -> str:
	sec = sec % 86400
	hh = sec // 3600
	mm = (sec % 3600) // 60
	ss = sec % 60
	return f"{hh:02d}{mm:02d}{ss:02d}"


def shift_hhmmss(hhmmss: str, offset_hours: int) -> str | None:
	sec = hhmmss_to_seconds(hhmmss)
	if sec is None:
		return None
	return seconds_to_hhmmss(sec + offset_hours * 3600)


def estimate_best_hour_offset(base_timestamps: set[str], candidate_timestamps: set[str]) -> int:
	best_offset = 0
	best_overlap = -1
	for h in range(-12, 13):
		overlap = 0
		for ts in candidate_timestamps:
			shifted = shift_hhmmss(ts, h)
			if shifted in base_timestamps:
				overlap += 1
		if overlap > best_overlap:
			best_overlap = overlap
			best_offset = h
	return best_offset


def calculate_regression(x, y):
	"""Perform linear regression on x and y."""
	if len(x) < 2:
		raise ValueError("Not enough data points for regression.")

	# Perform linear regression
	x = np.array(x).reshape(-1, 1)
	y = np.array(y)
	model = LinearRegression()
	model.fit(x, y)

	slope = model.coef_[0]
	intercept = model.intercept_
	r2 = model.score(x, y)

	return slope, intercept, r2


def calculate_path_loss_exponent(beta):
    """Calculate path-loss exponent from regression slope."""
    return -beta / 10


def calculate_rmse(y_true, y_pred):
    """Calculate RMSE for regression residuals."""
    return np.sqrt(mean_squared_error(y_true, y_pred))


def analyze_regression_results(x_segment, y_segment, slope, intercept):
    """Analyze regression results to calculate path-loss exponent and RMSE."""
    if len(x_segment) < 5:
        return None, None

    # Predicted values
    y_pred = slope * np.log10(x_segment) + intercept

    # Path-loss exponent
    path_loss_exponent = calculate_path_loss_exponent(slope)

    # RMSE
    rmse = calculate_rmse(y_segment, y_pred)

    return path_loss_exponent, rmse


def calculate_dynamic_breakpoint(x_dist, y_rsrp, window_size=15, sensitivity=0.1):
    """
    Estimate breakpoint using gradient of moving-averaged RSRP.
    Sensitivity adjusts the threshold for detecting significant drops.
    """
    if len(x_dist) < window_size + 5:
        return None

    # Sort by distance (important for gradient calculation)
    x = np.array(x_dist)
    y = np.array(y_rsrp)
    idx = np.argsort(x)
    x = x[idx]
    y = y[idx]

    # Moving average
    y_ma = np.convolve(y, np.ones(window_size) / window_size, mode="valid")
    x_ma = x[:len(y_ma)]

    # Gradient (RSRP fall rate)
    gradient = np.gradient(y_ma)

    # Find the largest negative slope exceeding sensitivity threshold
    significant_drops = np.where(gradient < -sensitivity)[0]
    if len(significant_drops) == 0:
        return None

    bp_idx = significant_drops[np.argmin(gradient[significant_drops])]
    return float(x_ma[bp_idx])


def calculate_moving_average(data, window_size):
    """Calculate moving average for a given data set and window size."""
    return np.convolve(data, np.ones(window_size) / window_size, mode='valid')

def has_sufficient_variation(data, threshold=1e-3):
    """Check if data has sufficient variation to perform meaningful regression."""
    return np.ptp(data) > threshold  # ptp: peak-to-peak (max - min)

def find_best_regression_breakpoint(x_dist, y_rsrp, min_points=30):
    """
    Finds breakpoint that maximizes combined R² of two log-distance regressions
    """
    x = np.array(x_dist)
    y = np.array(y_rsrp)

    candidate_distances = np.percentile(x, np.linspace(15, 85, 50))

    best_bp = None
    best_score = -np.inf

    for bp in candidate_distances:
        mask_before = x <= bp
        mask_after = x > bp

        if mask_before.sum() < min_points or mask_after.sum() < min_points:
            continue

        _, _, r2_before = calculate_regression(x[mask_before], y[mask_before])
        _, _, r2_after = calculate_regression(x[mask_after], y[mask_after])

        score = r2_before + r2_after

        if score > best_score:
            best_score = score
            best_bp = bp

    return best_bp


def plot_regression_segment(x_segment, y_segment, label_prefix, color):
    """
    Helper function to perform linear regression and plot a segment.
    """
    if len(x_segment) < 2 or not has_sufficient_variation(x_segment):
        print(f"Not enough data points or variation for {label_prefix} regression.")
        return None, None, None

    # Perform linear regression
    slope, intercept, r2 = calculate_regression(x_segment, y_segment)
    x_fit = np.linspace(min(x_segment), max(x_segment), 100)
    y_fit = slope * x_fit + intercept

    plt.plot(x_fit, y_fit, color=color, label=f"{label_prefix} (R²={r2:.2f})")
    return slope, intercept, r2


def create_rsrp_distance_plot(
    thy_log_path: Path,
    teltonika_log_path: Path,
    radio_log_path: Path,
    out_plot_path: Path,
    results_output_path: Path,
) -> int:
	"""Match timestamped distance and RSRP, then create RSRP vs distance plot."""
	distance_by_ts = build_distance_by_timestamp(thy_log_path, teltonika_log_path)
	rsrp_by_ts = load_rsrp_by_timestamp(radio_log_path)

	# Auto-align radio clock to GPS clock using integer-hour offset.
	best_hour_offset = estimate_best_hour_offset(set(distance_by_ts.keys()), set(rsrp_by_ts.keys()))
	shifted_rsrp_by_ts: dict[str, float] = {}
	for ts, v in rsrp_by_ts.items():
		shifted = shift_hhmmss(ts, best_hour_offset)
		if shifted and shifted not in shifted_rsrp_by_ts:
			shifted_rsrp_by_ts[shifted] = v

	common_timestamps = sorted(set(distance_by_ts.keys()) & set(shifted_rsrp_by_ts.keys()))
	if not common_timestamps:
		raise RuntimeError("Ingen fælles timestamps mellem afstand og radio RSRP")

	x_dist = [distance_by_ts[ts] for ts in common_timestamps]
	y_rsrp = [shifted_rsrp_by_ts[ts] for ts in common_timestamps]

	# Sort data by x_dist to ensure consistency
	sorted_indices = np.argsort(x_dist)
	x_dist = np.array(x_dist)[sorted_indices]
	y_rsrp = np.array(y_rsrp)[sorted_indices]

	# Calculate dynamic breakpoint
	breakpoint_distance = calculate_dynamic_breakpoint(x_dist, y_rsrp, window_size=15, sensitivity=0.1)
	if breakpoint_distance is None:
		raise RuntimeError("Ikke nok data til at beregne et dynamisk breakpoint.")

	# Add additional breakpoint at 2PI (approximately 6.28 meters)
	pi_breakpoint_distance = 2 * np.pi

	# Split data into segments: before and after the breakpoints
	x_dist_before = [d for d in x_dist if d <= breakpoint_distance]
	y_rsrp_before = [y for d, y in zip(x_dist, y_rsrp) if d <= breakpoint_distance]

	x_dist_after = [d for d in x_dist if d > breakpoint_distance]
	y_rsrp_after = [y for d, y in zip(x_dist, y_rsrp) if d > breakpoint_distance]

	x_dist_pi = [d for d in x_dist if d <= pi_breakpoint_distance]
	y_rsrp_pi = [y for d, y in zip(x_dist, y_rsrp) if d <= pi_breakpoint_distance]

	x_dist_after_pi = [d for d in x_dist if d > pi_breakpoint_distance]
	y_rsrp_after_pi = [y for d, y in zip(x_dist, y_rsrp) if d > pi_breakpoint_distance]

	# Debugging output for data segments
	print(f"Dynamisk breakpoint: {breakpoint_distance} m")
	print(f"2PI breakpoint: {pi_breakpoint_distance} m")
	print(f"Antal punkter før dynamisk breakpoint ({breakpoint_distance} m): {len(x_dist_before)}")
	print(f"Antal punkter efter dynamisk breakpoint ({breakpoint_distance} m): {len(x_dist_after)}")
	print(f"Antal punkter før 2PI breakpoint ({pi_breakpoint_distance} m): {len(x_dist_pi)}")
	print(f"Antal punkter efter 2PI breakpoint ({pi_breakpoint_distance} m): {len(x_dist_after_pi)}")

	# Perform regression and plot segments
	slope_before, intercept_before, r2_before = plot_regression_segment(x_dist_before, y_rsrp_before, f"Regression d ≤ {breakpoint_distance:.1f} m", "green")
	slope_after, intercept_after, r2_after = plot_regression_segment(x_dist_after, y_rsrp_after, f"Regression d > {breakpoint_distance:.1f} m", "orange")
	slope_pi, intercept_pi, r2_pi = plot_regression_segment(x_dist_pi, y_rsrp_pi, f"Regression d ≤ 2PI ({pi_breakpoint_distance:.1f} m)", "purple")
	slope_after_pi, intercept_after_pi, r2_after_pi = plot_regression_segment(x_dist_after_pi, y_rsrp_after_pi, f"Regression d > 2PI ({pi_breakpoint_distance:.1f} m)", "brown")

	# Analyze regression results (handle None)
	def safe_analyze(x, y, slope, intercept):
		if slope is None or intercept is None or len(x) < 2:
			return None, None
		return analyze_regression_results(x, y, slope, intercept)

	n_before, rmse_before = safe_analyze(x_dist_before, y_rsrp_before, slope_before, intercept_before)
	n_after, rmse_after = safe_analyze(x_dist_after, y_rsrp_after, slope_after, intercept_after)
	n_pi, rmse_pi = safe_analyze(x_dist_pi, y_rsrp_pi, slope_pi, intercept_pi)
	n_after_pi, rmse_after_pi = safe_analyze(x_dist_after_pi, y_rsrp_after_pi, slope_after_pi, intercept_after_pi)

	# Save results to CSV
	results = {
		"breakpoint_distance": breakpoint_distance,
		"2PI_breakpoint_distance": pi_breakpoint_distance,
		"n_before": n_before,
		"n_after": n_after,
		"n_pi": n_pi,
		"n_after_pi": n_after_pi,
		"r2_before": r2_before,
		"r2_after": r2_after,
		"r2_pi": r2_pi,
		"r2_after_pi": r2_after_pi,
		"rmse_before": rmse_before,
		"rmse_after": rmse_after,
		"rmse_pi": rmse_pi,
		"rmse_after_pi": rmse_after_pi,
	}

	with open(results_output_path, "w", newline="", encoding="utf-8") as csvfile:
		writer = csv.DictWriter(csvfile, fieldnames=results.keys())
		writer.writeheader()
		writer.writerow(results)

	return len(common_timestamps)


def compute_matched_distances_only(
	thy_log_path: Path,
	teltonika_log_path: Path,
	out_csv_path: Path,
) -> int:
	"""Match identical GPGGA timestamps and write only distance_m column to CSV."""
	thy_points = load_first_point_per_timestamp(thy_log_path)
	tel_points = load_first_point_per_timestamp(teltonika_log_path)

	common_timestamps = sorted(set(thy_points.keys()) & set(tel_points.keys()))

	out_csv_path.parent.mkdir(parents=True, exist_ok=True)
	with out_csv_path.open("w", encoding="utf-8", newline="") as f:
		writer = csv.writer(f)
		writer.writerow(["distance_m"])
		for ts in common_timestamps:
			thy_lat, thy_lon = thy_points[ts]
			tel_lat, tel_lon = tel_points[ts]
			distance_m = float(geodesic((thy_lat, thy_lon), (tel_lat, tel_lon)).meters)
			writer.writerow([f"{distance_m:.3f}"])

	return len(common_timestamps)


def find_default_logs(meas_root: Path, site: str) -> tuple[Path, Path]:
	"""Find site-specific thy.log and teltonika-gps.log automatically."""
	thy_log = meas_root / "pc_thy" / f"{site}.log"
	if not thy_log.exists():
		raise FileNotFoundError(f"Kunne ikke finde thy-log: {thy_log}")

	tel_candidates = sorted((meas_root / "pi_thy" / site).glob("*-teltonika-gps.log"))
	if not tel_candidates:
		raise FileNotFoundError(f"Kunne ikke finde teltonika-gps.log i pi_thy/{site}")

	return thy_log, tel_candidates[0]


def find_default_radio_log(meas_root: Path, site: str) -> Path:
	radio_candidates = sorted((meas_root / "pi_thy" / site).glob("*-radio.log"))
	if not radio_candidates:
		raise FileNotFoundError(f"Kunne ikke finde radio.log i pi_thy/{site}")
	return radio_candidates[0]


def find_file_with_suffix(directory, suffix):
    """Find a file in a directory that ends with a given suffix."""
    directory = Path(directory)  # Ensure directory is a Path object
    for filename in os.listdir(directory):
        if filename.endswith(suffix):
            return directory / filename
    raise FileNotFoundError(f"No file with suffix '{suffix}' found in {directory}")


def process_all_sites(sites, thy_log_dir, teltonika_log_dir, radio_log_dir, output_dir):
    """Process all sites and generate plots and results."""
    thy_log_dir = Path(thy_log_dir)  # Ensure directories are Path objects
    teltonika_log_dir = Path(teltonika_log_dir)
    radio_log_dir = Path(radio_log_dir)
    output_dir = Path(output_dir)

    for site in sites:
        try:
            thy_log_path = thy_log_dir / "pc_thy" / f"{site}.log"
            pi_thy_dir = teltonika_log_dir / "pi_thy" / site

            teltonika_log_path = find_file_with_suffix(pi_thy_dir, "-teltonika-gps.log")
            radio_log_path = find_file_with_suffix(pi_thy_dir, "-radio.log")
            out_plot_path = output_dir / f"{site}_rsrp_distance_plot.png"
            results_output_path = output_dir / f"{site}_results.csv"

            print(f"Attempting to save plot to: {out_plot_path}")
            try:
                plt.savefig(out_plot_path)
                print(f"Plot successfully saved to: {out_plot_path}")
            except Exception as e:
                print(f"Failed to save plot to {out_plot_path}: {e}")

            create_rsrp_distance_plot(
                thy_log_path,
                teltonika_log_path,
                radio_log_path,
                out_plot_path,
                results_output_path,
            )
        except Exception as e:
            print(f"Error processing site {site}: {e}")


def main():
	parser = argparse.ArgumentParser(
		description="Match thy logs and generate RSRP vs distance plots for multiple sites."
	)
	parser.add_argument(
		"--meas-root",
		type=Path,
		default=Path(__file__).resolve().parent / "DATA" / "meas_thy",
		help="Root mappe for målinger",
	)
	parser.add_argument(
		"--sites",
		type=str,
		nargs="+",
		default=["thy_1", "thy_2", "thy_3"],
		help="Liste over sites/målinger (e.g. thy_1 thy_2 thy_3)",
	)
	args = parser.parse_args()

	process_all_sites(args.sites, args.meas_root, args.meas_root, args.meas_root, args.meas_root)

if __name__ == "__main__":
	main()
