"""Recompute only the 14 observed differing energy values; no plant rerun."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "simulation"))
from buck_model import Parameters
from protection import energy_j

p = Parameters()
inputs = json.loads((HERE / "inputs.json").read_text(encoding="utf-8"))
rows = []
for row in inputs:
    i, v = row["current_a"], row["output_v"]
    rows.append({**row, "recomputed_energy_j": energy_j(i, v, p),
                 "current_square_pow": i ** 2, "current_square_multiply": i * i,
                 "voltage_square_pow": v ** 2, "voltage_square_multiply": v * v})
result = {"python": sys.version, "platform": sys.platform, "rows": rows}
(HERE / sys.argv[1]).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"platform": sys.platform, "recomputed_samples": len(rows)}))
