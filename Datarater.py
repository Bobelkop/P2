import os
import glob
import re
import csv
import numpy as np
from geopy.distance import geodesic

# === PATHS ===
root_dir = os.path.join(os.getcwd(), "DATA")
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
# METRICS
# =========================
def calculate_packet_loss(seqs):
    if not seqs:
        return 100
    expected = max(seqs) - min(seqs) + 1
    return (expected - len(seqs)) / expected * 100


def calculate_throughput(lines):
    timestamps = []
    total_bytes = 0

    for line in lines[1:]:
        parts = line.strip().split(",")
        if len(parts) >= 4:
            ts = float(parts[0])
            length = int(parts[3])

            timestamps.append(ts)
            total_bytes += length

    if len(timestamps) < 2:
        return 0

    duration = (max(timestamps) - min(timestamps)) / 1_000_000  # µs → sek

    if duration <= 0:
        return 0

    # ✅ Kbps direkte
    throughput_kbps = (total_bytes * 8) / duration / 1000

    return throughput_kbps

# =========================
# ANALYSE
# =========================

def analyse_test_file(file_path):
    with open(file_path, "r") as f:
        lines = f.readlines()

    delays = []
    timestamps = []
    total_bytes = 0

    for line in lines[1:]:
        parts = line.strip().split(",")
        if len(parts) >= 4:
            try:
                ts = float(parts[0])
                owd = float(parts[2])
                length = int(parts[3])

                timestamps.append(ts)
                delays.append(owd)
                total_bytes += length
            except:
                continue

    if len(timestamps) < 2:
        return None

    # ✅ throughput (Kbps)
    duration = (max(timestamps) - min(timestamps)) / 1_000_000
    throughput = (total_bytes * 8) / duration / 1000  # Kbps

    # ✅ latency og jitter
    avg_delay = np.mean(delays) / 1000  # µs → ms
    jitter = np.std(delays) / 1000

    # ✅ status (meget simpelt)
    status = "OK"
    reason = ""

    if jitter > 20:
        status = "FAIL"
        reason = "JIT"
    elif avg_delay > 50:
        status = "FAIL"
        reason = "LAT"

    return {
        "status": status,
        "tp": throughput,
        "lat": avg_delay,
        "jit": jitter,
        "reason": reason
    }


# =========================
# CSV → AFSTAND + HEIGHT
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

                dist = round(geodesic((lat1, lon1), (lat2, lon2)).meters, 1)

                afstand_map[testnr] = (dist, height)

            except:
                continue

    return afstand_map


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
# SPLIT HEIGHT
# =========================
def split_by_height(table, afstand_map):
    t15, t120 = {}, {}

    for testnr, values in table.items():
        if testnr not in afstand_map:
            continue

        dist, height = afstand_map[testnr]

        if abs(height - 15) < 2:
            t15[dist] = values
        else:
            t120[dist] = values

    return t15, t120


# =========================
# FORMAT CELL (rent output!)
# =========================
def format_cell(data):
    if not data:
        return "-"

    status = data["status"]
    tp = data["tp"]     # Kbps
    lat = data["lat"]
    jit = data["jit"]

    # ✅ throughput format
    if tp >= 1000:
        speed = f"{tp/1000:.1f}M"
    else:
        speed = f"{tp:.0f}K"

    # ✅ vælg symbol
    symbol = "✅" if status == "OK" else "❌"

    # ✅ ALTID vis data
    return f"{symbol} {speed} ({lat:.0f}/{jit:.0f})"
# =========================
# PRINT TABLE
# =========================
def print_table(title, table):
    print(f"\n=== {title} ===")

    col_width = 12

    header = "Afstand".ljust(10) + "|"
    for r in rates:
        header += r.center(col_width) + "|"

    print(header)
    print("-" * len(header))

    for d in sorted(table.keys()):
        row = str(d).ljust(10) + "|"

        for r in rates:
            value = table[d].get(r)
            cell = format_cell(value)
            row += cell.center(col_width) + "|"

        print(row)

def print_legend():
    print("\n=== Forklaring ===")
    print("Format: ✅ Throughput (Latency / Jitter)")
    print("")
    print("Throughput:")
    print("  K = Kbps (kilobit per sekund)")
    print("  M = Mbps (megabit per sekund)")
    print("")
    print("Latency:")
    print("  Gennemsnitlig forsinkelse i ms (lavere er bedre)")
    print("")
    print("Jitter:")
    print("  Variation i latency i ms (lavere er bedre)")
    print("")
    print("Symboler:")
    print("  ✅ = Acceptabel performance")
    print("  ❌ = Problem (typisk høj jitter eller latency)\n")


# =========================
# RUN
# =========================

afstand_map = hent_afstande()

uplink = process_folder(uplink_dir)
downlink = process_folder(downlink_dir)

u15, u120 = split_by_height(uplink, afstand_map)
d15, d120 = split_by_height(downlink, afstand_map)
print_legend()
print_table("Downlink (15m)", d15)
print_table("Downlink (120m)", d120)
print_table("Uplink (15m)", u15)
print_table("Uplink (120m)", u120)



with open("netvaerk_analyse.txt", "w", encoding="utf-8") as f:
    f.write("=== Forklaring ===\n")
    f.write("Format: ✅ Throughput (Latency / Jitter)\n\n")
    f.write("Latency og jitter er i millisekunder (ms)\n\n")

    # skriv din tabel til fil
    def capture_print(line):
        f.write(line + "\n")

    # midlertidigt redirect print
    import builtins
    original_print = print

    def file_print(*args, **kwargs):
        line = " ".join(str(a) for a in args)
        original_print(*args, **kwargs)
        f.write(line + "\n")

    print = file_print

    print_table("Downlink (15m)", d15)
    print_table("Downlink (120m)", d120)
    print_table("Uplink (15m)", u15)
    print_table("Uplink (120m)", u120)

    print = original_print
