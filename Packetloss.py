import os
import matplotlib.pyplot as plt

from Datarater import lav_tabeller, rates


# =========================
# CONVERT % → PPM
# =========================
def percent_to_ppm(pl):
    return pl * 10000  # 0.01% = 100 ppm


# =========================
# FARVE BASERET PÅ KVALITET
# =========================
def get_color(pl):
    if pl < 0.01:
        return "green"   # rigtig godt
    elif pl < 0.1:
        return "orange"  # lidt issues
    else:
        return "red"     # problem


# =========================
# PLOT FUNCTION (IMPROVED)
# =========================
def plot_packet_loss(title, table, output_dir):
    plt.figure()

    for rate in rates:
        x = []
        y = []
        colors = []

        for dist in sorted(table.keys()):
            data = table[dist].get(rate)

            if data and data["packet_loss"] is not None:
                pl = data["packet_loss"]

                # skip helt nul hvis du vil (kan kommenteres ud)
                if pl == 0:
                    continue

                x.append(dist)
                y.append(percent_to_ppm(pl))
                colors.append(get_color(pl))

        if x:
            # 🔹 linje (trend)
            plt.plot(x, y, alpha=0.4)

            # 🔹 punkter (vigtig!)
            plt.scatter(x, y, c=colors, label=rate, s=60)

    plt.xlabel("Afstand (m)")
    plt.ylabel("Packet loss (ppm)")
    plt.title(title)

    plt.grid(True)
    plt.legend()

    # lineær akse nu (meget bedre med ppm)
    plt.ylim(bottom=0)

    plt.tight_layout()

    filename = title.lower()\
        .replace(" ", "_")\
        .replace("(", "")\
        .replace(")", "") + ".png"

    filepath = os.path.join(output_dir, filename)

    plt.savefig(filepath, dpi=300)
    plt.close()

    print(f"Saved: {filepath}")


# =========================
# MAIN
# =========================
def main():
    tables = lav_tabeller()

    script_dir = os.path.dirname(os.path.abspath(__file__))

    output_dir = os.path.join(script_dir, "packetloss_grafer")
    os.makedirs(output_dir, exist_ok=True)

    plot_packet_loss("Downlink (15m)", tables["downlink_15"], output_dir)
    plot_packet_loss("Downlink (120m)", tables["downlink_120"], output_dir)
    plot_packet_loss("Uplink (15m)", tables["uplink_15"], output_dir)
    plot_packet_loss("Uplink (120m)", tables["uplink_120"], output_dir)

    print("\n✅ Forbedrede packetloss grafer gemt i 'packetloss_grafer'")


if __name__ == "__main__":
    main()
