"""在 WSL 实际运行本地解压的 ngspice，与已保存的 Python 开关波形对照。"""

import csv
import json
import math
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "simulation/spice_results"
COMMAND = ["wsl.exe", "-d", "Ubuntu-22.04", "--", ".tools/ngspice/usr/bin/ngspice"]


def run(arguments, log):
    result = subprocess.run(COMMAND + arguments, cwd=ROOT, capture_output=True,
                            encoding="utf-8", errors="replace", timeout=60)
    log.write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"ngspice exited {result.returncode}; evidence saved to {log}")
    return result.stdout + result.stderr


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def read_spice(path):
    # wr_singlescale + wr_vecnames：原始第一行为列名，其后 time, v(sw), v(out), i(L1)。
    lines = path.read_text("utf-8").splitlines()
    rows = []
    for line in lines[1:]:
        t, vsw, vo, il = map(float, line.split())
        rows.append({"time_s": t, "switch_voltage_v": vsw,
                     "output_v": vo, "inductor_current_a": il})
    return rows


def window_metrics(rows):
    span = rows[-1]["time_s"] - rows[0]["time_s"]
    result = {"window_start_s": rows[0]["time_s"], "window_end_s": rows[-1]["time_s"],
              "saved_points": len(rows)}
    for field in ("output_v", "inductor_current_a"):
        values = [r[field] for r in rows]
        integral = sum((b["time_s"] - a["time_s"]) * (a[field] + b[field]) / 2
                       for a, b in zip(rows, rows[1:]))
        result[f"{field}_time_mean"] = integral / span
        result[f"{field}_window_pp"] = max(values) - min(values)
    return result


def main():
    OUTPUT.mkdir(exist_ok=True)
    source_path = ROOT / "simulation/ideal_buck_fixed.cir"
    source = source_path.read_text("utf-8")
    # 仅替换输出/分析指令；脉冲源、元件、IC=0 和有限边沿参数均保留。
    circuit = "\n".join(line for line in source.splitlines()
                        if not line.lower().startswith((".tran", ".meas", ".end")))
    version = run(["--version"], OUTPUT / "ngspice-version.txt")
    commands = []
    for label, tran in (("steady", ".tran 0.25u 60m 59.6m 0.25u uic"),
                        ("startup", ".tran 0.05u 200u 0 0.05u uic")):
        relative = f"simulation/spice_results/{label}.cir"
        raw = f"simulation/spice_results/{label}.dat"
        deck = (circuit + "\n" + tran + "\n"
                ".control\nset wr_singlescale\nset wr_vecnames\nset numdgt=17\nrun\n"
                f"wrdata {raw} v(sw) v(out) i(L1)\nquit\n.endc\n.end\n")
        (ROOT / relative).write_text(deck, encoding="utf-8")
        arguments = ["-n", "-b", relative]
        log = run(arguments, OUTPUT / f"{label}.log")
        if "Using transient initial conditions" not in log:
            raise RuntimeError(f"{label}: initial-condition evidence missing; inspect saved log")
        commands.append(COMMAND + arguments)
        rows = read_spice(ROOT / raw)
        write_csv(OUTPUT / f"{label}.csv", rows)
    with (ROOT / "simulation/switching_results/fixed_duty_0p25us_waveform.csv").open(newline="", encoding="utf-8") as stream:
        python_rows = [{k: float(r[k]) for k in ("time_s", "switch_voltage_v", "output_v", "inductor_current_a")}
                       for r in csv.DictReader(stream)]
    spice_rows = read_spice(OUTPUT / "steady.dat")
    initial_rows = read_spice(OUTPUT / "startup.dat")
    a, b = window_metrics(python_rows), window_metrics(spice_rows)
    fields = ("output_v_time_mean", "inductor_current_a_time_mean", "output_v_window_pp", "inductor_current_a_window_pp")
    comparison = [{"metric": key, "python": a[key], "ngspice": b[key],
                   "ngspice_minus_python": b[key] - a[key],
                   "relative_error_percent": 100 * (b[key] / a[key] - 1)} for key in fields]
    write_csv(OUTPUT / "comparison.csv", comparison)
    expected_i_pp = 7 * (2 / 9) / (220e-6 * 50_000)
    expected_v_pp = expected_i_pp / (8 * 50_000 * 470e-6)
    initial = initial_rows[0]
    # 与已提交开关模型检查使用同样的直流绝对容差和 2% 纹波近似容差。
    checks = {
        "ngspice_dc_voltage_within_1e_5_v": abs(b["output_v_time_mean"] - 2) < 1e-5,
        "ngspice_dc_current_within_1e_5_a": abs(b["inductor_current_a_time_mean"] - 0.5) < 1e-5,
        "ngspice_voltage_ripple_formula_within_2_percent": abs(b["output_v_window_pp"] / expected_v_pp - 1) < 0.02,
        "ngspice_current_ripple_formula_within_2_percent": abs(b["inductor_current_a_window_pp"] / expected_i_pp - 1) < 0.02,
        "initial_saved_point_within_1ns": 0 <= initial["time_s"] <= 1e-9,
        "initial_output_near_zero": abs(initial["output_v"]) < 1e-6,
        "initial_current_near_zero": abs(initial["inductor_current_a"]) < 1e-6,
        "finite_spice_data": all(math.isfinite(v) for rows in (spice_rows, initial_rows) for row in rows for v in row.values()),
    }
    summary = {"model": "independent ideal fixed-duty SPICE transient; not hardware",
               "version": version, "python_window": a, "ngspice_window": b,
               "comparison": comparison, "initial_first_saved_point": initial,
               "initial_condition_definition": "L1 IC=0, C1 IC=0, .tran ... uic; no DC operating point initialization",
               "startup_saved_points": len(initial_rows), "checks": checks,
               "commands": commands,
               "package": {"name": "ngspice", "version": "36+ds-1ubuntu0.1",
                           "source": "Ubuntu jammy-updates/universe amd64", "installed_to_system": False}}
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"comparison": comparison, "initial": initial, "checks": checks}, indent=2), flush=True)
    if not all(checks.values()):
        raise AssertionError("SPICE cross-check failed; raw outputs and check results preserved")


if __name__ == "__main__":
    main()
