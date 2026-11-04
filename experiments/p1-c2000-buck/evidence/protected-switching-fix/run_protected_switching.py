"""导出 PWM 保护工况的采样、周期、有限窗口与平均模型差异。"""

import json
import sys
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

from buck_model import metrics
from protection import ProtectionLimits, energy_j, simulate_protected
from protected_switching import CASES, simulate_protected_switching, waveform_windows
from run_switching import write_csv
from switching_buck import PWM_FREQUENCY_HZ, steady_metrics


def crosses_primary_threshold(row, case, limits):
    if case == "overcurrent":
        return abs(row["inductor_current_a"]) >= limits.overcurrent_a
    if case == "overvoltage":
        return row["output_v"] >= limits.output_overvoltage_v
    return row["input_v"] <= limits.input_undervoltage_v


def summarize(case, p, samples, cycles, wave, events, averaged, averaged_events):
    trips = [r for r in events if r["reason"] == "trip"]
    avg_trips = [r for r in averaged_events if r["reason"] == "trip"]
    tail = [r["output_v"] for r in samples if r["time_s"] >= p.duration_s - 0.010]
    summary = {"case": case, "trip_count": len(trips), "control_sample_count": len(samples),
               "waveform_node_count": len(wave), "cycle_count": len(cycles),
               "final_10ms_mean_error_v": sum(tail) / len(tail) - p.target_v,
               "minimum_node_output_v": min(r["minimum_output_v"] for r in cycles),
               "minimum_node_current_a": min(r["minimum_current_a"] for r in cycles),
               "maximum_node_current_a": max(r["maximum_current_a"] for r in cycles),
               "maximum_node_output_v": max(r["maximum_output_v"] for r in cycles),
               "final_20_cycle_metrics": steady_metrics(cycles),
               "max_abs_switched_vs_averaged_sample_output_v": max(abs(a["output_v"] - b["output_v"]) for a, b in zip(samples, averaged)),
               "max_abs_switched_vs_averaged_sample_current_a": max(abs(a["inductor_current_a"] - b["inductor_current_a"]) for a, b in zip(samples, averaged))}
    if case == "load_step":
        summary["response"] = metrics(samples, "load_step", p)
        summary["averaged_response"] = metrics(averaged, "load_step", p)
        return summary
    trip_time = trips[0]["time_s"]
    trip = next(r for r in samples if r["time_s"] == trip_time)
    crossing_index = next(i for i, r in enumerate(wave)
                          if crosses_primary_threshold(r, case, ProtectionLimits()))
    crossing = wave[crossing_index]
    lower = crossing["time_s"] if case == "undervoltage" else wave[crossing_index - 1]["time_s"]
    upper = crossing["time_s"]
    clears = [r for r in samples if r["clear_result"] == "accepted"]
    clear = clears[0]
    after = [r for r in samples if r["time_s"] >= clear["time_s"]]
    outside = [i for i, r in enumerate(after) if abs(r["output_v"] - p.target_v) > 0.02 * p.target_v]
    entry = outside[-1] + 1 if outside else 0
    recovered_s = (after[entry]["time_s"] - clear["time_s"]
                   if entry < len(after) and after[-1]["time_s"] - after[entry]["time_s"] >= 0.002 else None)
    latched = [r for r in samples if r["state"] == "FAULT_LATCHED"]
    off_trace = [r for r in wave if r["state"] == "FAULT_LATCHED" and r["cycle"] < 2600]
    resistor_loss_j = sum((b["time_s"] - a["time_s"]) *
                         (a["output_v"]**2 / a["load_ohm"] + b["output_v"]**2 / b["load_ohm"]) / 2
                         for a, b in zip(off_trace, off_trace[1:]))
    end = off_trace[-1]
    energy_loss_j = energy_j(off_trace[0]["inductor_current_a"], off_trace[0]["output_v"], p) - energy_j(end["inductor_current_a"], end["output_v"], p)
    summary.update({"first_fault": trips[0]["latched_fault"], "first_trip_time_s": trip_time,
                    "first_threshold_crossing_bracket_s": [lower, upper],
                    "sample_detection_latency_bracket_s": [trip_time - upper, trip_time - lower],
                    "injection_to_trip_s": trip_time - 0.050,
                    "averaged_first_trip_time_s": avg_trips[0]["time_s"],
                    "switched_minus_averaged_trip_s": trip_time - avg_trips[0]["time_s"],
                    "trip_output_v": trip["output_v"], "trip_current_a": trip["inductor_current_a"],
                    "trip_energy_j": trip["stored_energy_j"],
                    "max_latched_sample_energy_increase_j": max(b["stored_energy_j"] - a["stored_energy_j"] for a, b in zip(latched, latched[1:])),
                    "clear_requests": [{key: r[key] for key in ("time_s", "clear_result", "active_faults", "output_v", "inductor_current_a", "stored_energy_j")}
                                       for r in samples if r["clear_request"]],
                    "accepted_clear_time_s": clear["time_s"],
                    "restart_ramp_complete_s": [r["time_s"] for r in events if r["reason"] == "soft_start_complete"][-1],
                    "recovery_from_clear_to_2_percent_s": recovered_s,
                    "off_window_start_s": off_trace[0]["time_s"], "off_window_end_s": end["time_s"],
                    "off_window_resistor_loss_j": resistor_loss_j,
                    "off_window_energy_loss_j": energy_loss_j,
                    "off_window_energy_balance_relative_error": (resistor_loss_j - energy_loss_j) / trip["stored_energy_j"]})
    return summary


