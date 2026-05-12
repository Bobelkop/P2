import Rasp

print("Generating graphs with regression...")
graf_stier = Rasp.Lav_Grafer()
print("Graphs generated successfully!")
print(f"  RSRP plot: {graf_stier['rsrp']}")
print(f"  SNR plot: {graf_stier['snr']}")
print(f"  Pathloss plot: {graf_stier['pathloss']}")
