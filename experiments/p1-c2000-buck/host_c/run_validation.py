"""Build/run host C with ASan+UBSan, then compare real PWM measurements sample by sample."""

import argparse
import csv
import json
import math
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "simulation"))
from protection import ProtectedController  # noqa: E402

CASES = ("load_step", "overcurrent", "overvoltage", "undervoltage")
STATES = {0: "SOFT_START", 1: "RUN", 2: "FAULT_LATCHED"}
CLEARS = {0: "not_requested", 1: "rejected_active_fault", 2: "rejected_residual_energy",
          3: "accepted", 4: "ignored_not_latched", 5: "rejected_unobservable_measurement"}
FAULTS = ((1, "OVERCURRENT"), (2, "OUTPUT_OVERVOLTAGE"), (4, "INPUT_UNDERVOLTAGE"))
DUTY_ABS_TOL = 1e-11
REFERENCE_ABS_TOL_V = 1e-14


def fault_string(mask):
    value = int(mask)
    if value < 0 or value > 7:
        raise ValueError(f"Unknown C fault mask: {value}")
    return "|".join(name for bit, name in FAULTS if value & bit)


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def compare_case(case, source, actual, output):
    if len(source) != len(actual):
        raise AssertionError(f"{case}: row count {len(actual)} != {len(source)}")
    control = ProtectedController()
    comparisons = []
    mismatches = []
    max_duty = max_reference = max_saved_duty = max_saved_reference = 0.0
    mismatch_rows = 0
    for k, (row, c) in enumerate(zip(source, actual)):
        expected = control.update(k, float(row["input_v"]), float(row["output_v"]),
                                  float(row["inductor_current_a"]), bool(int(row["clear_request"])))
        decoded = {"duty": float(c["duty"]), "reference_v": float(c["reference_v"]),
                   "state": STATES[int(c["state"])], "active_faults": fault_string(c["active_faults"]),
                   "latched_fault": fault_string(c["latched_fault"]), "clear_result": CLEARS[int(c["clear_result"])]}
        errors = []
        if int(c["sample"]) != k:
            errors.append("sample index")
        result = {"sample": k, "time_s": row["time_s"]}
        for key, tolerance in (("duty", DUTY_ABS_TOL), ("reference_v", REFERENCE_ABS_TOL_V)):
            delta = decoded[key] - expected[key]
            saved_delta = decoded[key] - float(row[key])
            result.update({"c_" + key: decoded[key], "python_" + key: expected[key],
                           "saved_" + key: float(row[key]), "c_minus_python_" + key: delta,
                           "c_minus_saved_" + key: saved_delta})
            if not math.isfinite(decoded[key]) or abs(delta) > tolerance or abs(saved_delta) > tolerance:
                errors.append(key)
        max_duty = max(max_duty, abs(result["c_minus_python_duty"]))
        max_reference = max(max_reference, abs(result["c_minus_python_reference_v"]))
        max_saved_duty = max(max_saved_duty, abs(result["c_minus_saved_duty"]))
        max_saved_reference = max(max_saved_reference, abs(result["c_minus_saved_reference_v"]))
        for key in ("state", "active_faults", "latched_fault", "clear_result"):
            result.update({"c_" + key: decoded[key], "python_" + key: expected[key], "saved_" + key: row[key]})
            if decoded[key] != expected[key] or decoded[key] != row[key]:
                errors.append(key)
        result["matches"] = int(not errors)
        comparisons.append(result)
        if errors:
            mismatch_rows += 1
            if len(mismatches) < 10:
                mismatches.append({"sample": k, "fields": errors})
    with (output / f"{case}_comparison.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(comparisons[0]))
        writer.writeheader()
        writer.writerows(comparisons)
    return {"case": case, "sample_count": len(source), "mismatch_rows": mismatch_rows,
            "max_abs_c_minus_python_duty": max_duty, "max_abs_c_minus_python_reference_v": max_reference,
            "max_abs_c_minus_saved_duty": max_saved_duty, "max_abs_c_minus_saved_reference_v": max_saved_reference,
            "first_mismatches": mismatches}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="host_c/results_" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"),
                        help="output directory inside P1; relative paths are resolved from the P1 root")
    args = parser.parse_args()
    started = perf_counter()
    output = (ROOT / args.output).resolve()
    if not output.is_relative_to(ROOT):
        parser.error("--output must stay inside the P1 experiment directory")
    output.mkdir(parents=True, exist_ok=False)
    build = output / "build"
    build.mkdir()
    build_relative = build.relative_to(ROOT).as_posix()
    commands = []
    flags = ["-std=c11", "-O1", "-g3", "-Wall", "-Wextra", "-Wpedantic", "-Wconversion",
             "-Wshadow", "-Wstrict-prototypes", "-Wmissing-prototypes", "-Werror",
             "-fno-fast-math", "-ffp-contract=off", "-fno-omit-frame-pointer", "-fsanitize=address,undefined"]
    launcher = ["wsl", "-d", "Ubuntu-22.04", "--"] if sys.platform == "win32" else []
    prefix = launcher + ["/usr/bin/env", "PATH=/usr/bin:/bin",
              "ASAN_OPTIONS=detect_leaks=1:halt_on_error=1", "UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1"]

    def run(args):
        command = prefix + args
        result = subprocess.run(command, cwd=ROOT, text=True, encoding="utf-8", errors="replace", capture_output=True)
        commands.append({"argv": command, "returncode": result.returncode,
                         "stdout": result.stdout, "stderr": result.stderr})
        with (output / f"command_{len(commands):02d}.json").open("x", encoding="utf-8") as stream:
            json.dump(commands[-1], stream, indent=2)
        print("command " + json.dumps(args), flush=True)
        print(result.stdout, end="", flush=True)
        if result.stderr:
            print(result.stderr, end="", flush=True)
        if result.returncode:
            raise RuntimeError(f"Command failed with status {result.returncode}; evidence retained in {output}")

    run(["/usr/bin/gcc", "--version"])
    run(["/usr/bin/uname", "-sm"])
    for name, source in (("replay_csv", "replay_csv.c"), ("test_boundaries", "test_boundaries.c")):
        run(["/usr/bin/gcc", *flags, "host_c/buck_control.c", "host_c/" + source,
             "-lm", "-o", build_relative + "/" + name])
    run(["./" + build_relative + "/test_boundaries"])
    summaries = []
    for case in CASES:
        source = f"simulation/protected_switching_results/{case}_control_samples.csv"
        actual = (output.relative_to(ROOT) / f"{case}_c.csv").as_posix()
        run(["./" + build_relative + "/replay_csv", source, actual])
        summary = compare_case(case, read_csv(ROOT / source), read_csv(ROOT / actual), output)
        summaries.append(summary)
        print(json.dumps(summary), flush=True)
    configuration = {"scope": "host C sampled control replay only; no plant execution, C2000 build, ISR or hardware trip validation",
                     "python": sys.version, "compiler_flags": flags,
                     "execution_mode": "Windows Python -> WSL GCC" if launcher else "native Linux Python/GCC",
                     "output_directory": output.relative_to(ROOT).as_posix(),
                     "duty_absolute_tolerance": DUTY_ABS_TOL, "reference_absolute_tolerance_v": REFERENCE_ABS_TOL_V,
                     "float_tolerance_basis": "binary64 epsilon=2^-52; 4*7001*epsilon=6.22e-12 at unit scale motivates 1e-11 duty tolerance; few operations on a 2 V ramp motivate 1e-14 V reference tolerance. Engineering roundoff allowances, not formal error bounds. Discrete results compare exactly.",
                     "parameters": {"sample_period_s": 20e-6, "kp": 0.03, "ki": 30.0, "maximum_duty": 0.95,
                                    "target_v": 2.0, "soft_start_s": 0.020, "overcurrent_a": 2.5,
                                    "overvoltage_v": 2.4, "undervoltage_v": 6.0, "clear_abs_output_v": 0.1,
                                    "clear_abs_current_a": 0.1},
                     "measurement_sources": [f"simulation/protected_switching_results/{case}_control_samples.csv" for case in CASES]}
    (output / "parameters.json").write_text(json.dumps(configuration, indent=2) + "\n", encoding="utf-8")
    (output / "metrics.json").write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")
    with (output / "commands.json").open("x", encoding="utf-8") as stream:
        json.dump(commands, stream, indent=2)
    if any(r["mismatch_rows"] for r in summaries):
        raise AssertionError("C/Python mismatch; full comparison evidence retained")
    print(f"PASS: {sum(r['sample_count'] for r in summaries)} samples; 4 replays and boundary executable completed with ASan+UBSan", flush=True)
    print(f"elapsed_s={perf_counter() - started:.6f}", flush=True)


if __name__ == "__main__":
    main()