def main():
    started = perf_counter()
    output = Path(__file__).resolve().parent / "protected_switching_results"
    output.mkdir(exist_ok=True)
    summaries, parameters = [], {}
    for case in CASES:
        p, samples, cycles, wave, events = simulate_protected_switching(case)
        _, averaged, averaged_events = simulate_protected(case)
        parameters[case] = asdict(p)
        write_csv(output / f"{case}_control_samples.csv", samples)
        write_csv(output / f"{case}_cycles.csv", cycles)
        write_csv(output / f"{case}_waveform.csv", wave)
        write_csv(output / f"{case}_events.csv", events)
        write_csv(output / f"{case}_averaged_comparison.csv", [
            {"time_s": a["time_s"], "switched_output_v": a["output_v"], "averaged_output_v": b["output_v"],
             "switched_minus_averaged_output_v": a["output_v"] - b["output_v"],
             "switched_current_a": a["inductor_current_a"], "averaged_current_a": b["inductor_current_a"],
             "switched_minus_averaged_current_a": a["inductor_current_a"] - b["inductor_current_a"],
             "switched_duty": a["duty"], "averaged_duty": b["duty"],
             "switched_state": a["state"], "averaged_state": b["state"]}
            for a, b in zip(samples, averaged)])
        summary = summarize(case, p, samples, cycles, wave, events, averaged, averaged_events)
        summaries.append(summary)
        print(json.dumps(summary), flush=True)
    (output / "metrics.json").write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")
    configuration = {"python": sys.version, "model": "ideal PWM synchronous Buck with unchanged sampled protection",
                     "pwm_frequency_hz": PWM_FREQUENCY_HZ, "maximum_integration_step_s": 0.5e-6,
                     "timing": "apply disturbance, sample and update protection/PI at PWM leading edge; zero computation delay; no asynchronous trip",
                     "threshold_crossing": "bracket from saved integration nodes, not exact continuous event solving; input step time is exact",
                     "fault_start_s": 0.050, "fault_removal_s": 0.065, "explicit_clear_s": 0.080,
                     "extra_clear_requests": "first active sample; first inactive but residual-energy sample when available",
                     "off_model": "ideal low-side held on; signed L/C states preserved; not both gates disabled",
                     "limits": asdict(ProtectionLimits()), "parameters_by_case": parameters,
                     "raw_waveform_windows_s": {case: [[a * p.control_period_s, b * p.control_period_s] for a, b in waveform_windows(case, round(parameters[case]["duration_s"] / p.control_period_s))] for case in CASES},
                     "extrema": "integration nodes plus PWM edges; cycle means and resistor loss use trapezoid quadrature",
                     "spice_status": "these protected cases are Python only; prior fixed-duty ngspice evidence remains separate"}
    (output / "parameters.json").write_text(json.dumps(configuration, indent=2) + "\n", encoding="utf-8")
    print(f"elapsed_s={perf_counter() - started:.6f}", flush=True)


if __name__ == "__main__":
    main()
