from __future__ import annotations

import argparse
import csv
import json
import math
import re
from bisect import bisect_left
from datetime import datetime
from pathlib import Path


GPS_LINE_PATTERN = re.compile(
	r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\s*"
	r"LAT:\s*(?P<lat>-?\d+(?:\.\d+)?),\s*"
	r"LON:\s*(?P<lon>-?\d+(?:\.\d+)?),\s*"
	r"ALT:\s*(?P<alt>-?\d+(?:\.\d+)?)$"
)

REFERENCE_LAT = 57.013896
REFERENCE_LON = 9.987568


def parse_gps_log(gps_path: Path) -> list[dict]:
	points = []
	with gps_path.open("r", encoding="utf-8") as f:
		for line_number, raw_line in enumerate(f, start=1):
			line = raw_line.strip()
			if not line:
				continue

			match = GPS_LINE_PATTERN.match(line)
			if not match:
				continue

			ts = datetime.strptime(match.group("timestamp"), "%Y-%m-%d %H:%M:%S")
			points.append(
				{
					"timestamp": ts,
					"lat": float(match.group("lat")),
					"lon": float(match.group("lon")),
					"alt": float(match.group("alt")),
					"line": line_number,
				}
			)

	points.sort(key=lambda p: p["timestamp"])
	return points


def parse_rsrp_value(rsrp_text: str | None) -> float | None:
	if not rsrp_text:
		return None

	cleaned = rsrp_text.replace("dBm", "").strip().replace(",", ".")
	try:
		return float(cleaned)
	except ValueError:
		return None


def find_nearest_gps(radio_ts: datetime, gps_points: list[dict]) -> dict | None:
	if not gps_points:
		return None

	gps_timestamps = [p["timestamp"] for p in gps_points]
	idx = bisect_left(gps_timestamps, radio_ts)

	candidates = []
	if idx < len(gps_points):
		candidates.append(gps_points[idx])
	if idx > 0:
		candidates.append(gps_points[idx - 1])

	if not candidates:
		return None

	return min(candidates, key=lambda p: abs((p["timestamp"] - radio_ts).total_seconds()))


def distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
	# Haversine formula for distance between two WGS84 coordinates.
	earth_radius_m = 6371000.0

	phi1 = math.radians(lat1)
	phi2 = math.radians(lat2)
	dphi = math.radians(lat2 - lat1)
	dlambda = math.radians(lon2 - lon1)

	a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
	c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
	return earth_radius_m * c


def merge_logs(gps_path: Path, radio_path: Path, output_path: Path) -> tuple[int, int]:
	gps_points = parse_gps_log(gps_path)
	if not gps_points:
		raise ValueError(f"Ingen gyldige GPS-linjer fundet i: {gps_path}")

	matched_count = 0
	total_radio_rows = 0

	with radio_path.open("r", encoding="utf-8") as rf, output_path.open(
		"w", encoding="utf-8", newline=""
	) as wf:
		writer = csv.writer(wf)
		writer.writerow(
			["timestamp", "rsrp_dbm", "snr", "plmn", "latitude", "longitude", "distance_m"]
		)

		for line_number, raw_line in enumerate(rf, start=1):
			line = raw_line.strip()
			if not line:
				continue

			total_radio_rows += 1
			try:
				row = json.loads(line)
			except json.JSONDecodeError:
				continue

			ts_text = row.get("timestamp")
			if not ts_text:
				continue

			try:
				radio_ts = datetime.fromisoformat(ts_text)
			except ValueError:
				continue

			nearest = find_nearest_gps(radio_ts, gps_points)
			if nearest is None:
				continue

			rsrp = parse_rsrp_value(row.get("rsrp"))
			snr = (row.get("snr") or "").strip()
			plmn = (row.get("plmn") or "").strip()
			distance = distance_meters(
				nearest["lat"],
				nearest["lon"],
				REFERENCE_LAT,
				REFERENCE_LON,
			)
			writer.writerow(
				[
					radio_ts.isoformat(),
					"" if rsrp is None else f"{rsrp:.1f}",
					snr,
					plmn,
					f"{nearest['lat']:.8f}",
					f"{nearest['lon']:.8f}",
					f"{distance:.2f}",
				]
			)
			matched_count += 1

	return total_radio_rows, matched_count


def default_paths(base_dir: Path) -> tuple[Path, Path, Path]:
	data_dir = base_dir / "Original data fra målinger 20-04-2026"
	gps_path = data_dir / "2026-04-20 14_35_50 gps_log.txt"
	radio_path = data_dir / "radio.log"
	output_path = base_dir / "gps_rsrp_samlet.log"
	return gps_path, radio_path, output_path


def build_arg_parser(base_dir: Path) -> argparse.ArgumentParser:
	gps_default, radio_default, output_default = default_paths(base_dir)
	parser = argparse.ArgumentParser(
		description="Sammensaet GPS-position med RSRP ud fra timestamp."
	)
	parser.add_argument(
		"--gps",
		type=Path,
		default=gps_default,
		help=f"Sti til GPS-log (default: {gps_default})",
	)
	parser.add_argument(
		"--radio",
		type=Path,
		default=radio_default,
		help=f"Sti til radio.log (default: {radio_default})",
	)
	parser.add_argument(
		"--output",
		type=Path,
		default=output_default,
		help=f"Output CSV-fil (default: {output_default})",
	)
	return parser


def main() -> None:
	base_dir = Path(__file__).resolve().parent
	parser = build_arg_parser(base_dir)
	args = parser.parse_args()

	gps_path = args.gps.resolve()
	radio_path = args.radio.resolve()
	output_path = args.output.resolve()

	if not gps_path.exists():
		raise FileNotFoundError(f"GPS-fil findes ikke: {gps_path}")
	if not radio_path.exists():
		raise FileNotFoundError(f"radio.log findes ikke: {radio_path}")

	output_path.parent.mkdir(parents=True, exist_ok=True)
	total_rows, matched_rows = merge_logs(gps_path, radio_path, output_path)

	print(f"Flettet radio-rows: {matched_rows}/{total_rows}")
	print(f"Output gemt i: {output_path}")


if __name__ == "__main__":
	main()
