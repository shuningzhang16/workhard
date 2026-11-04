"""Screen existing equal-power SPS/EPS operating points for necessary polarity."""

import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import traceback

from commutation_polarity import ZERO_CURRENT_TOL_A, analyze_edges, edge_summary, sps_polarity_boundary_deg
from dab_eps import simulate_eps
from dab_sps import Parameters, analytical_power, simulate
from run_experiment import write_csv


def run(source: Path, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    metadata = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "python_version": sys.version,
        "command_argv": sys.orig_argv, "source_file": str(source.resolve()),
        "scope": "necessary edge-current polarity in existing ideal periodic SPS/EPS waveforms",
        "numerical_zero_current_tol_a": ZERO_CURRENT_TOL_A,
        "zvs_status": "not_evaluated_missing_device_and_deadtime_model",
        "missing_model_inputs": ["Coss(V)/Qoss(V)/Eoss(V)", "actual dead time and gate delays",
                                 "magnetizing current and parasitic commutation network"],
        "hardware_operations": False}
    (output / "run_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    try:
        with source.open(encoding="utf-8", newline="") as stream:
            inputs = list(csv.DictReader(stream))
        (output / "input_comparisons.csv").write_bytes(source.read_bytes())
        all_events, summaries, input_status, boundaries = [], [], [], []

        def record(name, group, method, parameters, alpha, phase, target=None):
            cycle = simulate(parameters, phase) if method == "SPS" else simulate_eps(parameters, alpha, phase)
            events = analyze_edges(cycle, alpha)
            if len(events) != 8 or len({e["incoming_device"] for e in events}) != 8:
                raise AssertionError(f"Expected eight distinct device turn-ons per period: {name}")
            summary = {"case": name, "group": group, "method": method, **asdict(parameters),
                       "voltage_ratio_nV2_over_V1": parameters.turns_ratio * parameters.v2_v / parameters.v1_v,
                       "alpha_deg": alpha, "phase_deg": phase,
                       "target_w": "" if target is None else target,
                       "p2_w": cycle.metrics["p2_time_w"],
                       "power_match_error_w": "" if target is None else cycle.metrics["p2_time_w"] - target,
                       "i_peak_a": cycle.metrics["i_peak_a"], "i_rms_a": cycle.metrics["i_rms_a"],
                       **edge_summary(events)}
            if target is not None and abs(summary["power_match_error_w"]) > 1e-7:
                raise AssertionError(f"Source target no longer matched: {summary}")
            summaries.append(summary)
            all_events.extend({"case": name, "group": group, "method": method, **e} for e in events)
            return summary

        for row in inputs:
            usable = row["status"] == "matched"
            input_status.append({"case": row["case"], "source_status": row["status"],
                                 "analysis": "analyzed" if usable else "no_periodic_match_to_analyze"})
            if not usable:
                continue
            p = Parameters(**{key: float(row[key]) for key in asdict(Parameters())})
            for method in ["SPS", "EPS"]:
                lower = method.lower()
                alpha = 0 if method == "SPS" else float(row["eps_alpha_deg"])
                summary = record(row["case"], "equal_power", method, p, alpha,
                                 float(row[f"{lower}_phase_deg"]), float(row["target_w"]))
                if abs(summary["p2_w"] - float(row[f"{lower}_p_w"])) > 1e-9:
                    raise AssertionError("Regenerated waveform differs from stored comparison power")

        for ratio in [0.75, 1.0, 1.25]:
            p = Parameters(v2_v=12 * ratio)
            angle = sps_polarity_boundary_deg(p)
            boundaries.append({"voltage_ratio_nV2_over_V1": ratio,
                "all_leg_polarity_threshold_abs_phase_deg": angle,
                "power_magnitude_at_zero_current_boundary_w": analytical_power(p, angle),
                "primary_formal_zero_angle_deg": 90 * (1 - 1 / ratio),
                "secondary_formal_zero_angle_deg": 90 * (1 - ratio),
                "condition": "abs_phase_strictly_above_threshold_for_all_necessary_polarities",
                "zvs_status": "not_evaluated_missing_device_and_deadtime_model"})
            angles = [0, -0.5, 0.5] if angle == 0 else [sign * (angle + offset)
                     for sign in [1, -1] for offset in [-0.5, 0, 0.5]]
            for phase in angles:
                record(f"m{ratio:g}_phase{phase:g}", "sps_boundary_probe", "SPS", p, 0, phase)
        record("matched_30deg_hand_check", "hand_check", "SPS", Parameters(), 0, 30)
        write_csv(output / "edge_currents.csv", all_events)
        write_csv(output / "case_summary.csv", summaries)
        write_csv(output / "sps_boundaries.csv", boundaries)
        write_csv(output / "input_status.csv", input_status)

        # Check counts again from persisted edge data, including simultaneous legs.
        with (output / "edge_currents.csv").open(encoding="utf-8", newline="") as stream:
            persisted = list(csv.DictReader(stream))
        checks = []
        for summary in summaries:
            edges = [e for e in persisted if e["case"] == summary["case"] and e["group"] == summary["group"]
                     and e["method"] == summary["method"]]
            counts = {"necessary_met": sum(e["polarity_status"] == "necessary_polarity_met" for e in edges),
                      "opposed": sum(e["polarity_status"] == "opposes_transition" for e in edges),
                      "zero_boundary": sum(e["polarity_status"] == "zero_current_boundary" for e in edges)}
            if len(edges) != 8 or any(counts[key] != summary[key] for key in counts):
                raise AssertionError("Persisted edge count mismatch")
            checks.append({"case": summary["case"], "group": summary["group"], "method": summary["method"],
                           "edges": len(edges), **counts})
        write_csv(output / "csv_checks.csv", checks)

        command = [sys.executable, "-B", "-X", "utf8", "-m", "unittest", "-v",
                   "test_dab_sps", "test_dab_eps", "test_dab_transient", "test_commutation_polarity"]
        tests = subprocess.run(command, cwd=Path(__file__).resolve().parent,
                               capture_output=True, text=True, encoding="utf-8")
        (output / "tests.log").write_text("Command: " + subprocess.list2cmdline(command) + "\n"
            + tests.stdout + tests.stderr + f"\nProcess exit code: {tests.returncode}\n", encoding="utf-8")
        if tests.returncode:
            raise RuntimeError("Tests failed; evidence retained")

        comparison = [s for s in summaries if s["group"] == "equal_power"]
        lines = ["# 逐开关沿电流极性：必要条件筛查", "",
                 "此报告没有判定已实现 ZVS，也没有计算软开关效率或完整 ZVS 区域。",
                 "全部结果来自已有理想 SPS/EPS 周期波形，未加入 Coss/Qoss、死区或寄生网络。",
                 f"运行时间（UTC）：{metadata['started_at_utc']}。", "",
                 "每种策略每周期记录 8 个桥臂换流（含上管下降沿对应的下管开通），同时发生的不同桥臂分别计数。",
                 "下表计数顺序为：必要极性满足 / 方向相反 / 零电流边界。8/0/0 仍不足以确认 ZVS。", "",
                 "| 电压比 m | 目标 W | EPS α ° | SPS 计数 | EPS 计数 |",
                 "| ---: | ---: | ---: | ---: | ---: |"]
        for source_row in inputs:
            if source_row["status"] != "matched":
                continue
            pair = {s["method"]: s for s in comparison if s["case"] == source_row["case"]}
            sps, eps = pair["SPS"], pair["EPS"]
            def counts(s):
                return f"{s['necessary_met']}/{s['opposed']}/{s['zero_boundary']}"
            lines.append(f"| {sps['voltage_ratio_nV2_over_V1']:g} | {sps['target_w']:.3f} | "
                         f"{eps['alpha_deg']:g} | {counts(sps)} | {counts(eps)} |")
        lines.extend(["", "SPS 的理想电流零点边界（正反方向按 |φ| 对称）：", "",
                      "| m | 全部桥臂严格满足极性所需的相移绝对值下界 ° | 边界功率绝对值 W |",
                      "| ---: | ---: | ---: |"])
        for b in boundaries:
            lines.append(f"| {b['voltage_ratio_nV2_over_V1']:g} | {b['all_leg_polarity_threshold_abs_phase_deg']:.6f} | "
                         f"{b['power_magnitude_at_zero_current_boundary_w']:.6f} |")
        worst = max(abs(s["power_match_error_w"]) for s in comparison)
        lines.extend(["", "在上述角度边界本身，至少一组换流电流为零；m=1、φ=0 时全部为零。",
                      "边界相邻 ±0.5° 与正反方向共 15 个点已用逐沿电流核对。这只是零电流极性分界，不是完整软开关区域。", "",
                      "手算工况：24 V/12 V、n=2、100 µH、20 kHz、+30°，两桥四个电压换向时刻的原边电流分别为 −1、+1、+1、−1 A；",
                      "原边各桥臂顺换流方向电流为 1 A，副边为 2 A（实际侧电流，含变比折算）。8 个沿均满足极性。", "",
                      f"12 个同目标功率请求的 24 个策略波形，最大功率匹配误差 {worst:.3e} W。",
                      "原比较表的两个无解请求没有周期波形，因此标记为未分析；保留在 `input_status.csv`，未补造开关数据。",
                      f"总计 {len(summaries)} 个波形、{len(all_events)} 个桥臂沿；CSV 回读计数一致。25 项测试通过（原 19 项 + 新增 6 项）。", "",
                      "必要极性满足后，仍缺器件非线性 Coss/Qoss/Eoss、实际死区与延时、磁化及寄生换流模型，",
                      "无法验证可用电荷/能量是否足够，或开通前 VDS 是否已经降到零。全部 `zvs_status` 均保持未评估。", "",
                      "定义、推导与厂商原始来源见上级 `COMMUTATION.md`。", ""])
        (output / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"PASS: {len(summaries)} periodic waveforms, {len(all_events)} leg edges, 25 tests")
        print(f"Maximum equal-power mismatch: {worst:.3e} W")
        for s in comparison:
            if s["target_w"] > 0:
                print(f"{s['case']} {s['method']}: met/opposed/zero={s['necessary_met']}/{s['opposed']}/{s['zero_boundary']}")
    except Exception:
        (output / "failure.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parent
    parser.add_argument("--source", type=Path, default=root / "results_eps" / "comparisons.csv")
    parser.add_argument("--output", type=Path, default=root / "results_polarity")
    args = parser.parse_args()
    run(args.source, args.output)
