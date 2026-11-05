"""只对接近 10% 超调的量化负载案例做积分步长减半，不改变采样/控制。"""
import csv
import json
from pathlib import Path

from buck_model import metrics
from io_timing_buck import simulate_io_timing
from run_switching import write_csv


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / "evidence/io-timing-refinement"
    output.mkdir(exist_ok=True)
    with (root / "simulation/io_timing_results/load_step_delayed_quantized_control_samples.csv").open(newline="") as stream:
        coarse = list(csv.DictReader(stream))
    p, fine, cycles, wave, events, _ = simulate_io_timing("load_step", True, 0.25e-6)
    write_csv(output / "fine_control_samples.csv", fine)
    write_csv(output / "fine_cycles.csv", cycles)
    write_csv(output / "fine_waveform.csv", wave)
    differences = [{"time_s": b["time_s"], "output_difference_v": b["output_v"] - float(a["output_v"]),
                    "current_difference_a": b["inductor_current_a"] - float(a["inductor_current_a"]),
                    "same_pwm_counts": int(int(a["cmpa_counts"]) == b["cmpa_counts"]),
                    "same_state": int(a["state"] == b["state"])} for a, b in zip(coarse, fine)]
    summary = {"coarse_max_step_s": 0.5e-6, "fine_max_step_s": 0.25e-6,
               "control_period_s": p.control_period_s,
               "max_abs_sample_output_difference_v": max(abs(r["output_difference_v"]) for r in differences),
               "max_abs_sample_current_difference_a": max(abs(r["current_difference_a"]) for r in differences),
               "changed_pwm_count_samples": sum(not r["same_pwm_counts"] for r in differences),
               "changed_state_samples": sum(not r["same_state"] for r in differences),
               "fine_sample_metrics": metrics(fine, "load_step", p),
               "fine_node_peak_v": max(r["maximum_output_v"] for r in cycles),
               "fine_node_overshoot_percent": 100 * (max(r["maximum_output_v"] for r in cycles) / p.target_v - 1),
               "trip_count": sum(r["reason"] == "trip" for r in events)}
    write_csv(output / "step_comparison.csv", differences)
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary), flush=True)
    if summary["max_abs_sample_output_difference_v"] >= 1e-6 or summary["changed_pwm_count_samples"] or summary["changed_state_samples"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
