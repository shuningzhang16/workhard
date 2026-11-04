"""执行两种开关工况、平均模型对照及积分步长减半，保留有限窗口波形。"""

import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path

from buck_model import metrics, plant_step, simulate
from switching_buck import PWM_FREQUENCY_HZ, simulate_switching, steady_metrics


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    output = Path(__file__).resolve().parent / "switching_results"
    output.mkdir(exist_ok=True)
    summaries, convergence, configuration = [], [], {}
    for case in ("fixed_duty", "controlled_load_step"):
        p, coarse, cycles, wave = simulate_switching(case)
        _, fine, fine_cycles, fine_wave = simulate_switching(case, max_step_s=0.25e-6)
        configuration[case] = asdict(p)
        for label, samples, period_rows, trace in (("0p5us", coarse, cycles, wave),
                                                  ("0p25us", fine, fine_cycles, fine_wave)):
            write_csv(output / f"{case}_{label}_control_samples.csv", samples)
            write_csv(output / f"{case}_{label}_cycles.csv", period_rows)
            write_csv(output / f"{case}_{label}_waveform.csv", trace)
        coarse_stats, fine_stats = steady_metrics(cycles), steady_metrics(fine_cycles)
        coarse_response = metrics(coarse, "load_step", p) if case == "controlled_load_step" else None
        fine_response = metrics(fine, "load_step", p) if case == "controlled_load_step" else None
        summary = {"case": case, "steady_0p5us": coarse_stats, "steady_0p25us": fine_stats,
                   "control_sample_metrics_0p5us": coarse_response,
                   "control_sample_metrics_0p25us": fine_response}
        differences = [{"time_s": a["time_s"], "output_0p5us_v": a["output_v"],
                        "output_0p25us_v": b["output_v"],
                        "output_fine_minus_coarse_v": b["output_v"] - a["output_v"],
                        "current_fine_minus_coarse_a": b["inductor_current_a"] - a["inductor_current_a"]}
                       for a, b in zip(coarse, fine)]
        write_csv(output / f"{case}_step_comparison.csv", differences)
        change = {"case": case, "max_abs_control_sample_output_difference_v": max(abs(r["output_fine_minus_coarse_v"]) for r in differences),
                  "max_abs_control_sample_current_difference_a": max(abs(r["current_fine_minus_coarse_a"]) for r in differences),
                  "steady_output_mean_delta_v": fine_stats["output_mean_v"] - coarse_stats["output_mean_v"],
                  "steady_output_pp_delta_v": fine_stats["mean_cycle_output_pp_v"] - coarse_stats["mean_cycle_output_pp_v"],
                  "steady_current_pp_delta_a": fine_stats["mean_cycle_current_pp_a"] - coarse_stats["mean_cycle_current_pp_a"],
                  "steady_output_pp_relative_delta": (fine_stats["mean_cycle_output_pp_v"] - coarse_stats["mean_cycle_output_pp_v"]) / fine_stats["mean_cycle_output_pp_v"],
                  "recovery_delta_s": fine_response["recovery_to_2_percent_s"] - coarse_response["recovery_to_2_percent_s"] if fine_response else None}
        convergence.append(change)
        if case == "fixed_duty":
            duty = p.target_v / p.nominal_input_v
            expected_i_pp = (p.nominal_input_v - p.target_v) * duty / (p.inductance_h * PWM_FREQUENCY_HZ)
            expected_v_pp = expected_i_pp / (8 * PWM_FREQUENCY_HZ * p.capacitance_f)
            avg_i = avg_v = 0.0
            dt = p.control_period_s / p.integration_substeps
            for _ in range(round(p.duration_s / dt)):
                avg_i, avg_v = plant_step(avg_i, avg_v, duty, p.nominal_input_v, p.nominal_load_ohm, p, dt)
            summary["fixed_duty_checks"] = {
                "duty": duty, "analytic_dc_output_v": duty * p.nominal_input_v,
                "analytic_dc_current_a": duty * p.nominal_input_v / p.nominal_load_ohm,
                "analytic_small_ripple_current_pp_a": expected_i_pp,
                "analytic_small_ripple_output_pp_v": expected_v_pp,
                "averaged_model_final_output_v": avg_v, "averaged_model_final_current_a": avg_i,
                "fine_output_pp_relative_error_to_formula": fine_stats["mean_cycle_output_pp_v"] / expected_v_pp - 1,
                "fine_current_pp_relative_error_to_formula": fine_stats["mean_cycle_current_pp_a"] / expected_i_pp - 1,
            }
        else:
            averaged = simulate("load_step", p)
            comparison = [{"time_s": a["time_s"], "averaged_output_v": a["output_v"],
                           "switched_sampled_output_v": b["output_v"],
                           "switched_minus_averaged_output_v": b["output_v"] - a["output_v"],
                           "averaged_duty": a["duty"], "switched_duty": b["duty"]}
                          for a, b in zip(averaged, fine)]
            write_csv(output / "controlled_load_step_averaged_comparison.csv", comparison)
            summary["averaged_model_control_sample_metrics"] = metrics(averaged, "load_step", p)
            summary["max_abs_switched_vs_averaged_sampled_output_v"] = max(abs(r["switched_minus_averaged_output_v"]) for r in comparison)
        summaries.append(summary)
        print(json.dumps(summary), flush=True)
        print("step_comparison " + json.dumps(change), flush=True)
    (output / "metrics.json").write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")
    write_csv(output / "step_comparison_metrics.csv", convergence)
    configuration = {"python": sys.version, "model": "ideal switched synchronous buck; signed L/C states; no losses",
                     "pwm_frequency_hz": PWM_FREQUENCY_HZ,
                     "timing": "sample output, update PI and apply leading-edge PWM at each period start; zero compute delay",
                     "integration_max_steps_s": [0.5e-6, 0.25e-6], "parameters": configuration,
                     "raw_waveform_windows_s": {"fixed_duty": [[0.0596, 0.060]],
                                                "controlled_load_step": [[0.0498, 0.0506], [0.0996, 0.100]]},
                     "cycle_statistics": "all periods; means use trapezoid quadrature and extrema use integration nodes including switching edges",
                     "spice_status": "this script runs Python only; separate ngspice evidence is in spice_results"}
    (output / "parameters.json").write_text(json.dumps(configuration, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
