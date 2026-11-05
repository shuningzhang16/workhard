"""Four-cycle causal check: forbid Python control and perturb only native C state."""

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "simulation"))

from buck_model import Parameters
from c_controller import CController, load_library
from io_timing_buck import simulate_io_timing
from protection import ProtectedController
from run_switching import write_csv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    if not output.is_relative_to(ROOT):
        parser.error("--output must stay inside P1")
    output.mkdir(parents=True, exist_ok=True)
    library = load_library((ROOT / args.library).resolve())
    p = replace(Parameters(), duration_s=4 * Parameters().control_period_s)
    runs = {}
    with patch.object(ProtectedController, "update", side_effect=AssertionError("Python control is forbidden")) as forbidden:
        # Patch only the test's run length; production parameters stay unchanged.
        with patch("io_timing_buck.Parameters", return_value=p):
            for label, integral in (("zero", 0.0), ("perturbed", 0.05)):
                control = CController(library)
                control.native.pi.integral = integral
                result = simulate_io_timing("startup", True, controller=control)
                runs[label] = result[1]
                write_csv(output / f"takeover_{label}_samples.csv", result[1])
    zero, perturbed = runs["zero"], runs["perturbed"]
    checks = {"python_update_never_called": forbidden.call_count == 0,
              "four_integrated_cycles": len(zero) == len(perturbed) == 5,
              "c_initial_command_0p05": perturbed[0]["controller_duty"] == 0.05,
              "first_applied_duty_zero": perturbed[0]["duty"] == 0,
              "second_applied_duty_0p05": perturbed[1]["duty"] == 0.05,
              "plant_unchanged_before_delayed_pulse": perturbed[1]["output_v"] == perturbed[1]["inductor_current_a"] == 0,
              "plant_changes_after_delayed_pulse": perturbed[2]["output_v"] > zero[2]["output_v"] == 0
                                                     and perturbed[2]["inductor_current_a"] > zero[2]["inductor_current_a"] == 0}
    summary = {"scope": "isolated four-cycle test perturbation; production C and parameters unchanged",
               "python": sys.version, "argv": sys.argv, "python_update_call_count": forbidden.call_count,
               "initial_c_integral": {"zero": 0.0, "perturbed": 0.05},
               "checks": checks, "failures": [name for name, passed in checks.items() if not passed],
               "sample_2": {label: {key: rows[2][key] for key in ("time_s", "output_v", "inductor_current_a", "duty")}
                            for label, rows in runs.items()}}
    (output / "takeover.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary), flush=True)
    if summary["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
