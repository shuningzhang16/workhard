"""Independent ngspice MNA check of six local LC/diode commutation windows."""

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
import sys
import traceback

from dab_deadtime import Device, LEGS, edge_windows, simulate_window
from dab_sps import Parameters, simulate
from run_deadtime import load_cases
from run_experiment import write_csv


def selected_windows(source):
    cases = {(name, method): (alpha, cycle) for name, method, alpha, cycle in load_cases(source)}
    alpha, eps = cases[("m0.75_load0.1_forward", "EPS")]
    weak = next(w for w in edge_windows(eps, alpha) if w["switched"] == [0])
    _, sps = cases[("m0.75_load0.1_forward", "SPS")]
    sps_windows = edge_windows(sps, 0)
    reverse_alpha, reverse = cases[("m0.75_load0.1_reverse", "EPS")]
    reverse_weak = min((w for w in edge_windows(reverse, reverse_alpha) if w["switched"] in ([0], [1])),
                       key=lambda w: abs(w["initial_current_a"]))
    return [("matched_primary_clamp", edge_windows(simulate(Parameters(), 30), 0)[0], 500e-9),
            ("sps_favorable_primary", sps_windows[0], 500e-9),
            ("sps_opposing_secondary", sps_windows[1], 150e-9),
            ("eps_weak_short", weak, 150e-9), ("eps_weak_long", weak, 500e-9),
            ("eps_reverse_incomplete", reverse_weak, 500e-9)]


def netlist(window, duration, data_name):
    p, device = window["parameters"], Device()
    factors = (1.0, -1.0, -p.turns_ratio, p.turns_ratio)
    buses = (p.v1_v, p.v1_v, p.v2_v, p.v2_v)
    lines = ["Independent local DAB commutation teaching circuit",
        "* Not a TI transistor macro-model. Eight constant output capacitors.",
        "* Diodes: 0.8 V threshold plus 1 milliohm numerical slope resistance.",
        "* B sources implement a power-conserving ideal transformer port relation.",
        f"Vbus1 bus1 0 {p.v1_v:.16g}", f"Vbus2 bus2 0 {p.v2_v:.16g}",
        f"Bdrive link 0 V=v(n1a)-v(n1b)-{p.turns_ratio:.16g}*(v(n2a)-v(n2b))",
        f"Llink link 0 {p.inductance_h:.16g} IC={window['initial_current_a']:.16g}"]
    for j, leg in enumerate(LEGS):
        bus, initial = buses[j], buses[j] * window["before"][j]
        busnode = "bus1" if j < 2 else "bus2"
        lines.extend([f"Bport{leg} n{leg} 0 I={factors[j]:.16g}*i(Llink)",
            f"Ctop{leg} {busnode} n{leg} {device.coss_f:.16g} IC={bus-initial:.16g}",
            f"Cbot{leg} n{leg} 0 {device.coss_f:.16g} IC={initial:.16g}"])
        if j in window["switched"]:
            lines.extend([f"Bdh{leg} n{leg} {busnode} I=max((v(n{leg})-v({busnode})-{device.diode_drop_v})/0.001,0)",
                          f"Bdl{leg} 0 n{leg} I=max((-v(n{leg})-{device.diode_drop_v})/0.001,0)"])
        else:
            lines.append(f"Vhold{leg} n{leg} 0 {initial:.16g}")
    lines.extend([".options method=gear maxord=2 reltol=1e-7 abstol=1e-10 vntol=1e-9",
        ".control", "set wr_singlescale", "set wr_vecnames", "set numdgt=16",
        f"tran 0.2n {duration:.16g} 0 0.2n uic",
        f"wrdata {data_name} i(Llink) v(n1a) v(n1b) v(n2a) v(n2b)",
        "quit", ".endc", ".end", ""])
    return "\n".join(lines)


def read_spice_data(path, duration):
    data = [[float(x) for x in line.split()] for line in path.read_text().splitlines()[1:] if line.strip()]
    if len(data) < 2 or any(len(row) != 6 or not all(math.isfinite(x) for x in row) for row in data):
        raise ValueError("SPICE export must contain finite time, current and four node voltages")
    if not 0 <= data[0][0] <= 1e-11 or abs(data[-1][0] - duration) > 1e-15:
        raise ValueError("SPICE time axis does not cover the requested window")
    if any(a[0] >= b[0] for a, b in zip(data, data[1:])):
        raise ValueError("SPICE time axis must increase")
    return data


def execute_ngspice(invocation, output, name, duration):
    # quit can return zero even when analysis/wrdata failed. Remove only this
    # known export before execution, so a previous run cannot satisfy the read.
    data_path = output / f"{name}.dat"
    data_path.unlink(missing_ok=True)
    result = subprocess.run(invocation, cwd=output, capture_output=True, text=True, encoding="utf-8", timeout=60)
    (output / f"{name}.log").write_text(result.stdout + result.stderr + f"\nExit code: {result.returncode}\n", encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"ngspice failed for {name}; netlist and log retained")
    if not data_path.is_file():
        raise RuntimeError(f"ngspice returned zero but did not create {data_path.name}; log retained")
    return read_spice_data(data_path, duration)


