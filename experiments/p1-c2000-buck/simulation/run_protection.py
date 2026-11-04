"""导出保护的正常回归、三个物理扰动工况和状态转换证据。"""

import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path

from protection import ProtectionLimits, simulate_protected


def write_csv(path, rows, columns=None):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    output = Path(__file__).resolve().parent / "protection_results"
    output.mkdir(exist_ok=True)
    summaries = []
    parameters = {}
    for case in ("startup", "load_step", "input_step", "overcurrent", "overvoltage", "undervoltage"):
        p, rows, events = simulate_protected(case)
        parameters[case] = asdict(p)
        write_csv(output / f"{case}.csv", rows)
        write_csv(output / f"{case}_events.csv", events,
                  ["time_s", "from_state", "to_state", "reason", "latched_fault"])
        trips = [e for e in events if e["reason"] == "trip"]
        clears = [r for r in rows if r["clear_result"] == "accepted"]
        tail = [r["output_v"] for r in rows if r["time_s"] >= p.duration_s - 0.010]
        settled_after_clear_s = None
        if clears:
            after = [r for r in rows if r["time_s"] >= clears[0]["time_s"]]
            outside = [i for i, r in enumerate(after) if abs(r["output_v"] - p.target_v) > 0.02 * p.target_v]
            entry = outside[-1] + 1 if outside else 0
            if entry < len(after) and after[-1]["time_s"] - after[entry]["time_s"] >= 0.002:
                settled_after_clear_s = after[entry]["time_s"] - clears[0]["time_s"]
        fault_rows = [r for r in rows if r["state"] == "FAULT_LATCHED"]
        summary = {
            "case": case, "trip_count": len(trips),
            "first_fault": trips[0]["latched_fault"] if trips else "",
            "first_trip_time_s": trips[0]["time_s"] if trips else None,
            "rejected_active_clear_count": sum(r["clear_result"] == "rejected_active_fault" for r in rows),
            "accepted_clear_time_s": clears[0]["time_s"] if clears else None,
            "recovery_from_clear_to_2_percent_s": settled_after_clear_s,
            "final_10ms_mean_error_v": sum(tail) / len(tail) - p.target_v,
            "minimum_current_a": min(r["inductor_current_a"] for r in rows),
            "minimum_output_v": min(r["output_v"] for r in rows),
            "fault_energy_start_j": fault_rows[0]["stored_energy_j"] if fault_rows else None,
            "fault_energy_end_j": fault_rows[-1]["stored_energy_j"] if fault_rows else None,
        }
        summaries.append(summary)
        print(json.dumps(summary), flush=True)
    (output / "metrics.json").write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")
    write_csv(output / "metrics.csv", summaries)
    configuration = {"python": sys.version, "result_type": "teaching_averaged_model_only",
                     "limits": asdict(ProtectionLimits()), "parameters_by_case": parameters,
                     "fault_start_s": 0.050, "fault_removal_s": 0.065, "explicit_clear_s": 0.080,
                     "off_model": "ideal low-side held on, signed L/C states, no state reset"}
    (output / "parameters.json").write_text(json.dumps(configuration, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
