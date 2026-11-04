"""Bounded equal-power SPS/EPS comparison using standard-library simulation."""

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

from dab_sps import Parameters, analytical_power, simulate
from dab_eps import ALPHA_GRID_DEG, POWER_MATCH_TOL_W, match_power, search_eps, timing_rows
from run_experiment import write_csv


def run(output: Path):
    output.mkdir(parents=True, exist_ok=True)
    waves = output / "waveforms"
    waves.mkdir(exist_ok=True)
    metadata = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version,
        "command_argv": sys.orig_argv,
        "model": "independent ideal low-voltage EPS; primary bridge only",
        "parameters_default": asdict(Parameters()),
        "voltage_ratios_nV2_over_V1": [0.75, 1.0, 1.25],
        "target_fractions_of_sps_ideal_pmax": [0.1, 0.5],
        "unreachable_targets_at_ratio_1_w": [-39.6, 39.6],
        "alpha_grid_deg": list(ALPHA_GRID_DEG),
        "external_phase_branch_deg": [-90, 90],
        "bisection_iterations": 40,
        "power_match_tolerance_w": POWER_MATCH_TOL_W,
        "objective": "minimum RMS among feasible grid candidates; peak then alpha break ties",
        "result_type": "offline_simulation_not_hardware_measurement",
    }
    (output / "run_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    try:
        comparisons, all_candidates, wave_records = [], [], []
        cases = [(ratio, fraction, direction) for ratio in [0.75, 1.0, 1.25]
                 for fraction in [0.1, 0.5] for direction in [1, -1]]
        cases += [(1.0, 1.1, direction) for direction in [1, -1]]
        for ratio, fraction, direction in cases:
            p = Parameters(v2_v=12 * ratio)
            pmax = analytical_power(p, 90)
            target = direction * fraction * pmax
            name = f"m{ratio:g}_load{fraction:g}_{'forward' if direction > 0 else 'reverse'}"
            best, candidates = search_eps(p, target)
            all_candidates.extend({"case": name, **asdict(p), **r} for r in candidates)
            sps_match, _ = match_power(p, target, 0)
            row = {"case": name, **asdict(p), "voltage_ratio_nV2_over_V1": ratio,
                   "sps_ideal_pmax_w": pmax, "target_fraction": fraction,
                   "target_w": target, "status": "matched" if best else "no_match_in_branch",
                   "feasible_candidates": sum(r["status"] == "matched" for r in candidates),
                   **{key: "" for key in ["sps_phase_deg", "eps_alpha_deg", "eps_internal_leg_shift_deg",
                       "eps_phase_deg", "sps_p_w", "eps_p_w", "sps_error_w", "eps_error_w",
                       "sps_i_peak_a", "eps_i_peak_a", "sps_i_rms_a", "eps_i_rms_a",
                       "peak_reduction_percent", "rms_reduction_percent"]}}
            if best:
                if sps_match is None:
                    raise AssertionError("Comparison requires a matched SPS solution")
                alpha, eps = best
                sps = simulate(p, sps_match.phase_deg)
                sm, em = sps.metrics, eps.metrics
                row.update(sps_phase_deg=sps.phase_deg, eps_alpha_deg=alpha,
                           eps_internal_leg_shift_deg=180 - alpha, eps_phase_deg=eps.phase_deg,
                           sps_p_w=sm["p2_time_w"], eps_p_w=em["p2_time_w"],
                           sps_error_w=sm["p2_time_w"] - target, eps_error_w=em["p2_time_w"] - target,
                           sps_i_peak_a=sm["i_peak_a"], eps_i_peak_a=em["i_peak_a"],
                           sps_i_rms_a=sm["i_rms_a"], eps_i_rms_a=em["i_rms_a"],
                           peak_reduction_percent=100 * (1 - em["i_peak_a"] / sm["i_peak_a"]),
                           rms_reduction_percent=100 * (1 - em["i_rms_a"] / sm["i_rms_a"]))
                for method, cycle, zero_angle in [("sps", sps, 0), ("eps", eps, alpha)]:
                    path = waves / f"{name}_{method}.csv"
                    write_csv(path, timing_rows(cycle, zero_angle))
                    wave_records.append((path, cycle))
            comparisons.append(row)
        write_csv(output / "comparisons.csv", comparisons)
        write_csv(output / "candidates.csv", all_candidates)

        # Validate actual persisted timing data, not just the in-memory results.
        csv_checks = []
        for path, cycle in wave_records:
            p = cycle.parameters
            with path.open(encoding="utf-8", newline="") as stream:
                rows = [{k: float(v) for k, v in r.items()} for r in csv.DictReader(stream)]
            duration = rows[-1]["t1_s"] - rows[0]["t0_s"]
            for previous, following in zip(rows, rows[1:]):
                if abs(previous["t1_s"] - following["t0_s"]) > 1e-14 or abs(previous["iL1_a"] - following["iL0_a"]) > 1e-9:
                    raise AssertionError(f"Discontinuous CSV: {path.name}")
            for r in rows:
                if r["v1_v"] != p.v1_v * (r["q1a_high"] - r["q1b_high"]):
                    raise AssertionError(f"Primary leg/voltage mismatch: {path.name}")
                if r["v2_prime_v"] != p.turns_ratio * p.v2_v * (r["q2a_high"] - r["q2b_high"]):
                    raise AssertionError(f"Secondary leg/voltage mismatch: {path.name}")
                residual = r["iL1_a"] - r["iL0_a"] - r["vL_v"] / p.inductance_h * (r["t1_s"] - r["t0_s"])
                if abs(residual) > 1e-9:
                    raise AssertionError(f"Inductor equation mismatch: {path.name}")
            power = math.fsum((r["t1_s"] - r["t0_s"]) * r["v2_prime_v"] * (r["iL0_a"] + r["iL1_a"]) / 2 for r in rows) / duration
            rms = math.sqrt(math.fsum((r["t1_s"] - r["t0_s"]) * (r["iL0_a"]**2 + r["iL0_a"] * r["iL1_a"] + r["iL1_a"]**2) / 3 for r in rows) / duration)
            peak = max(abs(r[key]) for r in rows for key in ["iL0_a", "iL1_a"])
            check = {"file": path.name, "rows": len(rows),
                     "power_error_w": power - cycle.metrics["p2_time_w"],
                     "rms_error_a": rms - cycle.metrics["i_rms_a"],
                     "peak_error_a": peak - cycle.metrics["i_peak_a"]}
            csv_checks.append(check)
            if any(abs(check[key]) > 1e-9 for key in ["power_error_w", "rms_error_a", "peak_error_a"]):
                raise AssertionError(f"CSV round-trip mismatch: {check}")
        write_csv(output / "csv_checks.csv", csv_checks)

        for r in all_candidates:
            if r["status"] == "matched":
                if abs(r["power_match_error_w"]) > POWER_MATCH_TOL_W:
                    raise AssertionError(f"Power mismatch: {r}")
                for key in ["power_balance_w", "i_mean_a", "periodic_error_a"]:
                    if abs(r[key]) > 1e-9:
                        raise AssertionError(f"Physical invariant failed: {key}: {r}")

        command = [sys.executable, "-B", "-m", "unittest", "-v", "test_dab_sps", "test_dab_eps"]
        tests = subprocess.run(command, cwd=Path(__file__).resolve().parent,
                               capture_output=True, text=True, encoding="utf-8")
        (output / "tests.log").write_text("Command: " + subprocess.list2cmdline(command)
            + "\n" + tests.stdout + tests.stderr + f"\nProcess exit code: {tests.returncode}\n", encoding="utf-8")
        if tests.returncode:
            raise RuntimeError("Tests failed; saved CSV and tests.log remain available")

        matched = [r for r in comparisons if r["status"] == "matched"]
        worst = max(abs(r[key]) for r in matched for key in ["sps_error_w", "eps_error_w"])
        feasible = [r for r in all_candidates if r["status"] == "matched"]
        lines = ["# 等目标功率 SPS / EPS 比较", "",
                 "独立低压理想模型，离线仿真，未实测。EPS 只调整第一侧桥。", "",
                 f"运行时间（UTC）：{metadata['started_at_utc']}。",
                 "参数同前一步；电压比 m=nV2/V1。轻载/中载指目标为各电压比 SPS 理想最大功率的 10%/50%，不是硬件额定值。", "",
                 "| m | 目标 W | α ° | φ ° | SPS / EPS 峰值 A | SPS / EPS RMS A | RMS 降低 % |",
                 "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for r in matched:
            lines.append(f"| {r['voltage_ratio_nV2_over_V1']:g} | {r['target_w']:.3f} | {r['eps_alpha_deg']} | {r['eps_phase_deg']:.6f} | "
                         f"{r['sps_i_peak_a']:.6f} / {r['eps_i_peak_a']:.6f} | "
                         f"{r['sps_i_rms_a']:.6f} / {r['eps_i_rms_a']:.6f} | {r['rms_reduction_percent']:.3f} |")
        lines.extend(["", "搜索 α=0:15:180°；每个 α 在 |φ|≤90° 的单调支路做 40 次二分。",
                      "目标是候选集内最小 RMS，峰值仅记录，不承诺同时最优；α=0 是 SPS 退化点。",
                      "α 定义为每个原边过零处的零电平角宽；实际两桥臂内部相移为 180°−α。", "",
                      f"最大 SPS/EPS 目标匹配绝对误差：{worst:.3e} W（要求 ≤{POWER_MATCH_TOL_W:g} W）。",
                      f"{len(all_candidates)} 个候选记录中，{len(feasible)} 个匹配成功，{len(all_candidates)-len(feasible)} 个在该支路无匹配。",
                      "m=1 的 ±39.6 W 请求均无解：超出本方案在所查范围的 36 W 上限；未伪造匹配或电流改善率。",
                      f"最大候选端口功率不平衡：{max(abs(r['power_balance_w']) for r in feasible):.3e} W。",
                      f"最大候选周期首尾误差：{max(abs(r['periodic_error_a']) for r in feasible):.3e} A。",
                      f"最大候选电流时间均值：{max(abs(r['i_mean_a']) for r in feasible):.3e} A。", "",
                      "12 项测试通过（含原 SPS 6 项），24 份含桥臂状态的原始波形 CSV 回读通过。",
                      "完整候选及无解记录见 `candidates.csv`，同功率比较见 `comparisons.csv`，实际测试见 `tests.log`。", "",
                      "搜索只覆盖固定的第一侧 EPS 和 13 个内部设置，不证明全局最优。",
                      "此步未估计损耗、效率、ZVS，也未实现 DPS/TPS、闭环或硬件驱动。", ""])
        (output / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"PASS: {len(matched)} equal-power cases; 2 unreachable cases; {len(all_candidates)} candidates; 12 tests; 24 CSV checks")
        print(f"Maximum target-power error: {worst:.3e} W")
        for r in matched:
            if r["target_w"] > 0:
                print(f"m={r['voltage_ratio_nV2_over_V1']:g} P={r['target_w']:.3f} W alpha={r['eps_alpha_deg']} deg "
                      f"RMS {r['sps_i_rms_a']:.6f}->{r['eps_i_rms_a']:.6f} A ({r['rms_reduction_percent']:.3f}%)")
    except Exception:
        (output / "failure.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "results_eps")
    run(parser.parse_args().output)
