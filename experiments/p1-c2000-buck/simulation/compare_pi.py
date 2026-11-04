"""9 组 PI 有限比较和固定采样周期下的 RK4 步长减半；不修改默认模型。"""

import csv
import json
import math
import sys
from dataclasses import asdict, replace
from pathlib import Path

from buck_model import Parameters, metrics, simulate


CASES = ("startup", "load_step", "input_step")
KP_VALUES = (0.015, 0.030, 0.060)
KI_VALUES = (15.0, 30.0, 45.0)


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def existing_check_failures(rows, result, p):
    """逐项沿用 test_buck.py 的现有条件；不将未通过候选丢弃。"""
    failures = []
    checks = {
        "sample_count": len(rows) == 5001,
        "finite_values": all(math.isfinite(v) for row in rows for v in row.values()),
        "duty_range": all(0 <= r["duty"] <= p.maximum_duty for r in rows),
        "reference_start": rows[0]["reference_v"] == 0,
        "reference_end": abs(rows[1000]["reference_v"] - p.target_v) < 1e-7,
        "steady_error_lt_20mV": abs(result["steady_state_error_v"]) < 0.02,
        "overshoot_lt_10percent": result["overshoot_percent"] < 10,
        "post_event_deviation_lt_0p5V": result["post_event_max_abs_deviation_v"] < 0.5,
        "recovery_lt_30ms": (result["recovery_to_2_percent_s"] is not None
                             and result["recovery_to_2_percent_s"] < 0.030),
    }
    for name, passed in checks.items():
        if not passed:
            failures.append(name)
    return failures


def candidate_name(kp, ki):
    return f"kp_{kp:g}_ki_{ki:g}".replace(".", "p")


