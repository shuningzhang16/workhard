"""Finite continuous-period SPS/EPS physics experiment, with source errors."""

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

from dab_continuous import simulate_continuous
from dab_deadtime import Device, LEGS
from run_deadtime import load_cases
from run_experiment import write_csv


def verify_rows(path, parameters):
    with path.open(encoding="utf-8", newline="") as stream:
        raw = list(csv.DictReader(stream))
    rows = [{k: v if k == "kind" else float(v) for k, v in row.items()} for row in raw]
    current_gap = max(abs(a["i1_a"]-b["i0_a"]) for a, b in zip(rows, rows[1:]))
    time_gap = max(abs(a["t1_s"]-b["t0_s"]) for a, b in zip(rows, rows[1:]))
    node_gap = max(abs(a[f"v1_{leg}_v"]-b[f"v0_{leg}_v"]) for a, b in zip(rows, rows[1:]) for leg in LEGS)
    buses = (parameters.v1_v, parameters.v1_v, parameters.v2_v, parameters.v2_v)
    rail_violation = max(0.0, *(max(-Device().diode_drop_v-r[f"v{end}_{leg}_v"],
        r[f"v{end}_{leg}_v"]-bus-Device().diode_drop_v)
        for r in rows for leg, bus in zip(LEGS, buses) for end in (0, 1)))
    residual = math.fsum(r["source1_energy_j"] + r["source2_energy_j"] - r["resistor_energy_j"] -
                        r["diode_energy_j"] - r["turnon_redistribution_energy_j"] for r in rows) - (
                        rows[-1]["stored_energy1_j"]-rows[0]["stored_energy0_j"])
    result = {"file": path.name, "rows": len(rows), "current_gap_a": current_gap,
              "time_gap_s": time_gap, "node_gap_v": node_gap, "total_energy_residual_j": residual,
              "max_diode_rail_violation_v": rail_violation,
              "max_segment_energy_residual_j": max(abs(r["energy_residual_j"]) for r in rows),
              "max_cumulative_energy_residual_j": max(abs(r["cumulative_energy_residual_j"]) for r in rows)}
    if current_gap or time_gap or node_gap or rail_violation > 1e-8 or abs(residual) > 1e-10 or result["max_segment_energy_residual_j"] > 1e-12 or result["max_cumulative_energy_residual_j"] > 1e-10:
        raise AssertionError(f"Continuous waveform physical check failed: {result}")
    return result


