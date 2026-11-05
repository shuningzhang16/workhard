"""Run independent C/Python closed loops; save trajectories before assessing results."""

import argparse
import ctypes as ct
import json
import math
import sys
from dataclasses import asdict, replace
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "simulation"))

from buck_model import metrics
from c_controller import BuckCommand, BuckController, CController, load_library
from compare_pi import existing_check_failures
from io_timing_buck import BOARD, FAULT_CASES, NORMAL_CASES, simulate_io_timing, waveform_windows
from protection import ProtectionLimits
from run_io_timing import NUMERIC_COLUMNS
from run_protected_switching import crosses_primary_threshold
from run_switching import write_csv
from run_validation import DUTY_ABS_TOL, REFERENCE_ABS_TOL_V


def describe_and_check(case, result):
    p, rows, cycles, wave, events, shadow = result
    failures = []

    def check(name, passed):
        if not passed:
            failures.append(name)

    check("sample_count", len(rows) == round(p.duration_s / p.control_period_s) + 1)
    check("finite_plant_and_duty", all(math.isfinite(r[key]) for r in rows
                                      for key in ("output_v", "inductor_current_a", "duty")))
    check("duty_range", all(0 <= r["duty"] <= p.maximum_duty for r in rows))
    check("one_period_delay_or_trip", all(r["duty"] == (0.0 if k == 0 or r["state"] == "FAULT_LATCHED"
                                                       else rows[k - 1]["next_pwm_duty"])
                                           for k, r in enumerate(rows)))
    periods = {}
    for node in wave:
        periods.setdefault(node["cycle"], []).append(node)
    pulse_error = max(abs(sum((b["time_s"] - a["time_s"]) *
                             (a["switch_voltage_v"] + b["switch_voltage_v"]) / 2
                             for a, b in zip(trace, trace[1:])) / p.control_period_s
                          - rows[k]["duty"] * rows[k]["input_v"])
                      for k, trace in periods.items())
    check("actual_pulse_area", pulse_error <= 1e-8)  # Existing PWM test tolerance.
    trips = [r for r in events if r["reason"] == "trip"]
    peak = max(r["maximum_output_v"] for r in cycles)
    summary = {"control_samples": len(rows), "cycles": len(cycles), "waveform_nodes": len(wave),
               "peak_node_output_v": peak, "node_overshoot_percent": 100 * (peak / p.target_v - 1),
               "minimum_node_output_v": min(r["minimum_output_v"] for r in cycles),
               "minimum_node_current_a": min(r["minimum_current_a"] for r in cycles),
               "trip_count": len(trips), "max_abs_pulse_mean_voltage_error_v": pulse_error,
               "adc_out_of_range_samples": sum(r["any_adc_input_out_of_range"] for r in rows),
               "unsafe_clear_candidate_samples": sum(r["unsafe_clear_candidate"] for r in rows),
               "first_hypothetical_unsafe_clear": shadow, "verification_failures": failures}
    if case in NORMAL_CASES:
        response = metrics(rows, case, p)
        failures.extend(existing_check_failures([{key: r[key] for key in NUMERIC_COLUMNS} for r in rows], response, p))
        check("normal_case_no_trip", not trips)
        summary["response"] = response
        return summary

    check("one_trip", len(trips) == 1)
    if not trips:
        return summary
    first = next(k for k, r in enumerate(rows) if r["state"] == "FAULT_LATCHED")
    trip = rows[first]
    cause = {"overcurrent": "OVERCURRENT", "overvoltage": "OUTPUT_OVERVOLTAGE",
             "undervoltage": "INPUT_UNDERVOLTAGE"}[case]
    check("initial_cause", trip["latched_fault"] == cause)
    check("active_clear_rejected", trip["clear_result"] == "rejected_active_fault")
    latched = rows[first:4000]
    check("latch_retained", all(r["state"] == "FAULT_LATCHED" and r["latched_fault"] == cause
                                and r["duty"] == 0 and r["reference_v"] == 0 for r in latched))
    energy_increase = max(b["stored_energy_j"] - a["stored_energy_j"] for a, b in zip(latched, latched[1:]))
    check("freewheel_energy_decay", energy_increase <= 1e-12)
    check("latched_pulses_zero", all(r["switch_voltage_v"] == 0 and r["high_side_on"] == 0
                                     for r in wave if first <= r["cycle"] < 4000))
    for k in (first, 4000):
        before, after = periods[k - 1][-1], periods[k][0]
        check(f"continuous_LC_at_{k}", all(before[key] == after[key] == rows[k][key]
                                           for key in ("output_v", "inductor_current_a")))
    accepted = [r for r in rows if r["clear_result"] == "accepted"]
    check("only_explicit_80ms_clear", [r["time_s"] for r in accepted] == [0.08])
    check("true_state_clear_eligible", bool(rows[4000]["true_clear_eligible"]))
    check("soft_start_restarted", rows[4000]["reference_v"] == 0 and rows[4001]["reference_v"] == 0.002
          and rows[5000]["reference_v"] == 2 and rows[5000]["state"] == "RUN")
    check("actual_restarted_pulses", any(r["high_side_on"] == 1 for r in wave if 4000 <= r["cycle"] < 4030))
    if shadow:
        original = next(r for r in rows if r["time_s"] == shadow["time_s"])
        check("counterfactual_not_applied", not shadow["applied_to_main_trajectory"]
              and original["state"] == "FAULT_LATCHED" and original["clear_request"] == 0 and original["duty"] == 0)
    crossing_index = next(i for i, r in enumerate(wave) if crosses_primary_threshold(r, case, ProtectionLimits()))
    upper = wave[crossing_index]["time_s"]
    lower = upper if case == "undervoltage" else wave[crossing_index - 1]["time_s"]
    recovery = metrics(rows, case, replace(p, event_time_s=0.08))["recovery_to_2_percent_s"]
    check("recovered_before_end", recovery is not None and abs(rows[-1]["output_v"] - 2) < 0.02)
    summary.update({"first_fault": trip["latched_fault"], "first_trip_time_s": trip["time_s"],
                    "injection_to_trip_s": trip["time_s"] - 0.05,
                    "true_threshold_crossing_bracket_s": [lower, upper],
                    "true_threshold_to_detection_bracket_s": [trip["time_s"] - upper, trip["time_s"] - lower],
                    "trip_previous_queued_duty": trip["previous_pwm_duty"], "trip_applied_duty": trip["duty"],
                    "trip_energy_j": trip["stored_energy_j"], "max_latched_sample_energy_increase_j": energy_increase,
                    "clear_requests": [{key: r[key] for key in ("time_s", "clear_result", "output_v", "inductor_current_a",
                                                               "measured_output_v", "measured_current_a", "true_clear_eligible")}
                                       for r in rows if r["clear_request"]],
                    "recovery_from_clear_to_2_percent_s": recovery})
    return summary


