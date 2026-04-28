import Rasp
import time

t = time.time()
res = Rasp.alle_målinger_fra_json(force_reload=True)
elapsed = time.time() - t

print(f"Loaded {len(res)} measurements in {elapsed:.2f} seconds")
print("\nMeasurements:")
for k in sorted(res.keys()):
    print(f"  {k}")
