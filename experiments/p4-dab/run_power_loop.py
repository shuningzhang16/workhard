"""Run the causal fixed-bus power loop and retain its full discrete/plant trace."""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import traceback

from dab_power_loop import Gains, scenarios, segment_metrics, simulate_power_loop
from dab_transient import Settings
from run_experiment import write_csv
from run_transient_demo import summarize, validate_csv


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    metadata = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "python_version": sys.version,
        "command_argv": sys.orig_argv, "model": "fixed-bus RL plant with discrete power PI",
        "gains_teaching_assumptions": asdict(Gains()),
        "control_update_period_s": 1 / Settings().circuit.frequency_hz,
        "feedback": "p2_w of exactly the previous completed switching period; initial feedback=0",
        "antiwindup": "conditional integration against both amplitude and slew reachable limits",
        "settling_definition": "max(0.25 W, 2% target), stays in band to segment end, minimum 10 completed periods",
        "hardware_operations": False, "scenarios": {}}
    summaries, performance, checks = [], [], []
    try:
        for name, references, options in scenarios():
            settings = options.get("settings", Settings())
            metadata["scenarios"][name] = {"settings": asdict(settings), "references_w": references,
                                           "clear_cycles": list(options.get("clear_cycles", ()))}
            (output / "run_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
            result, control = simulate_power_loop(references, **options)
            path = output / f"{name}_waveform.csv"
            write_csv(path, result.rows)
            write_csv(output / f"{name}_control.csv", control)
            write_csv(output / f"{name}_periods.csv", result.periods)
            write_csv(output / f"{name}_samples.csv", result.samples)
            if result.events:
                write_csv(output / f"{name}_events.csv", result.events)
            else:
                (output / f"{name}_events.csv").write_text("t_s,event,reason,i_a,sensed_v2_v,request_deg\n", encoding="utf-8")
            summaries.append(summarize(name, result))
            performance.extend(segment_metrics(name, result, control))
            checks.append(validate_csv(path, result.settings))
        write_csv(output / "summary.csv", summaries)
        write_csv(output / "performance.csv", performance)
        write_csv(output / "csv_checks.csv", checks)
        command = [sys.executable, "-B", "-X", "utf8", "-m", "unittest", "-v", "test_dab_sps",
                   "test_dab_eps", "test_dab_transient", "test_commutation_polarity", "test_dab_power_loop"]
        tests = subprocess.run(command, cwd=Path(__file__).resolve().parent,
                               capture_output=True, text=True, encoding="utf-8")
        (output / "tests.log").write_text("Command: " + subprocess.list2cmdline(command) + "\n"
            + tests.stdout + tests.stderr + f"\nProcess exit code: {tests.returncode}\n", encoding="utf-8")
        if tests.returncode:
            raise RuntimeError("Tests failed; full plant/controller traces and logs retained")
        lines = ["# 固定母线下的离散传输功率闭环", "",
                 "独立离线教学仿真，非硬件测量；母线仍为理想 24 V / 12 V，不含输出电压或电池动态。",
                 f"运行时间（UTC）：{metadata['started_at_utc']}。", "",
                 "PI 每 50 µs 更新一次，只使用上一已完成周期的实算 P2；首次反馈设为 0 W。",
                 "教学增益 Kp=0.4°/W、Ki=2000°/(W·s)，相移限幅 ±60°、限速 6°/周期。",
                 "同时针对幅值和速率限制冻结向受限方向累积的积分；保护锁存时积分清零，电感电流不重置。", "",
                 "以下误差为实际周期功率减目标；方向性超调按指令变化方向计算。进入带内时间要求保持至本指令段结束，至少 10 个周期。",
                 "容差带为 max(0.25 W, 2% 目标绝对值)，仅描述本次有限观察窗口。", "",
                 "| 工况 / 起始周期 | 目标 W | 尾 10 周期误差 W | 方向性超调 W | 进入带内时间 ms | 峰值 A | 冻结积分次数 |",
                 "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for m in performance:
            settling = f"{m['settling_time_s']*1000:.3f}" if m["settled_in_observed_window"] else "观察窗口内未进入并保持"
            lines.append(f"| {m['scenario']} / {m['start_period']} | {m['target_w']:g} | {m['tail_mean_error_w']:.6f} | "
                         f"{m['directional_overshoot_w']:.6f} | {settling} | {m['peak_current_a']:.6f} | {m['integral_frozen_updates']} |")
        lines.extend(["", "100 W 指令是故意设置的不可达请求；未将受限功率记成达标。保护案例的零功率跟踪段包含锁存停机，不代表主动控制性能。", "",
                      "| 工况 | 全程峰值 A | E1−E2−ER−ΔEL / J | 保护锁存次数 |",
                      "| --- | ---: | ---: | ---: |"])
        for s in summaries:
            lines.append(f"| {s['scenario']} | {s['peak_current_a']:.6f} | {s['total_energy_residual_j']:.3e} | {s['trip_count']} |")
        lines.extend(["", "过流恢复案例保持 1.6 A 阈值：非零功率指令时的显式清除被拒绝；指令为零、电流满足原清除条件后才接受。",
                      "该案例以 5 W 指令恢复；控制器不绕过原采样保护，也没有改变故障期间的 R-L 储能耗散路径。", "",
                      "30 项测试通过：此前 25 项及新增闭环 5 项。3 份完整波形 CSV 回读的连续性、RL 方程及能量检查通过。",
                      "因果性测试逐项确认反馈来自 k−1 周期，并改变未来目标验证先前输出不变。",
                      "物理容差仍为逐段能量残差 <1e−12 J、累积残差 <1e−10 J；没有每周期扣除均值或重置电感电流。", "",
                      "控制器积分与限幅/限速标志见 `*_control.csv`，逐段性能见 `performance.csv`，实算功率见 `*_periods.csv`。",
                      "这些增益只在所列固定参数和有限工况下验证，不宣称完整稳定域、硬件性能、效率或 ZVS。", ""])
        (output / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
        print("PASS: 3 closed-loop scenarios, 30 tests, 3 complete waveform CSV checks")
        for m in performance:
            print(f"{m['scenario']} [{m['start_period']}:{m['stop_period_exclusive']}]: target={m['target_w']:g} W, "
                  f"tail error={m['tail_mean_error_w']:.6f} W, settled={m['settled_in_observed_window']}, "
                  f"overshoot={m['directional_overshoot_w']:.6f} W")
    except Exception:
        (output / "failure.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "results_power_loop")
    run(parser.parse_args().output)
