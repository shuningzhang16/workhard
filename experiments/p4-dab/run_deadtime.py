"""Finite same-ideal-power SPS/EPS commutation windows, without retuning."""

import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
import sys
import traceback

from dab_deadtime import Device, edge_windows, simulate_window
from dab_eps import simulate_eps
from dab_sps import Parameters, simulate
from run_experiment import write_csv


def load_cases(source):
    with source.open(encoding="utf-8", newline="") as stream:
        inputs = list(csv.DictReader(stream))
    # Four existing targets, both methods: mismatch light load, reverse, medium,
    # and matched-voltage light load. No new modulation optimization.
    selected = ("m0.75_load0.1_forward", "m0.75_load0.1_reverse",
                "m0.75_load0.5_forward", "m1_load0.1_forward")
    cases = []
    for name in selected:
        row = next(r for r in inputs if r["case"] == name)
        p = Parameters(**{key: float(row[key]) for key in asdict(Parameters())})
        for method in ("SPS", "EPS"):
            alpha = 0 if method == "SPS" else float(row["eps_alpha_deg"])
            cycle = simulate(p, float(row["sps_phase_deg"])) if method == "SPS" else simulate_eps(p, alpha, float(row["eps_phase_deg"]))
            if abs(cycle.metrics["p2_time_w"] - float(row["target_w"])) > 1e-7:
                raise AssertionError("Original equal-power operating point mismatch")
            cases.append((name, method, alpha, cycle))
    return cases


