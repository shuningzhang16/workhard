"""Execute finite continuous-plant PI/protection cases and retain evidence."""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
import sys
import traceback

from dab_continuous import simulate_continuous
from dab_continuous_control import simulate_continuous_loop, simulate_switching_control
from dab_power_loop import Gains, scenarios, segment_metrics
from dab_transient import Settings
from run_continuous import verify_rows
from run_deadtime import load_cases
from run_experiment import write_csv
from test_dab_switching import replay_fixed


def fixed_regression(source):
    comparisons = []
    fields = ("p1_input_w", "p2_output_w", "i_rms_a", "i_end_a", "i_mean_a",
              "resistor_power_w", "diode_power_w", "turnon_redistribution_power_w")
    for name, method, alpha, cycle in load_cases(source):
        for deadtime in (150e-9, 500e-9):
            p, phase = cycle.parameters, cycle.phase_deg
            old = simulate_continuous(p, alpha, phase, deadtime_s=deadtime)
            new = replay_fixed(p, alpha, phase, deadtime, count=100)
            row = {"case": name, "method": method, "alpha_deg": alpha,
                   "phase_deg": phase, "deadtime_s": deadtime, "periods": 100}
            for field in fields:
                row[f"max_difference_{field}"] = max(abs(a[field]-b[field]) for a, b in zip(old.periods, new.periods))
            row["zvs_flags_equal"] = int([e["zvs_in_this_model"] for e in old.turnons] ==
                                         [e["zvs_in_this_model"] for e in new.turnons])
            comparisons.append(row)
            if not row["zvs_flags_equal"] or any(row[f"max_difference_{f}"] > 1e-8 for f in fields):
                raise AssertionError(f"Fixed-angle replay changed existing physics: {row}")
    return comparisons


