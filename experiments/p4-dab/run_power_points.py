"""Five fixed-parameter power-loop runs; unchanged PI and plant protection."""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
import sys
import traceback

from dab_power_loop import Gains, segment_metrics, simulate_power_loop
from dab_sps import Parameters
from dab_transient import Settings
from run_experiment import write_csv
from run_transient_demo import summarize, validate_csv


TARGETS_W = (5.0, 15.0, -10.0, 0.0)
PERIODS_PER_TARGET = 200


def parameter_points():
    # These five explicit points are not a Cartesian sweep or a stability domain.
    return [(name, Settings(circuit=Parameters(v2_v=v2), series_resistance_ohm=resistance))
            for name, v2, resistance in (
                ("v2_9_r_0p5", 9.0, 0.5),
                ("v2_12_r_0p5", 12.0, 0.5),
                ("v2_15_r_0p5", 15.0, 0.5),
                ("v2_12_r_0p25", 12.0, 0.25),
                ("v2_12_r_1", 12.0, 1.0))]


def references():
    return [target for target in TARGETS_W for _ in range(PERIODS_PER_TARGET)]


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    points = parameter_points()
    gains = Gains()
    metadata = {"started_at_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version, "command_argv": sys.orig_argv,
        "scope": "exactly five independent fixed-bus RL parameter points; no tuning or stability-domain claim",
        "gains": asdict(gains), "targets_w": TARGETS_W,
        "periods_per_target": PERIODS_PER_TARGET, "initial_current_a": 0.0,
        "clear_cycles": [], "sense_v2": "unchanged default: physical fixed V2",
        "feedback": "previous completed switching period P2 only; initial feedback zero",
        "settling_definition": "max(0.25 W, 2% absolute target), retained through segment end for at least 10 periods",
        "hardware_operations": False,
        "points": {name: asdict(settings) for name, settings in points}}
    (output / "run_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    parameters = []
    for name, settings in points:
        row = {"scenario": name, **asdict(settings.circuit), **asdict(gains),
               **{k: v for k, v in asdict(settings).items() if k != "circuit"}}
        row.update(voltage_ratio=settings.circuit.turns_ratio * settings.circuit.v2_v / settings.circuit.v1_v,
                   periods_per_target=PERIODS_PER_TARGET, total_periods=len(references()))
        parameters.append(row)
    write_csv(output / "parameters.csv", parameters)
    summaries, performance, checks = [], [], []
    try:
        for name, settings in points:
            result, control = simulate_power_loop(references(), settings=settings, gains=gains)
            wave_path = output / f"{name}_waveform.csv"
            write_csv(wave_path, result.rows)
            write_csv(output / f"{name}_control.csv", control)
            write_csv(output / f"{name}_periods.csv", result.periods)
            write_csv(output / f"{name}_samples.csv", result.samples)
            if result.events:
                write_csv(output / f"{name}_events.csv", result.events)
            else:
                (output / f"{name}_events.csv").write_text(
                    "t_s,event,reason,i_a,sensed_v2_v,request_deg\n", encoding="utf-8")
            summaries.append(summarize(name, result))
            period = 1 / settings.circuit.frequency_hz
            for metric in segment_metrics(name, result, control):
                start, stop = metric["start_period"], metric["stop_period_exclusive"]
                tail = result.periods[stop - 10:stop]
                metric.update(v2_v=settings.circuit.v2_v, series_resistance_ohm=settings.series_resistance_ohm,
                    trip_events=sum(e["event"] == "trip" and start * period <= e["t_s"] < stop * period
                                    for e in result.events),
                    tail_mean_phase_deg=math.fsum(r["scheduled_phase_deg"] for r in tail) / len(tail),
                    tail_mean_rms_current_a=math.fsum(r["i_rms_a"] for r in tail) / len(tail))
                performance.append(metric)
            # Save performance before verification, including any trips/non-settling.
            write_csv(output / "summary.csv", summaries)
            write_csv(output / "performance.csv", performance)
            checks.append(validate_csv(wave_path, settings))
            write_csv(output / "csv_checks.csv", checks)
        command = [sys.executable, "-B", "-X", "utf8", "-m", "unittest", "-v",
                   "test_dab_sps", "test_dab_eps", "test_dab_transient",
                   "test_commutation_polarity", "test_dab_power_loop", "test_power_points"]
        tests = subprocess.run(command, cwd=Path(__file__).resolve().parent,
                               capture_output=True, text=True, encoding="utf-8")
        (output / "tests.log").write_text("Command: " + subprocess.list2cmdline(command) + "\n"
            + tests.stdout + tests.stderr + f"\nProcess exit code: {tests.returncode}\n", encoding="utf-8")
        if tests.returncode:
            raise RuntimeError("Tests failed; raw traces and logs retained")
        lines = ["# 固定 PI 增益的五个有限参数工况", "",
            "离线 RL 教学模型；每次独立运行的两侧母线固定，不含输出电容或电池动态。",
            "仅验证下表五点，不代表参数范围内所有组合或完整稳定域。未调参。", "",
            "统一 V1=24 V、n=2、L=100 µH、fs=20 kHz；Kp=0.4°/W、Ki=2000°/(W·s)。",
            "目标依次 5→15→−10→0 W，各 200 周期（10 ms），每点共 800 周期（40 ms）。",
            "每周期只反馈上一已完成周期的实算 P2；电流只在独立运行起点初始化为 0。",
            "原相移限幅 ±60°、限速 6°/周期、过流阈值 8 A、母线检测阈值 15 V 均不变。",
            "原母线逻辑为 sensed_V2 > 15 V；15 V 恰在边界，不改成 >=，也不抬高阈值。",
            "未安排显式清除；若触发保护会保持锁存，并记录事件和锁存周期。", "",
            "| 参数点 | V2 / V | nV2/V1 | R / Ω | 全程峰值 / A | 跳闸次数 | 全程能量残差 / J |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for p, s in zip(parameters, summaries):
            lines.append(f"| {p['scenario']} | {p['v2_v']:g} | {p['voltage_ratio']:g} | "
                f"{p['series_resistance_ohm']:g} | {s['peak_current_a']:.6f} | {s['trip_count']} | {s['total_energy_residual_j']:.3e} |")
        lines.extend(["", "误差=实际周期 P2−目标；误差带 max(0.25 W, 2%|目标|)。",
            "进入带内时间从该段指令起点计算，要求此后保持至段末且至少 10 个周期；不能推断窗口外表现。",
            "尾段误差取最后 10 周期均值；超调按目标变化方向计，零功率达标不等于电流为零。", "",
            "| 参数点 | 目标 / W | 尾段误差 / W | 入带 / ms | 超调 / W | 峰值 / A | 幅值/速率限制次数 | 积分冻结次数 | 跳闸/锁存周期 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"])
        for m in performance:
            settling = f"{m['settling_time_s']*1000:.3f}" if m["settled_in_observed_window"] else "未进入并保持"
            lines.append(f"| {m['scenario']} | {m['target_w']:g} | {m['tail_mean_error_w']:.6f} | {settling} | "
                f"{m['directional_overshoot_w']:.6f} | {m['peak_current_a']:.6f} | "
                f"{m['amplitude_limited_updates']}/{m['rate_limited_updates']} | {m['integral_frozen_updates']} | "
                f"{m['trip_events']}/{m['latched_periods']} |")
        settled_count = sum(m["settled_in_observed_window"] for m in performance)
        trip_count = sum(s["trip_count"] for s in summaries)
        lines.extend(["", f"实际记录：{settled_count}/{len(performance)} 段满足本次入带定义，保护跳闸 {trip_count} 次。",
            "锁存造成的零功率不应解释为主动跟踪；逐段锁存周期与事件均单列。", "",
            "33 项测试通过（原 30 项加本步 3 项），5 份完整波形 CSV 回读通过。",
            "测试保留逐段能量残差 <1e−12 J、累积残差 <1e−10 J，以及时间和电流连续性。",
            "额外的一周期单元测试只检查检测输入刚大于 15 V 时会锁存，不计入五点性能比较。", "",
            "参数与原保护设置见 `parameters.csv`，完整命令与运行配置见 `run_metadata.json`。",
            "`performance.csv` 另含误差峰值、积分范围、尾段相移及 RMS 电流；原始控制、波形、周期、采样、事件分别落盘。",
            "未修改此前模型、PI、测试或结果；不宣称硬件表现、实际效率或 ZVS。", ""])
        (output / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
        print("PASS: 5 fixed parameter points, 33 tests, 5 full waveform CSV checks")
        print(f"Observed settling: {settled_count}/{len(performance)} segments; trips: {trip_count}")
        for m in performance:
            print(f"{m['scenario']}: target={m['target_w']:g} W, tail error={m['tail_mean_error_w']:.6f} W, "
                  f"settled={m['settled_in_observed_window']}, settling={m['settling_time_s']} s, "
                  f"peak={m['peak_current_a']:.6f} A, trips={m['trip_events']}")
    except Exception:
        (output / "failure.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "results_power_points")
    run(parser.parse_args().output)