def run(source, output, command):
    output.mkdir(parents=True, exist_ok=True)
    metadata = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "runner_argv": sys.orig_argv,
        "ngspice_command": command, "diode_slope_resistance_ohm": 0.001,
        "comparison_limits": {"node_voltage_v": 0.01, "inductor_current_a": 1e-4},
        "limit_reason": "1 mOhm diode regularization adds up to millivolts; compare against ideal hard clamps",
        "hardware_operations": False, "runs": []}
    summaries, comparisons = [], []
    try:
        version = subprocess.run(command + ["--version"], cwd=output, capture_output=True, text=True, encoding="utf-8", timeout=30)
        (output / "version.log").write_text(version.stdout + version.stderr, encoding="utf-8")
        for name, window, duration in selected_windows(source):
            circuit_path = output / f"{name}.cir"
            circuit_path.write_text(netlist(window, duration, f"{name}.dat"), encoding="utf-8")
            invocation = command + ["-n", "-b", circuit_path.name]
            metadata["runs"].append({"name": name, "command": invocation, "duration_s": duration,
                "initial_current_a": window["initial_current_a"], "before": window["before"],
                "after": window["after"], "switched": window["switched"]})
            (output / "run_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
            data = execute_ngspice(invocation, output, name, duration)
            rows, events = simulate_window(window, duration)
            fine, _ = simulate_window(window, duration, sample_step_s=0.5e-9)
            write_csv(output / f"{name}_python.csv", rows)
            cursor = 0
            max_current = max_voltage = 0.0
            for point in data:
                t = point[0]
                while cursor + 1 < len(rows) and rows[cursor]["t1_s"] < t:
                    cursor += 1
                row = rows[cursor]
                ratio = (t - row["t0_s"]) / (row["t1_s"] - row["t0_s"])
                expected = [row["i0_a"] + ratio * (row["i1_a"] - row["i0_a"])] + [
                    row[f"v0_{leg}_v"] + ratio * (row[f"v1_{leg}_v"] - row[f"v0_{leg}_v"]) for leg in LEGS]
                errors = [actual - reference for actual, reference in zip(point[1:], expected)]
                max_current = max(max_current, abs(errors[0]))
                max_voltage = max(max_voltage, *(abs(e) for e in errors[1:]))
                comparisons.append({"case": name, "t_s": t, "current_difference_a": errors[0],
                                    **{f"node_{leg}_difference_v": errors[j+1] for j, leg in enumerate(LEGS)}})
            step_error = max(abs(rows[-1][f"v1_{leg}_v"] - fine[-1][f"v1_{leg}_v"]) for leg in LEGS)
            summary = {"case": name, "duration_s": duration, "spice_points": len(data),
                "first_spice_time_s": data[0][0], "last_spice_time_s": data[-1][0],
                "max_current_difference_a": max_current, "max_node_voltage_difference_v": max_voltage,
                "python_half_step_node_difference_v": step_error,
                "python_completed_leg_turnons": sum(e["zvs_in_this_model"] for e in events),
                "leg_turnons": len(events)}
            summaries.append(summary)
            write_csv(output / "comparison.csv", comparisons)
            write_csv(output / "summary.csv", summaries)
            if max_current > 1e-4 or max_voltage > 0.01 or step_error > 1e-7:
                raise AssertionError(f"Independent SPICE comparison failed: {summary}")
        (output / "RESULTS.md").write_text(
            "# ngspice 独立换流验证\n\n六个局部网表均实际运行成功；包含完成、方向相反、死区不足与正反向 EPS。\n"
            "每个网表使用独立 MNA 求解 L、8 个线性 C、行为端口和二极管分段电导，未调用 Python 轨迹作为激励。\n"
            "每次运行前仅删除该案例的确定导出文件；随后要求新文件存在、数值有限且时间覆盖完整，避免退出码为零时误读旧数据。\n"
            "与 Python 的硬钳位区别仅为二极管额外 1 mΩ 数值斜率，比较容差预设 10 mV / 0.1 mA。\n\n"
            f"最大节点差 {max(s['max_node_voltage_difference_v'] for s in summaries):.6g} V，"
            f"最大电流差 {max(s['max_current_difference_a'] for s in summaries):.6g} A。\n"
            f"Python 输出采样间隔减半时最大末端节点差 {max(s['python_half_step_node_difference_v'] for s in summaries):.3e} V。\n\n"
            "网表、原始 ngspice 数据、日志、Python 波形及逐点误差均保留。相同教学器件假设的独立求解器一致，不等于真实 MOSFET 已验证。\n",
            encoding="utf-8")
        print("PASS: 6 independent ngspice commutation circuits")
        for summary in summaries:
            print(summary)
    except Exception:
        (output / "failure.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=root / "results_eps" / "comparisons.csv")
    parser.add_argument("--output", type=Path, default=root / "results_deadtime_spice")
    parser.add_argument("--ngspice-command", nargs="+", default=["wsl.exe", "-d", "Ubuntu-22.04", "--",
        "/mnt/e/UserData/Documents/ChatGPT/硬件/experiments/p1-c2000-buck/.tools/ngspice/usr/bin/ngspice"])
    args = parser.parse_args()
    run(args.source, args.output, args.ngspice_command)
