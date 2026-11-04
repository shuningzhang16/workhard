"""Run and retain the SPS dynamic-phase and sampled-protection demonstration."""

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

from dab_transient import simulate_transient, teaching_scenarios
from run_experiment import write_csv


def summarize(name, run):
    rows = run.rows
    e1 = math.fsum(r["e1_j"] for r in rows)
    e2 = math.fsum(r["e2_j"] for r in rows)
    er = math.fsum(r["er_j"] for r in rows)
    delta = rows[-1]["inductor_e1_j"] - rows[0]["inductor_e0_j"]
    tail = run.periods[-10:]
    summary = {"scenario": name, "periods": len(run.periods), "duration_s": rows[-1]["t1_s"],
               "initial_current_a": rows[0]["i0_a"], "final_current_a": rows[-1]["i1_a"],
               "peak_current_a": max(abs(r[key]) for r in rows for key in ["i0_a", "i1_a"]),
               "max_sampled_current_a": max(abs(r["i_a"]) for r in run.samples),
               "tail_p1_w": math.fsum(r["p1_w"] for r in tail) / len(tail),
               "tail_p2_w": math.fsum(r["p2_w"] for r in tail) / len(tail),
               "tail_resistor_power_w": math.fsum(r["resistor_power_w"] for r in tail) / len(tail),
               "e1_j": e1, "e2_j": e2, "resistor_energy_j": er,
               "inductor_energy_change_j": delta, "total_energy_residual_j": e1 - e2 - er - delta,
               "max_segment_residual_j": max(abs(r["energy_residual_j"]) for r in rows),
               "trip_count": sum(e["event"] == "trip" for e in run.events),
               "clear_accepted_count": sum(e["event"] == "clear_accepted" for e in run.events),
               "trip_time_s": "", "threshold_crossing_time_s": "", "detection_delay_s": "",
               "trip_current_a": "", "stopped_initial_energy_j": "", "stopped_final_energy_j": "",
               "stopped_resistor_energy_j": "", "stopped_energy_residual_j": ""}
    trips = [e for e in run.events if e["event"] == "trip"]
    if trips:
        trip = trips[0]
        crossing = None
        p, resistance = run.settings.circuit, run.settings.series_resistance_ohm
        if trip["reason"] == "overcurrent":
            for row in rows:
                if row["t0_s"] >= trip["t_s"]:
                    break
                if abs(row["i0_a"]) <= run.settings.overcurrent_a < abs(row["i1_a"]):
                    limit = math.copysign(run.settings.overcurrent_a, row["i1_a"])
                    steady = (row["v1_v"] - row["v2_prime_v"]) / resistance
                    crossing = row["t0_s"] - p.inductance_h / resistance * math.log(
                        (limit - steady) / (row["i0_a"] - steady))
                    break
        elif name == "bus_input_recovery":
            crossing = 20.33 / p.frequency_hz
        end = next((e["t_s"] for e in run.events if e["event"] == "clear_accepted"
                    and e["t_s"] > trip["t_s"]), rows[-1]["t1_s"])
        stopped = [r for r in rows if trip["t_s"] <= r["t0_s"] < end and r["latched"]]
        stored0, stored1 = stopped[0]["inductor_e0_j"], stopped[-1]["inductor_e1_j"]
        stopped_er = math.fsum(r["er_j"] for r in stopped)
        summary.update(trip_time_s=trip["t_s"], trip_current_a=trip["i_a"],
                       threshold_crossing_time_s="" if crossing is None else crossing,
                       detection_delay_s="" if crossing is None else trip["t_s"] - crossing,
                       stopped_initial_energy_j=stored0, stopped_final_energy_j=stored1,
                       stopped_resistor_energy_j=stopped_er,
                       stopped_energy_residual_j=stored0 - stored1 - stopped_er)
    return summary


