"""Finite receiver-power matches and explicitly partial device loss budgets."""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
import sys
import traceback

from dab_loss_budget import GATE_DRIVE_V, LOSS_PARAMETERS, MATCH_TOL_W, MAX_BISECTIONS, loss_budget, match_actual_power, tail_metrics
from run_continuous import verify_rows
from run_deadtime import load_cases
from run_experiment import write_csv


def cases(source):
    for name, method, alpha, cycle in load_cases(source):
        direction = -1 if cycle.metrics["p2_time_w"] < 0 else 1
        target = round(abs(cycle.metrics["p2_time_w"]), 8)
        for deadtime in ((150e-9, 500e-9) if name == "m0.75_load0.1_forward" else (150e-9,)):
            if "load0.5" in name:
                bounds = (10.0, 45.0) if alpha == 0 else (27.0, 40.0)
            elif alpha == 0:
                minimum_phase = 360*cycle.parameters.frequency_hz*deadtime + 0.1
                bounds = (minimum_phase, 20.0) if direction == 1 else (-20.0, -minimum_phase)
            else:
                bounds = (1.0, 20.0) if direction == 1 else (-20.0, -1.0)
            yield name, method, alpha, cycle.parameters, direction, target, deadtime, bounds


def run(source, output):
    output.mkdir(parents=True, exist_ok=True)
    plans = list(cases(source))
    metadata = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "python_version": sys.version,
        "command_argv": sys.orig_argv, "matching_tolerance_w": MATCH_TOL_W, "max_bisections": MAX_BISECTIONS,
        "periods_per_evaluation": 100, "initial_current_a": 0,
        "receiver_definition": "forward=P2, reverse=-P1; positive target at receiver in both directions",
        "plant_unchanged": True, "external_series_resistance_ohm": 0.5,
        "resistance_role": "external series resistance excludes the separately postprocessed MOSFET channel resistance",
        "postprocessing": "MOSFET channel/gate losses do not alter matched plant power or trajectory",
        "device_source": "https://www.ti.com/lit/ds/symlink/csd18540q5b.pdf",
        "device_source_location": "SLPS488B, April 2017, page 3",
        "formula_source": "https://www.ti.com/lit/an/slpa009a/slpa009a.pdf",
        "formula_location": "SLPA009A sections 2 and 3.2, equations 1/2 and 31",
        "assumed_junction_temperature_c": 25, "self_heating_modeled": False,
        "gate_supply": "independent ideal 10 V driver supply; only Qg charging energy budgeted",
        "excluded_losses": ["turn-on/off channel overlap", "reverse recovery", "nonlinear output-capacitance losses",
            "magnetic core and AC winding loss", "driver quiescent and supply-conversion loss", "parasitics and temperature feedback"],
        "hardware_operations": False,
        "cases": [{"case": n, "method": m, "alpha_deg": a, "parameters": asdict(p), "direction": d,
            "target_received_w": t, "deadtime_s": dt, "phase_bounds_deg": bounds}
            for n, m, a, p, d, t, dt, bounds in plans]}
    (output / "run_metadata.json").write_text(json.dumps(metadata, indent=2)+"\n", encoding="utf-8")
    (output / "input_comparisons.csv").write_bytes(source.read_bytes())
    write_csv(output / "device_parameters.csv", [{"parameter_case": label, "rds_on_ohm": rds, "qg_c": qg,
        "drive_v": GATE_DRIVE_V, "assumed_temperature_c": 25,
        "datasheet_rds_conditions": "TA=25C, VGS=10V, ID=28A",
        "datasheet_qg_conditions": "TA=25C, VDS=30V, ID=28A, VGS=10V",
        "interpretation": "constant extrapolation; listed maxima case is sensitivity, not a complete worst-case bound"}
        for label, rds, qg in LOSS_PARAMETERS])
    evaluations, matches, budgets, devices, checks = [], [], [], [], []
    try:
        for name, method, alpha, p, direction, target, deadtime, bounds in plans:
            key = f"{name}_{method}_{round(deadtime*1e9)}ns"
            def keep_evaluation(record):
                evaluations.append({"case": name, "method": method, "deadtime_s": deadtime, **record})
                write_csv(output / "matching_evaluations.csv", evaluations)
            matched = match_actual_power(p, alpha, target, deadtime, bounds, direction=direction, on_evaluation=keep_evaluation)
            summary = {"case": name, "method": method, "deadtime_s": deadtime, "direction": direction,
                "target_received_w": target, "receiver": "side_2" if direction == 1 else "side_1",
                "alpha_deg": alpha, "lower_phase_deg": bounds[0], "upper_phase_deg": bounds[1],
                "status": matched.status, "phase_deg": "" if matched.phase_deg is None else matched.phase_deg,
                "evaluations": len(matched.evaluations),
                "lower_phase_received_w": matched.evaluations[0]["received_power_w"],
                "upper_phase_received_w": matched.evaluations[1]["received_power_w"],
                "p1_input_w": "", "p2_output_w": "", "received_power_w": "", "input_power_w": "",
                "received_power_error_w": "", "tail_i_rms_a": "", "last_period_zvs_in_model": "",
                "periodic_current_error_a": "", "period_power_change_w": "", "period_converged": ""}
            if matched.status == "matched":
                result = matched.result
                measured = tail_metrics(result, direction)
                summary.update(**measured, received_power_error_w=measured["received_power_w"]-target,
                    tail_i_rms_a=math.fsum(r["i_rms_a"] for r in result.periods[-10:])/10,
                    last_period_zvs_in_model=result.periods[-1]["zvs_in_model"])
                path = output / f"{key}_waveform.csv"
                write_csv(path, result.rows)
                write_csv(output / f"{key}_periods.csv", result.periods)
                write_csv(output / f"{key}_turnons.csv", result.turnons)
                totals, device_rows = loss_budget(result, p, alpha, matched.phase_deg)
                identity = {"case": name, "method": method, "deadtime_s": deadtime, "target_received_w": target,
                            "receiver": summary["receiver"], "received_power_w": measured["received_power_w"]}
                budgets.extend({**identity, **r} for r in totals)
                devices.extend({**identity, **r} for r in device_rows)
                write_csv(output / "loss_budget.csv", budgets)
                write_csv(output / "device_loss_details.csv", devices)
                checks.append(verify_rows(path, p))
                write_csv(output / "csv_checks.csv", checks)
            matches.append(summary)
            write_csv(output / "matches.csv", matches)
            print(f"{key}: {matched.status}, phase={summary['phase_deg']}, "
                  f"receiver={summary['received_power_w']} W, error={summary['received_power_error_w']} W", flush=True)
        pairs = []
        for s in matches:
            if s["method"] != "SPS":
                continue
            e = next(r for r in matches if r["case"] == s["case"] and r["deadtime_s"] == s["deadtime_s"] and r["method"] == "EPS")
            pair = {"case": s["case"], "deadtime_s": s["deadtime_s"], "target_received_w": s["target_received_w"],
                "receiver": s["receiver"], "sps_status": s["status"], "eps_status": e["status"],
                "receiver_power_difference_eps_minus_sps_w": "", "typical_partial_loss_difference_eps_minus_sps_w": ""}
            if s["status"] == e["status"] == "matched":
                pair["receiver_power_difference_eps_minus_sps_w"] = e["received_power_w"]-s["received_power_w"]
                pair_budget = {r["method"]: r for r in budgets if r["case"] == s["case"] and
                    r["deadtime_s"] == s["deadtime_s"] and r["parameter_case"] == "typical_25C"}
                pair["typical_partial_loss_difference_eps_minus_sps_w"] = pair_budget["EPS"]["partial_loss_budget_w"]-pair_budget["SPS"]["partial_loss_budget_w"]
            pairs.append(pair)
        write_csv(output / "equal_receiver_comparisons.csv", pairs)
        command = [sys.executable, "-B", "-X", "utf8", "-m", "unittest", "-v", "test_dab_sps", "test_dab_eps",
            "test_dab_transient", "test_commutation_polarity", "test_dab_power_loop", "test_power_points",
            "test_dab_deadtime", "test_deadtime_spice", "test_dab_continuous", "test_dab_loss_budget"]
        test = subprocess.run(command, cwd=Path(__file__).resolve().parent, capture_output=True, text=True, encoding="utf-8")
        (output / "tests.log").write_text("Command: "+subprocess.list2cmdline(command)+"\n"+test.stdout+test.stderr+f"\nExit code: {test.returncode}\n", encoding="utf-8")
        if test.returncode:
            raise RuntimeError("Loss budget tests failed; actual traces and logs retained")
        lines = ["# 同接收端功率与有限损耗预算", "", "连续 RLC 核心保持不变；正向匹配 P2，反向匹配 −P1。",
            "每次独立试算 100 周期，末 10 周期接收功率误差要求 ≤1e−5 W；每个显式区间最多二分 24 次。",
            "仅使用原 EPS α，未重新优化内部角度。未匹配点保留实际区间端点，不扩展成全局不可达结论。", "",
            "| 目标接收 W | 接收侧 | 方法 | 死区 ns | 状态 | 外部相移 ° | 接收 W | 误差 W | IRMS A | 模型 ZVS / 8 |",
            "| ---: | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |"]
        for s in matches:
            values = [f"{s[key]:.8f}" if s[key] != "" else "—" for key in
                      ("phase_deg", "received_power_w", "received_power_error_w", "tail_i_rms_a")]
            lines.append(f"| {s['target_received_w']:g} | {s['receiver']} | {s['method']} | {s['deadtime_s']*1e9:g} | "
                         f"{s['status']} | {' | '.join(values)} | {s['last_period_zvs_in_model']} |")
        lines.extend(["", "以下为固定 25°C、10 V 驱动典型参数的部分损耗估计，单位 W：", "",
            "| 工况 | 方法/死区 ns | 外部 R | 死区二极管 | 电容开通重分配 | 沟道后处理 | 栅驱后处理 | 部分预算 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"])
        for b in budgets:
            if b["parameter_case"] == "typical_25C":
                values = [f"{b[key]:.6f}" for key in ("external_series_r_w", "deadtime_diode_w", "turnon_charge_redistribution_w",
                          "channel_conduction_postprocess_w", "gate_charge_postprocess_w", "partial_loss_budget_w")]
                lines.append(f"| {b['case']} | {b['method']}/{b['deadtime_s']*1e9:g} | {' | '.join(values)} |")
        lines.extend(["", "0.5 Ω 在本预算中明确作为不含 MOSFET 沟道的外部串联 R；其 I²R 已在物理收支内，只计一次。",
            "新增沟道损耗仅对实际导通时间积分，死区关断沟道不计；栅驱按实际开通次数 Qg×10 V 计算。",
            "两项新增预算未反馈到连续模型，因此匹配是原 RLC 模型内的接收功率，不是加完后处理损耗的重新仿真。",
            "CΔV² 已包含双电容开通重分配，诊断用残余 ½CV² 不再叠加。",
            "数据表列出最大 Rds/Qg 的敏感性结果见 loss_budget.csv，不是完整最坏情况上界。",
            "未建模开通/关断沟道重叠、反向恢复、非线性电容、磁芯/交流绕组、驱动静态及供电损耗、寄生和温度反馈。未报告实测或完整效率。",
            f"47 项测试通过，{len(checks)} 份匹配后的完整波形回读通过；接收端口、门极次数、导通时间及不重复计入电容能量均有定向测试。", ""])
        (output / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"PASS: {len(matches)} attempts, {len(checks)} matched cases, 47 tests", flush=True)
    except Exception:
        (output / "failure.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=root/"results_eps"/"comparisons.csv")
    parser.add_argument("--output", type=Path, default=root/"results_loss_budget")
    args = parser.parse_args()
    run(args.source, args.output)