def compare_runs(case, python_result, c_result, output):
    py_rows, c_rows = python_result[1], c_result[1]
    differences = []
    # Once quantized PWM and stimuli agree, the same deterministic plant must
    # agree exactly. Only unquantized controller outputs use prior C tolerances.
    numeric = {"controller_duty": DUTY_ABS_TOL, "reference_v": REFERENCE_ABS_TOL_V,
               "output_v": 0.0, "inductor_current_a": 0.0, "duty": 0.0}
    exact = ("time_s", "raw_vin", "raw_vout", "raw_current", "cmpa_counts", "state", "active_faults",
             "latched_fault", "clear_request", "clear_result", "unsafe_clear_candidate")
    for k, (a, b) in enumerate(zip(py_rows, c_rows)):
        row = {"sample": k, "time_s": b["time_s"]}
        for key in numeric:
            row["c_minus_python_" + key] = b[key] - a[key]
        mismatches = [key for key, tolerance in numeric.items()
                      if not math.isfinite(row["c_minus_python_" + key]) or abs(row["c_minus_python_" + key]) > tolerance]
        mismatches += [key for key in exact if a[key] != b[key]]
        row["mismatched_fields"] = "|".join(mismatches)
        differences.append(row)
    write_csv(output / f"{case}_comparison.csv", differences)
    return {"case": case, "samples": len(differences), "same_sample_count": len(py_rows) == len(c_rows),
            "mismatch_rows": sum(bool(r["mismatched_fields"]) for r in differences),
            "max_abs_differences": {key: max(abs(r["c_minus_python_" + key]) for r in differences) for key in numeric},
            "same_events": python_result[4] == c_result[4], "same_counterfactual": python_result[5] == c_result[5]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    if not output.is_relative_to(ROOT):
        parser.error("--output must stay inside P1")
    output.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    library = load_library((ROOT / args.library).resolve())
    summaries, comparisons, parameters, calls = [], [], {}, {}
    for case in NORMAL_CASES + FAULT_CASES:
        # Each call starts its own zero-energy plant and controller. No CSV
        # measurements, reference outputs or other trajectory drive either run.
        python_result = simulate_io_timing(case, True)
        control = CController(library)
        c_result = simulate_io_timing(case, True, controller=control)
        calls[case] = control.main_step_calls
        for backend, result in (("python", python_result), ("c", c_result)):
            p, rows, cycles, wave, events, _ = result
            parameters[case] = asdict(p)
            for suffix, records in (("control_samples", rows), ("cycles", cycles), ("waveform", wave), ("events", events)):
                write_csv(output / f"{case}_{backend}_{suffix}.csv", records)
            summary = {"case": case, "backend": backend, **describe_and_check(case, result)}
            if backend == "c":
                summary["native_main_step_calls"] = control.main_step_calls
                if control.main_step_calls != len(rows):
                    summary["verification_failures"].append("native_call_count")
            summaries.append(summary)
        comparisons.append(compare_runs(case, python_result, c_result, output))
        # Persist after every completed case, including any failed checks.
        (output / "metrics.json").write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")
        (output / "comparisons.json").write_text(json.dumps(comparisons, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(comparisons[-1]), flush=True)
    config = {"python": sys.version, "scope": "host shared C controller drives PWM plant at every sample; independent Python comparison",
              "library": args.library, "native_main_step_calls": calls,
              "ctypes_native_struct_bytes": {"BuckController": ct.sizeof(BuckController), "BuckCommand": ct.sizeof(BuckCommand)},
              "parameters_by_case": parameters, "limits": asdict(ProtectionLimits()), "board_parameters": BOARD,
              "integration_max_step_s": 0.5e-6, "control_period_s": 20e-6,
              "timing": "simultaneous ideal period-start ADC; one-period quantized PWM delay; immediate sampled Trip override",
              "adc": "existing ideal floor bins and 0..4095 clipping; nominal provisional scaling; no real SOC skew",
              "clear_policy": "first active request, first inactive residual request when available, explicit 80 ms clear; copied-controller probe never applied to main plant",
              "faults": "50..65 ms: R=0.25 ohm / Vin=14 V / Vin=4.5 V; original nominal values restored at 65 ms",
              "signed_plant": "unchanged ideal low-side freewheel; no physical negative-voltage clamp",
              "comparison": "original duty/reference tolerances 1e-11/1e-14; identical quantized drive must give identical plant trajectories; discrete fields exact",
              "sanitizer": "UBSan shared library; prior ASan replay evidence is separate",
              "hardware": "no target execution, real ADC/ISR timing, flashing or output enabling",
              "waveform_windows_s": {case: [[a * 20e-6, b * 20e-6] for a, b in waveform_windows(case, round(values['duration_s'] / 20e-6))]
                                     for case, values in parameters.items()}}
    (output / "parameters.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    failures = [{"case": r["case"], "backend": r["backend"], "checks": r["verification_failures"]}
                for r in summaries if r["verification_failures"]]
    differences = [r["case"] for r in comparisons if r["mismatch_rows"] or not r["same_sample_count"]
                   or not r["same_events"] or not r["same_counterfactual"]]
    status = {"verification_failures": failures, "comparison_failures": differences,
              "native_main_step_calls": sum(calls.values()), "elapsed_s": perf_counter() - started}
    (output / "status.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status), flush=True)
    if failures or differences:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