def main():
    output = Path(__file__).resolve().parent / "pi_comparison"
    output.mkdir(exist_ok=True)
    default = Parameters()
    case_results, candidates = [], []
    for kp in KP_VALUES:
        for ki in KI_VALUES:
            p = replace(default, kp_duty_per_v=kp, ki_duty_per_v_s=ki)
            name = candidate_name(kp, ki)
            results, failures = [], []
            for case in CASES:
                rows = simulate(case, p)
                result = metrics(rows, case, p)
                failed = existing_check_failures(rows, result, p)
                case_results.append({"candidate": name, "kp_duty_per_v": kp,
                                     "ki_duty_per_v_s": ki, **result,
                                     "passes_existing_checks": not failed,
                                     "failed_checks": "|".join(failed)})
                failures.extend(f"{case}:{check}" for check in failed)
                results.append(result)
            disturbances = [r for r in results if r["case"] != "startup"]
            recoveries = [r["recovery_to_2_percent_s"] for r in disturbances]
            summary = {
                "candidate": name, "kp_duty_per_v": kp, "ki_duty_per_v_s": ki,
                "passes_all_existing_checks": not failures,
                "failed_checks": "|".join(failures),
                "worst_disturbance_deviation_v": max(r["post_event_max_abs_deviation_v"] for r in disturbances),
                "worst_disturbance_recovery_s": max(recoveries) if all(t is not None for t in recoveries) else None,
                "worst_overshoot_percent": max(r["overshoot_percent"] for r in results),
                "startup_recovery_s": results[0]["recovery_to_2_percent_s"],
                "nominal_continuous_ki_bound": (1 + p.nominal_input_v * kp) / (
                    p.nominal_input_v * p.nominal_load_ohm * p.capacitance_f),
            }
            candidates.append(summary)
            print(json.dumps(summary), flush=True)
            write_csv(output / "all_case_metrics.csv", case_results)
            write_csv(output / "all_candidates.csv", candidates)

    eligible = [c for c in candidates if c["passes_all_existing_checks"]]
    selected = min(eligible, key=lambda c: (c["worst_disturbance_deviation_v"],
                                           c["worst_disturbance_recovery_s"],
                                           c["worst_overshoot_percent"]))
    default_result = next(c for c in candidates if c["kp_duty_per_v"] == default.kp_duty_per_v
                          and c["ki_duty_per_v_s"] == default.ki_duty_per_v_s)
    chosen = replace(default, kp_duty_per_v=selected["kp_duty_per_v"],
                     ki_duty_per_v_s=selected["ki_duty_per_v_s"])
    selection = {
        "result_type": "finite_teaching_model_comparison_not_global_optimum",
        "python": sys.version,
        "selection_rule": "among candidates passing all existing checks, minimize worst disturbance deviation, then recovery, then overshoot",
        "default_unchanged": asdict(default), "selected_for_comparison_only": asdict(chosen),
        "kp_values": KP_VALUES, "ki_values": KI_VALUES,
        "default_metrics": default_result, "selected_metrics": selected,
        "control_period_s_fixed": default.control_period_s,
        "integration_steps_s": [default.control_period_s / 4, default.control_period_s / 8],
    }
    (output / "selection.json").write_text(json.dumps(selection, indent=2) + "\n", encoding="utf-8")

    convergence, convergence_metrics = [], []
    for label, p in (("default", default), ("selected", chosen)):
        for case in CASES:
            coarse = simulate(case, p)
            fine_p = replace(p, integration_substeps=8)
            fine = simulate(case, fine_p)
            coarse_metric, fine_metric = metrics(coarse, case, p), metrics(fine, case, fine_p)
            convergence_metrics.extend([
                {"configuration": label, "integration_step_s": p.control_period_s / p.integration_substeps,
                 **coarse_metric},
                {"configuration": label, "integration_step_s": fine_p.control_period_s / fine_p.integration_substeps,
                 **fine_metric},
            ])
            trajectory = []
            for a, b in zip(coarse, fine):
                if a["time_s"] != b["time_s"]:
                    raise ValueError("Convergence comparison must use identical control sample times")
                trajectory.append({"time_s": a["time_s"], "output_5us_v": a["output_v"],
                                   "output_2p5us_v": b["output_v"],
                                   "output_fine_minus_coarse_v": b["output_v"] - a["output_v"],
                                   "current_fine_minus_coarse_a": b["inductor_current_a"] - a["inductor_current_a"],
                                   "duty_fine_minus_coarse": b["duty"] - a["duty"]})
            write_csv(output / f"{label}_{case}_step_comparison.csv", trajectory)
            if label == "selected":
                write_csv(output / f"selected_{case}.csv", coarse)
            summary = {
                "configuration": label, "case": case,
                "max_abs_output_difference_v": max(abs(r["output_fine_minus_coarse_v"]) for r in trajectory),
                "rms_output_difference_v": math.sqrt(sum(r["output_fine_minus_coarse_v"]**2 for r in trajectory) / len(trajectory)),
                "max_abs_current_difference_a": max(abs(r["current_fine_minus_coarse_a"]) for r in trajectory),
                "max_abs_duty_difference": max(abs(r["duty_fine_minus_coarse"]) for r in trajectory),
                "steady_state_error_delta_v": fine_metric["steady_state_error_v"] - coarse_metric["steady_state_error_v"],
                "overshoot_delta_percentage_points": fine_metric["overshoot_percent"] - coarse_metric["overshoot_percent"],
                "post_event_max_deviation_delta_v": fine_metric["post_event_max_abs_deviation_v"] - coarse_metric["post_event_max_abs_deviation_v"],
                "recovery_delta_s": fine_metric["recovery_to_2_percent_s"] - coarse_metric["recovery_to_2_percent_s"],
                "fine_failed_checks": "|".join(existing_check_failures(fine, fine_metric, fine_p)),
            }
            convergence.append(summary)
            print("step_comparison " + json.dumps(summary), flush=True)
    write_csv(output / "step_comparison_metrics.csv", convergence)
    write_csv(output / "both_step_sizes_metrics.csv", convergence_metrics)
    print("selected_for_comparison_only " + selected["candidate"], flush=True)


if __name__ == "__main__":
    main()