def run(source, output):
    output.mkdir(parents=True, exist_ok=True)
    metadata = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "command_argv": sys.orig_argv,
        "python_version": sys.version, "device": asdict(Device()), "deadtime_s": [20e-9, 150e-9, 500e-9],
        "sample_step_s": 1e-9, "source": str(source.resolve()),
        "model": "local simultaneous-leg LC commutation, constant Qoss/30 V capacitance, fixed-drop diode clamps",
        "device_source": "https://www.ti.com/lit/ds/symlink/csd18540q5b.pdf",
        "source_location": "SLPS488B, April 2017, page 3; Qoss=83 nC at 30 V, diode VSD=0.8 V at 28 A",
        "assumptions": ["constant capacitance outside the 30 V charge anchor",
                        "fixed diode drop at all model currents", "zero series resistance during local commutation",
                        "initial current from each original ideal periodic edge, not a corrected periodic solution"],
        "hardware_operations": False}
    (output / "run_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    (output / "input_comparisons.csv").write_bytes(source.read_bytes())
    all_events, summaries, checks = [], [], []
    try:
        for name, method, alpha, cycle in load_cases(source):
            for deadtime in metadata["deadtime_s"]:
                key = f"{name}_{method}_{round(deadtime * 1e9)}ns"
                wave, events = [], []
                windows = edge_windows(cycle, alpha)
                for index, window in enumerate(windows):
                    rows, leg_events = simulate_window(window, deadtime)
                    wave.extend({"window_index": index, "edge_time_s": window["edge_time_s"], **r} for r in rows)
                    events.extend({"case": name, "method": method, "deadtime_s": deadtime,
                                   "window_index": index, "edge_time_s": window["edge_time_s"], **e} for e in leg_events)
                path = output / f"{key}_waveform.csv"
                write_csv(path, wave)
                all_events.extend(events)
                summaries.append({"case": name, "method": method, "deadtime_s": deadtime,
                    "alpha_deg": alpha, "phase_deg": cycle.phase_deg, "v2_v": cycle.parameters.v2_v,
                    "ideal_target_power_w": cycle.metrics["p2_time_w"], "ideal_rms_current_a": cycle.metrics["i_rms_a"],
                    "leg_turnons": len(events), "zvs_in_model": sum(e["zvs_in_this_model"] for e in events),
                    "incomplete_turnons": sum(not e["zvs_in_this_model"] for e in events),
                    "favorable_but_incomplete": sum(e["initial_directional_current_a"] > 1e-9 and not e["zvs_in_this_model"] for e in events),
                    "max_positive_vds_at_turnon_v": max(max(0, e["incoming_vds_at_turnon_v"]) for e in events),
                    "diode_energy_sum_j": math.fsum(r["diode_energy_j"] for r in wave),
                    "residual_coss_energy_sum_j": math.fsum(e["residual_coss_energy_j"] for e in events)})
                write_csv(output / "leg_turnons.csv", all_events)
                write_csv(output / "case_summary.csv", summaries)
                with path.open(encoding="utf-8", newline="") as stream:
                    persisted = list(csv.DictReader(stream))
                continuity = 0.0
                node_continuity = initial_state_error = rail_violation = 0.0
                buses = (cycle.parameters.v1_v, cycle.parameters.v1_v, cycle.parameters.v2_v, cycle.parameters.v2_v)
                for r in persisted:
                    window = windows[int(r["window_index"])]
                    if float(r["t0_s"]) == 0:
                        initial_state_error = max(initial_state_error, abs(float(r["i0_a"]) - window["initial_current_a"]))
                    for j, leg in enumerate(("1a", "1b", "2a", "2b")):
                        start, end = float(r[f"v0_{leg}_v"]), float(r[f"v1_{leg}_v"])
                        if float(r["t0_s"]) == 0:
                            initial_state_error = max(initial_state_error, abs(start - window["before"][j] * buses[j]))
                        rail_violation = max(rail_violation, -Device().diode_drop_v - min(start, end),
                                             max(start, end) - buses[j] - Device().diode_drop_v)
                for a, b in zip(persisted, persisted[1:]):
                    if a["window_index"] == b["window_index"]:
                        continuity = max(continuity, abs(float(a["i1_a"]) - float(b["i0_a"])),
                                         abs(float(a["t1_s"]) - float(b["t0_s"])))
                        node_continuity = max(node_continuity, *(abs(float(a[f"v1_{leg}_v"]) - float(b[f"v0_{leg}_v"]))
                                                                 for leg in ("1a", "1b", "2a", "2b")))
                energy = max(abs(float(r["cumulative_energy_residual_j"])) for r in persisted)
                # Independent trapezoidal integration from endpoint powers.
                integral = math.fsum((float(r["t1_s"]) - float(r["t0_s"])) / 2 * (
                    float(r["source_power0_w"]) + float(r["source_power1_w"]) -
                    float(r["diode_power0_w"]) - float(r["diode_power1_w"])) for r in persisted)
                stored_change = math.fsum(float(r["stored_energy1_j"]) - float(r["stored_energy0_j"]) for r in persisted)
                check = {"case": key, "rows": len(wave), "continuity_error": continuity,
                         "node_continuity_error_v": node_continuity, "initial_state_error": initial_state_error,
                         "max_diode_rail_violation_v": rail_violation,
                         "max_window_energy_residual_j": energy,
                         "independent_trapezoid_energy_residual_j": integral - stored_change}
                checks.append(check)
                write_csv(output / "csv_checks.csv", checks)
                if continuity or node_continuity or initial_state_error or rail_violation > 1e-8 or energy > 1e-10 or abs(integral - stored_change) > 5e-10:
                    raise AssertionError(f"Dead-time waveform verification failed: {check}")
        command = [sys.executable, "-B", "-X", "utf8", "-m", "unittest", "-v",
                   "test_dab_sps", "test_dab_eps", "test_dab_transient", "test_commutation_polarity",
                   "test_dab_power_loop", "test_power_points", "test_dab_deadtime", "test_deadtime_spice"]
        test = subprocess.run(command, cwd=Path(__file__).resolve().parent, capture_output=True, text=True, encoding="utf-8")
        (output / "tests.log").write_text("Command: " + subprocess.list2cmdline(command) + "\n" + test.stdout + test.stderr +
                                          f"\nExit code: {test.returncode}\n", encoding="utf-8")
        if test.returncode:
            raise RuntimeError("Tests failed; full window traces retained")
        lines = ["# 局部死区换流动态结果", "", "四个原有目标功率 × SPS/EPS × 三个死区；未重新调参。",
            "同功率只指来源的理想周期解；此处每个边沿独立初始化实际边沿电流，不宣称含死区的全周期仍同功率。",
            "同时换流的桥臂共享一个动态电感电流；由节点电压判定，不由初始极性直接判定。",
            "器件为 Qoss/30 V 线性电荷等效教学模型、0.8 V 固定压降钳位；不是原厂 MOSFET 模型。", "",
            "| 原目标 W | 方法 | 死区 ns | 模型内完成 / 8 | 极性有利但未完成 | 最大正 VDS / V |",
            "| ---: | --- | ---: | ---: | ---: | ---: |"]
        for s in summaries:
            lines.append(f"| {s['ideal_target_power_w']:.3f} | {s['method']} | {s['deadtime_s']*1e9:g} | "
                         f"{s['zvs_in_model']} | {s['favorable_but_incomplete']} | {s['max_positive_vds_at_turnon_v']:.6f} |")
        lines.extend(["", "38 项测试通过（原 33 项 + 换流 3 项 + SPICE 导出 2 项），24 份波形 CSV 回读通过。",
            "独立 RK4 检查无钳位区间；电源能量、二极管耗散与 L/C 储能差独立计算，并以端点功率梯形积分复核。",
            "`leg_turnons.csv` 保留每个待开通器件的电流初态、开通时电流、节点电压、VDS、首次到轨时间及钳位状态。",
            "模型内完成标准：开通时 VDS ≤ 1 µV（数值零容差，允许体二极管正向钳位时负 VDS）。",
            "实际器件的非线性电容、反向恢复、温度、寄生与栅极驱动尚未在本阶段建模；损耗预算另分阶段。", ""])
        (output / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"PASS: {len(summaries)} cases, {len(all_events)} leg turn-ons, 38 tests")
        for s in summaries:
            print(f"{s['case']} {s['method']} {s['deadtime_s']*1e9:g} ns: complete={s['zvs_in_model']}/8, "
                  f"favorable but incomplete={s['favorable_but_incomplete']}")
    except Exception:
        (output / "failure.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=root / "results_eps" / "comparisons.csv")
    parser.add_argument("--output", type=Path, default=root / "results_deadtime")
    args = parser.parse_args()
    run(args.source, args.output)
