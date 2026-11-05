"""保存有限三工况的原时序/量化延迟对照；保留未满足原性能条件的结果。"""

import json
import sys
from dataclasses import asdict, replace
from pathlib import Path
from time import perf_counter

from buck_model import metrics
from compare_pi import existing_check_failures
from io_timing_buck import BOARD, CASES, simulate_io_timing, waveform_windows
from protection import ProtectionLimits
from run_switching import write_csv
from switching_buck import steady_metrics


NUMERIC_COLUMNS = ("time_s", "input_v", "load_ohm", "output_v", "inductor_current_a", "load_current_a", "reference_v", "duty")


def summarize(case, adapted, result):
    p, rows, cycles, wave, events, counterfactual = result
    trip_events = [r for r in events if r["reason"] == "trip"]
    response = metrics(rows, case if case != "overvoltage" else "load_step", p)
    failures = (existing_check_failures([{key: r[key] for key in NUMERIC_COLUMNS} for r in rows], response, p)
                if case != "overvoltage" else [])
    summary = {"case": case, "mode": "delayed_quantized" if adapted else "original_timing",
               "control_samples": len(rows), "waveform_nodes": len(wave), "response": response,
               "existing_response_check_failures": failures, "trip_count": len(trip_events),
               "peak_node_output_v": max(r["maximum_output_v"] for r in cycles),
               "minimum_node_output_v": min(r["minimum_output_v"] for r in cycles),
               "minimum_node_current_a": min(r["minimum_current_a"] for r in cycles),
               "steady_cycles": steady_metrics(cycles),
               "max_abs_measured_minus_true_output_v": max(abs(r["measured_output_v"] - r["output_v"]) for r in rows),
               "max_abs_pwm_quantization_duty_error": max(abs(r["next_pwm_duty"] - r["controller_duty"]) for r in rows),
               "adc_out_of_range_samples": sum(r["any_adc_input_out_of_range"] for r in rows),
               "unsafe_clear_candidate_samples": sum(r["unsafe_clear_candidate"] for r in rows),
               "first_hypothetical_unsafe_clear": counterfactual}
    if case != "overvoltage":
        return summary
    trip_time = trip_events[0]["time_s"]
    trip_row = next(r for r in rows if r["time_s"] == trip_time)
    crossing_index = next(i for i, r in enumerate(wave) if r["output_v"] >= ProtectionLimits().output_overvoltage_v)
    lower, upper = wave[crossing_index - 1]["time_s"], wave[crossing_index]["time_s"]
    accepted = [r for r in rows if r["clear_result"] == "accepted"]
    latched = [r for r in rows if r["state"] == "FAULT_LATCHED"]
    summary.update({"first_fault": trip_events[0]["latched_fault"], "first_trip_time_s": trip_time,
                    "injection_to_trip_s": trip_time - p.event_time_s,
                    "true_output_threshold_crossing_bracket_s": [lower, upper],
                    "true_threshold_to_detection_bracket_s": [trip_time - upper, trip_time - lower],
                    "trip_true_output_v": trip_row["output_v"], "trip_measured_output_v": trip_row["measured_output_v"],
                    "trip_previous_queued_duty": trip_row["previous_pwm_duty"], "trip_applied_duty": trip_row["duty"],
                    "trip_energy_j": trip_row["stored_energy_j"],
                    "max_latched_sample_energy_increase_j": max(b["stored_energy_j"] - a["stored_energy_j"] for a, b in zip(latched, latched[1:])),
                    "accepted_clear_times_s": [r["time_s"] for r in accepted],
                    "clear_requests": [{key: r[key] for key in ("time_s", "clear_result", "output_v", "inductor_current_a", "measured_output_v", "measured_current_a", "true_clear_eligible")}
                                       for r in rows if r["clear_request"]],
                    "recovery_from_clear_to_2_percent_s": metrics(rows, "load_step", replace(p, event_time_s=accepted[0]["time_s"]))["recovery_to_2_percent_s"] if accepted else None})
    return summary


def main():
    started = perf_counter()
    output = Path(__file__).resolve().parent / "io_timing_results"
    output.mkdir(exist_ok=True)
    summaries, parameters = [], {}
    for case in CASES:
        runs = []
        for adapted in (False, True):
            result = simulate_io_timing(case, adapted)
            p, rows, cycles, wave, events, _ = result
            parameters[case] = asdict(p)
            label = case + ("_delayed_quantized" if adapted else "_original_timing")
            for suffix, records in (("control_samples", rows), ("cycles", cycles), ("waveform", wave), ("events", events)):
                write_csv(output / f"{label}_{suffix}.csv", records)
            summary = summarize(case, adapted, result)
            summaries.append(summary)
            runs.append(rows)
            print(json.dumps(summary), flush=True)
        comparison = [{"time_s": a["time_s"], "original_output_v": a["output_v"], "adapted_output_v": b["output_v"],
                       "adapted_measured_output_v": b["measured_output_v"], "output_difference_v": b["output_v"] - a["output_v"],
                       "current_difference_a": b["inductor_current_a"] - a["inductor_current_a"],
                       "original_applied_duty": a["duty"], "adapted_controller_duty": b["controller_duty"], "adapted_applied_duty": b["duty"],
                       "original_state": a["state"], "adapted_state": b["state"]}
                      for a, b in zip(*runs)]
        write_csv(output / f"{case}_comparison.csv", comparison)
        summaries[-1]["max_abs_output_difference_from_original_v"] = max(abs(r["output_difference_v"]) for r in comparison)
        summaries[-1]["max_abs_current_difference_from_original_a"] = max(abs(r["current_difference_a"]) for r in comparison)
    (output / "metrics.json").write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")
    configuration = {"python": sys.version, "parameters_by_case": parameters, "limits": asdict(ProtectionLimits()),
                     "board_parameters_from": "firmware/board_config.h", "board_parameters": BOARD,
                     "integration_max_step_s": 0.5e-6,
                     "timing_assumption": "all three measurements sampled together at period start; previous CMPA command applied for this period; zero calculation delay and immediate sampled Trip override",
                     "adc_assumption": "ideal floor code bins, clipped 0..4095, nominal firmware decoder; no noise, skew, offset or acquisition dynamics",
                     "pwm_quantization": "int(duty*2000+0.5)/2000 as in target_main.c; one-period command delay",
                     "fault_model": "signed LC states with ideal low-side freewheel, unchanged; no device clamp model",
                     "clear_counterfactual": "one copied controller update using real trajectory measurements; not applied to main plant",
                     "hardware_scope": "simulation permits commands to study closed-loop effects; real target firmware remains boot-inhibited and OST-latched",
                     "raw_waveform_windows_s": {case: [[a * p.control_period_s, b * p.control_period_s] for a, b in waveform_windows(case, round(parameters[case]["duration_s"] / p.control_period_s))] for case in CASES}}
    (output / "parameters.json").write_text(json.dumps(configuration, indent=2) + "\n", encoding="utf-8")
    failed = [{"case": r["case"], "mode": r["mode"], "failures": r["existing_response_check_failures"]}
              for r in summaries if r["existing_response_check_failures"]]
    print("response_failures " + json.dumps(failed), flush=True)
    print(f"elapsed_s={perf_counter() - started:.6f}", flush=True)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