def run(source, output):
    output.mkdir(parents=True, exist_ok=True)
    metadata = {"started_at_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version, "command_argv": sys.orig_argv,
        "carrier_update_reference_deg": 90, "control_modulation": "SPS; EPS fixed-angle regression only",
        "deadtime_s": 150e-9, "gains": asdict(Gains()),
        "feedback": "P2 of the preceding completed 50 us period including Coss source charge",
        "physical_state": "iL, four capacitor-node voltages, four leg channel states, pending turn-on deadlines",
        "protection_order": "sample before scheduled turn-off/turn-on at ties",
        "trip_response": "cancel pending high turn-ons; transition both bridges to low-low through physical dead time",
        "recovery": "explicit clear, zero raw command, no sampled fault, abs(iL)<=0.2A; reenable by physical switching",
        "physical_v2_varies": False, "postprocessed_channel_gate_losses_in_plant": False,
        "hardware_operations": False, "scenarios": {}}
    (output/"input_comparisons.csv").write_bytes(source.read_bytes())
    checks, summaries, performance = [], [], []
    cases = [(name, refs, options, True) for name, refs, options in scenarios()]
    cases.append(("bus_input_recovery", [5]*20+[0]*30+[5]*90,
        {"clear_cycles": (22, 40), "sense_v2": lambda turns: 17 if 20.33 <= turns < 25 else 15}, True))
    cases.append(("pending_turnon_trip", [-0.54]*4,
        {"sense_v2": lambda turns: 17 if 0.75 <= turns < 1 else 12}, False))
    cases.append(("phase_zero_crossing", [0.54]*8+[0]*8+[-0.54]*8, {}, False))
    try:
        comparisons = fixed_regression(source)
        write_csv(output/"fixed_angle_regression.csv", comparisons)
        print("PASS: 16 fixed-angle, 100-period replays against existing solver", flush=True)
        for name, commands, options, closed in cases:
            settings = options.get("settings", Settings())
            metadata["scenarios"][name] = {"settings": asdict(settings), "closed_loop": closed,
                "references_w" if closed else "phase_requests_deg": commands,
                "clear_cycles": list(options.get("clear_cycles", ())),
                "sense_injection": ("17V from 20.33T to 25T, otherwise exactly 15V" if name == "bus_input_recovery" else
                                    "17V from 0.75T to 1T, otherwise 12V" if name == "pending_turnon_trip" else "none")}
            (output/"run_metadata.json").write_text(json.dumps(metadata, indent=2)+"\n", encoding="utf-8")
            if closed:
                result, control = simulate_continuous_loop(commands, **options)
                write_csv(output/f"{name}_control.csv", control)
                performance.extend(segment_metrics(name, result, control))
            else:
                result = simulate_switching_control(settings, commands, **options)
            path = output/f"{name}_waveform.csv"
            write_csv(path, result.rows)
            write_csv(output/f"{name}_periods.csv", result.periods)
            write_csv(output/f"{name}_samples.csv", result.samples)
            write_csv(output/f"{name}_turnons.csv", result.turnons)
            write_csv(output/f"{name}_gate_events.csv", result.gate_events)
            if result.events:
                write_csv(output/f"{name}_events.csv", result.events)
            else:
                (output/f"{name}_events.csv").write_text("t_s,event,reason,i_a,sensed_v2_v,request_deg\n", encoding="utf-8")
            checks.append(verify_rows(path, settings.circuit))
            off_min = min(e["actual_off_duration_s"] for e in result.turnons)
            if off_min < 150e-9-1e-16:
                raise AssertionError("A channel turned on before its physical dead time")
            if any(e["incoming"] != "low" for e in result.turnons if e["latched"]):
                raise AssertionError("A high channel turned on while fault was latched")
            summary = {"scenario": name, "closed_loop": int(closed), "periods": len(commands),
                "waveform_rows": len(result.rows), "peak_current_a": max(r["i_peak_a"] for r in result.rows),
                "max_sampled_current_a": max(abs(s["i_a"]) for s in result.samples),
                "tail_p2_w": math.fsum(p["p2_w"] for p in result.periods[-10:])/min(10,len(commands)),
                "trip_count": sum(e["event"] == "trip" for e in result.events),
                "clear_accepted_count": sum(e["event"] == "clear_accepted" for e in result.events),
                "clear_denied_count": sum(e["event"] == "clear_denied" for e in result.events),
                "minimum_channel_off_duration_s": off_min,
                "max_cumulative_energy_residual_j": max(abs(r["cumulative_energy_residual_j"]) for r in result.rows)}
            summaries.append(summary)
            write_csv(output/"summary.csv", summaries)
            write_csv(output/"performance.csv", performance)
            write_csv(output/"csv_checks.csv", checks)
            print(f"{name}: peak={summary['peak_current_a']:.6f} A, trips={summary['trip_count']}, "
                  f"tail P2={summary['tail_p2_w']:.6f} W", flush=True)
        command = [sys.executable, "-B", "-X", "utf8", "-m", "unittest", "-v",
            "test_dab_sps", "test_dab_eps", "test_dab_transient", "test_commutation_polarity",
            "test_dab_power_loop", "test_power_points", "test_dab_deadtime", "test_deadtime_spice",
            "test_dab_continuous", "test_dab_loss_budget", "test_dab_switching", "test_dab_continuous_control"]
        tests = subprocess.run(command, cwd=Path(__file__).resolve().parent, capture_output=True, text=True, encoding="utf-8")
        (output/"tests.log").write_text("Command: "+subprocess.list2cmdline(command)+"\n"+
            tests.stdout+tests.stderr+f"\nExit code: {tests.returncode}\n", encoding="utf-8")
        if tests.returncode:
            raise RuntimeError("Tests failed; actual results and logs retained")
        lines = ["# 连续死区物理模型上的 PI 与采样保护", "",
            "固定载波 90° 参考点更新，保留电流、四节点、导通状态及待开通期限；不使用逐周期状态重置。",
            "PI 沿用 Kp=0.4°/W、Ki=2000°/(W·s)，仅反馈上一完整周期 P2；±60°、6°/周期不变。",
            "20 次采样/周期；过流默认 8 A、故障实验 1.6 A，清除电流 0.2 A，检测电压严格 >15 V。",
            "故障优先取消未发生的高管开通，通过实际死区将两桥换到低低零电压状态。", "",
            "| 工况 / 起点 | 目标 W | 尾 10 周期误差 W | 入带 ms | 锁存周期 |",
            "| --- | ---: | ---: | ---: | ---: |"]
        for m in performance:
            settle = f"{m['settling_time_s']*1000:.3f}" if m["settled_in_observed_window"] else "未保持入带"
            lines.append(f"| {m['scenario']} / {m['start_period']} | {m['target_w']:g} | "
                f"{m['tail_mean_error_w']:.6f} | {settle} | {m['latched_periods']} |")
        lines.extend(["", "入带为 max(0.25 W, 2%|目标|)，保持至该指令段结束且至少 10 周期。",
            "100 W 饱和请求及保护锁存区间不计为跟踪成功；零目标段含锁存停机，不能代表主动零功率性能。", "",
            "16 个固定角工况各 100 周期与原求解器比较通过；55 项测试、6 份完整波形回读通过。",
            "定向测试包括死区被采样打断、不同腿死区重叠、零相移同时开关、换向、故障取消待开通、严格电压阈值与显式恢复。",
            "母线仍为固定理想源；检测注入未改变物理电压，沟道/栅驱后处理未纳入物理闭环。",
            "本次是有限离线 SPS 实验；不宣称硬件保护能力、完整稳定域、效率或热性能。", ""])
        (output/"RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
        print("PASS: 55 tests, 16 fixed-angle comparisons, 6 complete waveform checks", flush=True)
    except Exception:
        (output/"failure.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=root/"results_eps"/"comparisons.csv")
    parser.add_argument("--output", type=Path, default=root/"results_continuous_control")
    args = parser.parse_args()
    run(args.source, args.output)
