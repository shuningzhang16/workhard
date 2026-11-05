"""Narrow repair of the cross-runtime artifact audit, without changing a model."""
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
probes = {}
for platform in ("windows", "linux"):
    records = json.loads((HERE / (platform + ".json")).read_text(encoding="utf-8"))["rows"]
    probes[platform] = {(r["case"], r["sample"]): r for r in records}
cases = []
for case in ("startup", "load_step", "overvoltage"):
    paths = [ROOT / f"simulation/io_timing_results/{case}_delayed_quantized_control_samples.csv",
             ROOT / f"host_c/closed_loop_results/{case}_python_control_samples.csv"]
    data = []
    for path in paths:
        with path.open(newline="", encoding="utf-8") as stream:
            data.append(list(csv.DictReader(stream)))
    assert len(data[0]) == len(data[1])
    changed = []
    for k, (old, new) in enumerate(zip(*data)):
        assert all(old[key] == new[key] for key in old if key != "stored_energy_j")
        if old["stored_energy_j"] != new["stored_energy_j"]:
            a, b = probes["windows"][case, k], probes["linux"][case, k]
            assert a["recomputed_energy_j"] == float(old["stored_energy_j"])
            assert b["recomputed_energy_j"] == float(new["stored_energy_j"])
            assert a["current_a"] == b["current_a"] and a["output_v"] == b["output_v"]
            assert a["voltage_square_pow"] != b["voltage_square_pow"]
            assert a["voltage_square_multiply"] == b["voltage_square_multiply"]
            changed.append(abs(float(new["stored_energy_j"]) - float(old["stored_energy_j"])))
    cases.append({"case": case, "samples": len(data[0]), "all_other_fields_exact": True,
                  "energy_difference_samples": len(changed), "max_abs_energy_difference_j": max(changed, default=0)})
summary = {"cases": cases, "diagnosis": "Only derived energy differs: native Python pow(v,2) reproduced each saved value in its originating runtime; plant, ADC, commands and states are identical.",
           "repair": "replace overbroad cross-runtime text-equality claim with exact trajectory comparison and explicit native recomputation of every differing derived energy value",
           "changed_model_or_acceptance_thresholds": False, "simulation_rerun": False}
(HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary))