def validate_csv(path, settings):
    with path.open(encoding="utf-8", newline="") as stream:
        raw = list(csv.DictReader(stream))
    numeric = [{k: float(v) for k, v in r.items() if k != "reason"} for r in raw]
    continuity = max(abs(a["i1_a"] - b["i0_a"]) for a, b in zip(numeric, numeric[1:]))
    time_gap = max(abs(a["t1_s"] - b["t0_s"]) for a, b in zip(numeric, numeric[1:]))
    p, resistance = settings.circuit, settings.series_resistance_ohm
    endpoint_error = 0.0
    for r in numeric:
        steady = (r["v1_v"] - r["v2_prime_v"]) / resistance
        expected = steady + (r["i0_a"] - steady) * math.exp(-resistance * (r["t1_s"] - r["t0_s"]) / p.inductance_h)
        endpoint_error = max(endpoint_error, abs(r["i1_a"] - expected))
    net = math.fsum(r["e1_j"] - r["e2_j"] - r["er_j"] for r in numeric)
    delta = 0.5 * p.inductance_h * (numeric[-1]["i1_a"]**2 - numeric[0]["i0_a"]**2)
    result = {"file": path.name, "rows": len(numeric), "continuity_error_a": continuity,
              "time_gap_s": time_gap, "rl_endpoint_error_a": endpoint_error,
              "energy_residual_j": net - delta}
    if continuity != 0 or time_gap > 1e-14 or endpoint_error > 1e-10 or abs(net - delta) > 1e-10:
        raise AssertionError(f"Persisted CSV check failed: {result}")
    return result


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    metadata = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "python_version": sys.version,
                "command_argv": sys.orig_argv, "type": "independent_offline_RL_teaching_simulation",
                "solver": "event-aligned exact RL current and independent current integrals",
                "initialization": "initial current only at t=0; never subtract cycle mean",
                "protection": "sampled; zero both ideal bridge outputs while latched; R dissipates stored energy",
                "bus_sense_injection": "17 V from 20.33T to 25T in bus_input_recovery; physical V2 stays 12 V",
                "scenarios": {}, "hardware_operations": False}
    summaries, checks = [], []
    try:
        for name, settings, commands, options in teaching_scenarios():
            metadata["scenarios"][name] = {"settings": asdict(settings), "periods": len(commands),
                "initial_current_a": options.get("initial_current_a", 0),
                "clear_cycles": list(options.get("clear_cycles", ())),
                "commands_deg": commands}
            (output / "run_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
            result = simulate_transient(settings, commands, **options)
            wave_path = output / f"{name}_waveform.csv"
            write_csv(wave_path, result.rows)
            write_csv(output / f"{name}_periods.csv", result.periods)
            write_csv(output / f"{name}_samples.csv", result.samples)
            if result.events:
                write_csv(output / f"{name}_events.csv", result.events)
            else:
                (output / f"{name}_events.csv").write_text("t_s,event,reason,i_a,sensed_v2_v,request_deg\n", encoding="utf-8")
            summaries.append(summarize(name, result))
            checks.append(validate_csv(wave_path, settings))
        write_csv(output / "summary.csv", summaries)
        write_csv(output / "csv_checks.csv", checks)
        command = [sys.executable, "-B", "-X", "utf8", "-m", "unittest", "-v", "test_dab_sps", "test_dab_eps", "test_dab_transient"]
        tests = subprocess.run(command, cwd=Path(__file__).resolve().parent,
                               capture_output=True, text=True, encoding="utf-8")
        (output / "tests.log").write_text("Command: " + subprocess.list2cmdline(command) + "\n"
            + tests.stdout + tests.stderr + f"\nProcess exit code: {tests.returncode}\n", encoding="utf-8")
        if tests.returncode:
            raise RuntimeError("Tests failed; raw CSV and tests.log preserved")
        lines = ["# SPS 动态相移与采样保护结果", "",
                 "独立教学 RL 模型，离线仿真，未实测；未进行硬件操作。",
                 f"运行时间（UTC）：{metadata['started_at_utc']}。", "",
                 "固定母线 24 V / 12 V、n=2、L=100 µH、fs=20 kHz；新增教学假设 R=0.5 Ω。",
                 "20 次采样/周期（2.5 µs），相移限幅 ±60°，正常运行每周期最多变化 6°。",
                 "故障优先于限速，锁存后两桥立即置零并保留电感电流，显式清除后从零相移恢复。", "",
                 "| 工况 | 模型峰值 A | 末 10 周期 P1 / P2 W | 锁存次数 | 全程能量残差 J |",
                 "| --- | ---: | ---: | ---: | ---: |"]
        for s in summaries:
            lines.append(f"| {s['scenario']} | {s['peak_current_a']:.6f} | {s['tail_p1_w']:.6f} / {s['tail_p2_w']:.6f} | {s['trip_count']} | {s['total_energy_residual_j']:.3e} |")
        lines.extend(["", "能量式为 E1−E2−ER = Δ(½Li²)。ER 由独立的 i² 解析积分计算，不是用能量差补算。",
                      "P1/P2 采用相同的第一侧→第二侧符号；反向运行时两者均可为负。未计算效率。", ""])
        for s in summaries:
            if s["trip_count"]:
                lines.extend([f"- `{s['scenario']}`：检测时刻 {s['trip_time_s']*1e6:.3f} µs，检测电流 {s['trip_current_a']:.6f} A；",
                              f"  相对所注入/解析越限时刻的采样延迟 {s['detection_delay_s']*1e6:.6f} µs。",
                              f"  首次锁存区间初始/末端电感能量 {s['stopped_initial_energy_j']:.9g} / {s['stopped_final_energy_j']:.9g} J，",
                              f"  电阻耗散 {s['stopped_resistor_energy_j']:.9g} J，收支残差 {s['stopped_energy_residual_j']:.3e} J。"])
        lines.extend(["", "方向切换采用连续电流状态，未每周期重置或扣除均值；恒定工况收敛到独立推导的 RL 周期解。",
                      "过流案例拒绝带非零指令的提前清除；母线输入案例拒绝越限仍存在时的清除。两者均保持锁存直到第 40 周期的显式清除。",
                      "母线案例只把检测输入注入 17 V，实际第二侧恒压源始终为 12 V；这不是输出电压闭环或真实母线充电过程。", "",
                      "过流恢复案例使用每周期 2° 的反向请求斜坡；直接请求 −30° 会再次触发 1.6 A 保护，该反例已保留为回归测试。",
                      "19 项测试通过（原 SPS/EPS 12 项及新增瞬态 7 项），4 份完整波形 CSV 回读验证通过。",
                      "波形、逐周期功率、采样和事件分别保存在各工况的 CSV；完整命令与参数在 `run_metadata.json`。", "",
                      "电流阈值不是连续时间电流钳位；两桥置零的回路是理想模型中的 R-L 续流路径，不构成硬件安全保证。",
                      "未包含死区、器件损耗模型、效率、ZVS、DPS/TPS 或完整功率闭环。", ""])
        (output / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
        print("PASS: 4 transient scenarios, 19 tests, 4 raw CSV continuity/RL/energy checks")
        for s in summaries:
            print(f"{s['scenario']}: peak={s['peak_current_a']:.6f} A, final P2={s['tail_p2_w']:.6f} W, "
                  f"trips={s['trip_count']}, energy residual={s['total_energy_residual_j']:.3e} J")
    except Exception:
        (output / "failure.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "results_transient")
    run(parser.parse_args().output)
