import math
import os
import glob
import re
import csv
import numpy as np
import matplotlib.pyplot as plt
from geopy.distance import geodesic

# === PATHS ===
script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.join(script_dir, "DATA")
uplink_dir = os.path.join(root_dir, "core-uplink")
downlink_dir = os.path.join(root_dir, "raspberrypi-downlink")

rates = ["15.6kbps", "65.5kbps", "250kbps", "1mbps", "4mbps"]

# =========================
# EXTRACT RATE
# =========================
def extract_rate(filename):
    match = re.search(r'_(\d+\.?\d*(?:kbps|mbps))\.test', filename)
    return match.group(1) if match else None

# =========================
# PACKET LOSS
# =========================
def calculate_packet_loss(seqs):
    if not seqs:
        return 100
    expected = max(seqs) - min(seqs) + 1
    return (expected - len(seqs)) / expected * 100

# =========================
# ANALYSE
# =========================
def analyse_test_file(file_path):
    with open(file_path, "r") as f:
        lines = f.readlines()

    delays = []
    timestamps = []
    seqs = []
    total_bytes = 0

    for line in lines[1:]:
        parts = line.strip().split(",")

        if len(parts) >= 4:
            try:
                ts = float(parts[0])
                seq = int(parts[1])
                owd = float(parts[2])
                length = int(parts[3])

                timestamps.append(ts)
                seqs.append(seq)
                delays.append(owd)
                total_bytes += length
            except:
                continue

    if len(timestamps) < 2:
        return None

    duration = (max(timestamps) - min(timestamps)) / 1_000_000
    throughput = (total_bytes * 8) / duration / 1000

    avg_delay = np.mean(delays) / 1000
    packet_loss = calculate_packet_loss(seqs)

    status = "OK"
    reason = ""

    if packet_loss > 5:
        status = "FAIL"
        reason = "PL"
    elif avg_delay > 50:
        status = "FAIL"
        reason = "LAT"

    return {
        "status": status,
        "tp": throughput,
        "lat": avg_delay,
        "packet_loss": packet_loss,
        "reason": reason,
        "delays": delays
    }

# =========================
# LOAD DATA
# =========================
def process_folder(folder):
    table = {}

    files = glob.glob(os.path.join(folder, "**", "*.test"), recursive=True)

    for file_path in files:
        rate = extract_rate(os.path.basename(file_path))
        if rate not in rates:
            continue

        match = re.search(r"test(\d+)", file_path.lower())
        if not match:
            continue

        testnr = int(match.group(1))
        result = analyse_test_file(file_path)

        table.setdefault(testnr, {})[rate] = result

    return table

# =========================
# DISTANCE MAP
# =========================
def hent_afstande():
    afstand_map = {}

    with open(os.path.join(root_dir, "testlist.csv")) as f:
        reader = csv.DictReader(f)

        for row in reader:
            try:
                testnr = int(row["testnr"])

                lat1 = float(row["latitude"])
                lon1 = float(row["longitude"])

                lat2 = float(row["drone_latitude"])
                lon2 = float(row["drone_longitude"])

                height = float(row["height"])

                dist_2d = geodesic((lat1, lon1), (lat2, lon2)).meters
                dist_3d = math.sqrt(dist_2d**2 + height**2)

                afstand_map[testnr] = (round(dist_3d, 1), height)

            except:
                continue

    return afstand_map

# =========================
# LATENCIES PER CONDITION
# =========================
def collect_by_distance_with_direction(uplink, downlink, afstand_map):
    distance_map = {}

    # ===== UPLINK =====
    for testnr, rates_data in uplink.items():
        if testnr not in afstand_map:
            continue

        dist, height = afstand_map[testnr]

        for rate, data in rates_data.items():
            if not data:
                continue

            key = f"{rate} UL ({round(height)}m)"

            lat_ms = [d / 1000 for d in data["delays"]]

            distance_map.setdefault(dist, {})[key] = lat_ms

    # ===== DOWNLINK =====
    for testnr, rates_data in downlink.items():
        if testnr not in afstand_map:
            continue

        dist, height = afstand_map[testnr]

        for rate, data in rates_data.items():
            if not data:
                continue

            key = f"{rate} DL ({round(height)}m)"

            lat_ms = [d / 1000 for d in data["delays"]]

            distance_map.setdefault(dist, {})[key] = lat_ms

    return distance_map