def run(source, output):
    output.mkdir(parents=True, exist_ok=True)
    metadata = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "python_version": sys.version,
        "command_argv": sys.orig_argv, "period_count": 100, "initial_current_a": 0,
        "resistance_ohm": 0.5, "device": asdict(Device()), "deadtime_s": [150e-9, 500e-9],
        "time_origin": "first scheduled turn-off edge of each fixed modulation pattern",
        "advancement": "exact RL active intervals; damped LC modes with diode events, <=pi/4 resonant angle per step",
        "turnon": "continuous iL; instantaneous rail connection with source charge and full pair-capacitor redistribution loss",
        "target_matching": "source ideal phases retained; actual target and SPS/EPS mismatch reported, not rematched",
        "scope": "open-loop physical simulation; existing sampled-protection and PI simulations remain separate",
        "hardware_operations": False}
    (output / "run_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    (output / "input_comparisons.csv").write_bytes(source.read_bytes())
    summaries, checks = [], []
    try:
        for name, method, alpha, cycle in load_cases(source):
            for deadtime in metadata["deadtime_s"]:
                key = f"{name}_{method}_{round(deadtime*1e9)}ns"
                result = simulate_continuous(cycle.parameters, alpha, cycle.phase_deg, deadtime_s=deadtime)
                path = output / f"{key}_waveform.csv"
                write_csv(path, result.rows)
                write_csv(output / f"{key}_periods.csv", result.periods)
                write_csv(output / f"{key}_turnons.csv", result.turnons)
                tail = result.periods[-10:]
                means = {field: math.fsum(r[field] for r in tail)/len(tail) for field in (
                    "p1_input_w", "p2_output_w", "resistor_power_w", "diode_power_w",
                    "turnon_redistribution_power_w", "i_rms_a", "i_mean_a")}
                current_error = max(abs(r["periodic_current_difference_a"]) for r in tail)
                power_change = max(abs(a["p2_output_w"]-b["p2_output_w"]) for a, b in zip(tail, tail[1:]))
                summary = {"case": name, "method": method, "deadtime_s": deadtime,
                    "v2_v": cycle.parameters.v2_v, "alpha_deg": alpha, "phase_deg": cycle.phase_deg,
                    "source_ideal_target_w": cycle.metrics["p2_time_w"], **means,
                    "actual_target_error_w": means["p2_output_w"]-cycle.metrics["p2_time_w"],
                    "max_tail_periodic_current_error_a": current_error, "max_tail_power_change_w": power_change,
                    "period_converged": int(current_error < 1e-8 and power_change < 1e-6),
                    "last_period_zvs_in_model": result.periods[-1]["zvs_in_model"],
                    "last_period_i_peak_a": result.periods[-1]["i_peak_a"],
                    "whole_run_i_peak_a": max(r["i_peak_a"] for r in result.rows),
                    "last_period_segments": result.periods[-1]["integration_segments"],
                    "power_balance_residual_w": means["p1_input_w"]-means["p2_output_w"]-means["resistor_power_w"]-
                        means["diode_power_w"]-means["turnon_redistribution_power_w"]}
                summaries.append(summary)
                write_csv(output / "summary.csv", summaries)
                checks.append(verify_rows(path, cycle.parameters))
                write_csv(output / "csv_checks.csv", checks)
        pairs = []
        for s in summaries:
            if s["method"] == "SPS":
                e = next(r for r in summaries if r["case"] == s["case"] and r["deadtime_s"] == s["deadtime_s"] and r["method"] == "EPS")
                pairs.append({"case": s["case"], "deadtime_s": s["deadtime_s"], "source_target_w": s["source_ideal_target_w"],
                              "sps_actual_p2_w": s["p2_output_w"], "eps_actual_p2_w": e["p2_output_w"],
                              "eps_minus_sps_power_w": e["p2_output_w"]-s["p2_output_w"],
                              "interpretation": "not rematched; do not treat loss comparison as equal actual power"})
        write_csv(output / "actual_power_mismatch.csv", pairs)
        command = [sys.executable, "-B", "-X", "utf8", "-m", "unittest", "-v",
            "test_dab_sps", "test_dab_eps", "test_dab_transient", "test_commutation_polarity",
            "test_dab_power_loop", "test_power_points", "test_dab_deadtime", "test_deadtime_spice", "test_dab_continuous"]
        tests = subprocess.run(command, cwd=Path(__file__).resolve().parent, capture_output=True, text=True, encoding="utf-8")
        (output / "tests.log").write_text("Command: " + subprocess.list2cmdline(command) + "\n" + tests.stdout + tests.stderr +
                                          f"\nExit code: {tests.returncode}\n", encoding="utf-8")
        if tests.returncode:
            raise RuntimeError("Continuous model tests failed; evidence retained")
        lines = ["# 连续整周期 RLC 换流结果", "", "16 个固定角度工况，各连续运行 100 周期，初始电流仅在运行起点设为 0。",
            "电流跨死区、开通、非死区与周期边界连续；非死区解析 RL，死区解析阻尼 LC 并定位二极管/过零事件。",
            "R=0.5 Ω；线性电容和固定二极管压降假设沿用上阶段。没有整周期统一微步长。",
            "原理想同功率角度保持不变，实际功率误差如下；未宣称两种方法在含损耗模型中仍同功率。", "",
            "| 原目标 W | 方法 | 死区 ns | 实际 P2 W | 目标误差 W | IRMS A | 模型 ZVS / 8 | R / 二极管 / 开通重分配 W | 周期收敛 |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for s in summaries:
            lines.append(f"| {s['source_ideal_target_w']:.3f} | {s['method']} | {s['deadtime_s']*1e9:g} | "
                f"{s['p2_output_w']:.6f} | {s['actual_target_error_w']:.6f} | {s['i_rms_a']:.6f} | {s['last_period_zvs_in_model']} | "
                f"{s['resistor_power_w']:.6f} / {s['diode_power_w']:.6f} / {s['turnon_redistribution_power_w']:.6f} | {s['period_converged']} |")
        lines.extend(["", "功率和 IRMS 取末 10 周期均值；ZVS 计数取最后一个周期，仍仅指教学器件模型内节点电压条件。",
            "周期收敛要求末 10 周期起止电流差 <1e−8 A、相邻周期 P2 变化 <1e−6 W。未用均值扣除或边沿理想电流覆盖实际状态。",
            "开通重分配损耗使用 C×(节点开通前电压−目标轨电压)²，包含两只电容；单管残余 ½CV² 仅作诊断，不再重复相加。",
            "44 项测试通过（原 38 项加本步 6 项），16 份全程波形 CSV 回读通过，另含节点二极管边界检查。",
            "测试包括独立 RK4 阻尼换流与 R 损耗、全事件连续性和开通能量、不同初态收敛、C/死区趋零时回到原 RL 结果，以及与细分死区步长的对照。",
            "当前预算仅含所建模的串联 R、死区二极管与电容开通重分配；尚无器件导通/栅驱/重叠/反向恢复和磁芯等完整损耗估算。",
            "不据此报告硬件效率。源角度下的 SPS/EPS 实际功率差独立保存在 actual_power_mismatch.csv。", ""])
        (output / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"PASS: {len(summaries)} continuous cases, 44 tests, {len(checks)} full waveform checks")
        for s in summaries:
            print(f"{s['case']} {s['method']} {s['deadtime_s']*1e9:g} ns: P2={s['p2_output_w']:.6f} W, "
                  f"target error={s['actual_target_error_w']:.6f} W, ZVS={s['last_period_zvs_in_model']}/8, "
                  f"converged={s['period_converged']}, segments={s['last_period_segments']}")
    except Exception:
        (output / "failure.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=root / "results_eps" / "comparisons.csv")
    parser.add_argument("--output", type=Path, default=root / "results_continuous")
    args = parser.parse_args()
    run(args.source, args.output)