# =========================
# BYTEBLOWER STYLE PLOT
# =========================
import os

# Create a directory to save the graphs
graph_dir = os.path.join(script_dir, "graphs")
os.makedirs(graph_dir, exist_ok=True)

def plot_byteblower_style(latency_map, title, threshold=None):
    fig, ax1 = plt.subplots(figsize=(9, 6))

    for i, (label, latencies) in enumerate(latency_map.items()):
        if i > 10:  # Limit the number of lines
            break

        lat = np.array(latencies)
        lat = lat[lat > 0]

        if len(lat) < 10:
            continue

        lat = np.sort(lat)
        n = len(lat)

        cdf = np.arange(1, n+1) / n
        ccdf = 1 - cdf
        ccdf = np.clip(ccdf, 1e-6, 1)

        ax1.plot(lat, ccdf, label=f"{label} (n={n})")

    ax1.set_xscale("log")
    ax1.set_yscale("log")

    ax1.set_xlabel("Latency (ms)")
    ax1.set_ylabel("CCDF")

    # Percentile lines
    for p in [0, 0.9, 0.99, 0.999]:
        ax1.axhline(1 - p, linestyle="--", alpha=0.4)

    ax1.set_ylim(1e-4, 1)  # Adjust y-axis to ensure P99.99 is at the top

    # Add vertical threshold line if provided
    if threshold is not None:
        ax1.axvline(threshold, color="red", linestyle="-.", linewidth=2, label=f"Threshold = {threshold} ms")

    ax1.grid(True, which="both", linestyle="--", alpha=0.3)

    # Secondary axis
    ax2 = ax1.twinx()
    ax2.set_yscale("log")

    ticks = [1, 0.1, 0.01, 0.001, 0.0001]  # Extend ticks to include 0.0001
    ax1.set_yticks(ticks)
    ax1.set_yticklabels(["1", "0.1", "0.01", "0.001", "0.0001"])  # Use decimal notation for primary y-axis labels

    ax2.set_yticks(ticks)
    ax2.set_yticklabels(["P0", "P90", "P99", "P99.9", "P99.99"])  # Ensure P0 is at the top and match tick count

    ax2.set_ylabel("CDF percentile")

    ax1.set_ylim(1e-4, 1)  # Ensure the y-axis scale matches the full range

    # Explicitly align the secondary y-axis labels with the primary y-axis
    ax2.set_ylim(ax1.get_ylim())

    ax1.legend(fontsize=8)
    plt.title(title)
    plt.tight_layout()

    # Save the plot to the graphs directory
    file_name = title.replace(" ", "_").replace("-", "_") + ".png"
    file_path = os.path.join(graph_dir, file_name)
    plt.savefig(file_path)
    plt.close()

    print(f"Saved graph: {file_path}")

# =========================
# MAIN
# =========================
def main():
    print("Indlæser data...")

    afstand_map = hent_afstande()

    uplink = process_folder(uplink_dir)
    downlink = process_folder(downlink_dir)

    print("Plotter grafer...")

    distance_data = collect_by_distance_with_direction(uplink, downlink, afstand_map)

    threshold = 40  # Set your desired vertical threshold value here (in ms)

    for dist in sorted(distance_data.keys()):
        curves = distance_data[dist]

        title = f"Latency CCDF - {dist:.1f} m"

        plot_byteblower_style(curves, title, threshold)

if __name__ == "__main__":
    main()