"""Run the bounded SPS study and retain raw data and the actual test transcript."""

import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import traceback

from dab_sps import Parameters, simulate, waveform_rows


def write_csv(path, rows):
    rows = list(rows)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def summary_row(name, cycle):
    p = cycle.parameters
    return {"case": name, **asdict(p), "phase_deg": cycle.phase_deg,
            "voltage_ratio_nV2_over_V1": p.turns_ratio * p.v2_v / p.v1_v,
            **cycle.metrics}


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    wave_dir = output / "waveforms"
    wave_dir.mkdir(exist_ok=True)
    metadata = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "result_type": "ideal_offline_simulation_not_hardware_measurement",
        "python_version": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "command_argv": [sys.executable, *sys.argv],
        "solver": "event-aligned piecewise-linear integration of di/dt=(v1-n*v2)/L",
        "initial_condition": "zero time-mean periodic current; not startup settling",
        "parameter_source": "independent low-voltage teaching assumptions; not RD264",
        "parameters_default": asdict(Parameters()),
        "waveform_periods": 2,
        "waveform_nominal_subdivisions_per_period": 200,
        "scan_voltage_ratios": [0.75, 1.0, 1.25],
        "scan_phase_degrees": list(range(-90, 91, 15)),
        "hardware_operations": False,
    }
    (output / "run_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        cases = []
        for label, v2 in [("matched", 12), ("ratio075", 9), ("ratio125", 15)]:
            for mode, phase in [("forward", 30), ("reverse", -30), ("zero", 0)]:
                name = f"{label}_{mode}"
                cycle = simulate(Parameters(v2_v=v2), phase)
                cases.append(summary_row(name, cycle))
                write_csv(wave_dir / f"{name}.csv", waveform_rows(cycle))
        write_csv(output / "cases.csv", cases)

        scan = []
        for ratio in metadata["scan_voltage_ratios"]:
            for phase in metadata["scan_phase_degrees"]:
                cycle = simulate(Parameters(v2_v=12 * ratio), phase)
                scan.append(summary_row(f"ratio{ratio}_phase{phase}", cycle))
        write_csv(output / "scan.csv", scan)

        # Read back the saved raw CSV, independently of the in-memory metrics.
        csv_checks = []
        for case in cases:
            with (wave_dir / f"{case['case']}.csv").open(encoding="utf-8", newline="") as stream:
                rows = [{key: float(value) for key, value in row.items()}
                        for row in csv.DictReader(stream)]
            duration = rows[-1]["t1_s"] - rows[0]["t0_s"]
            power = math.fsum((r["t1_s"] - r["t0_s"]) * r["p2_avg_w"] for r in rows) / duration
            rms = math.sqrt(math.fsum(
                (r["t1_s"] - r["t0_s"]) * (r["iL0_a"]**2
                + r["iL0_a"] * r["iL1_a"] + r["iL1_a"]**2) / 3
                for r in rows) / duration)
            check = {"case": case["case"], "rows": len(rows),
                     "power_roundtrip_error_w": power - case["p2_time_w"],
                     "rms_roundtrip_error_a": rms - case["i_rms_a"]}
            csv_checks.append(check)
            if abs(check["power_roundtrip_error_w"]) > 1e-9 or abs(check["rms_roundtrip_error_a"]) > 1e-9:
                raise AssertionError(f"CSV round-trip mismatch: {check}")
        write_csv(output / "csv_checks.csv", csv_checks)

        test_command = [sys.executable, "-m", "unittest", "-v", "test_dab_sps"]
        tests = subprocess.run(test_command, cwd=Path(__file__).resolve().parent,
                               capture_output=True, text=True, encoding="utf-8")
        transcript = ("Command: " + subprocess.list2cmdline(test_command) + "\n"
                      + tests.stdout + tests.stderr
                      + f"\nProcess exit code: {tests.returncode}\n")
        (output / "tests.log").write_text(transcript, encoding="utf-8")
        if tests.returncode:
            raise RuntimeError("Tests failed; see tests.log and saved CSV evidence")

        maximum_error = max(abs(r["power_error_w"]) for r in scan)
        lines = [
            "# SPS 低压教学模型：本次运行结果", "",
            "结果类型：理想模型离线仿真，未进行实物测量。参数均为教学假设。", "",
            f"运行时间（UTC）：{metadata['started_at_utc']}。Python {platform.python_version()}。",
            "求解电感微分方程，按开关事件分段线性积分；选择零直流偏置周期解。", "",
            "| 工况 | 相移 / ° | nV2/V1 | 解析功率 / W | 时域功率 / W | 原边峰值 / A | 原边 RMS / A |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for r in cases:
            lines.append(f"| {r['case']} | {r['phase_deg']:g} | {r['voltage_ratio_nV2_over_V1']:g} | "
                         f"{r['p_analytic_w']:.6f} | {r['p2_time_w']:.6f} | "
                         f"{r['i_peak_a']:.6f} | {r['i_rms_a']:.6f} |")
        lines.extend([
            "", f"有限扫描共 {len(scan)} 点：3 个电压比 × 13 个相移（−90° 至 +90°，步进 15°）。",
            f"最大解析/时域功率绝对误差：{maximum_error:.3e} W。",
            f"最大端口功率不平衡：{max(abs(r['power_balance_w']) for r in scan):.3e} W。",
            f"最大周期首尾电流误差：{max(abs(r['periodic_error_a']) for r in scan):.3e} A。",
            f"最大电流时间均值绝对值：{max(abs(r['i_mean_a']) for r in scan):.3e} A。", "",
            "6 项物理与数据导出测试通过，实际输出保存在 `tests.log`；扫描测试内部覆盖上述 39 点。",
            "9 份波形 CSV 已读回并重新积分，误差保存在 `csv_checks.csv`。", "",
            "电压匹配时，±30° 分别传输 ±20 W；0° 的零偏置周期解电流为零。",
            "电压比为 0.75 或 1.25 时，0° 平均功率仍为零，但原边 RMS 电流约 0.433 A。",
            "有限扫描只比较指定电压比与相移，不是整个设计空间或器件额定能力的验证。", "",
            "误差接近浮点舍入水平，是因为理想桥输出分段恒定，电感电流分段线性，积分可精确到浮点精度；",
            "这不代表实际器件精度，也不证明效率、ZVS、启动、瞬态控制或硬件安全性。", "",
            "复现命令及参数定义见上级 `README.md` 和 `MODEL.md`。", "",
        ])
        (output / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"PASS: {len(cases)} cases, {len(scan)} scan points, 6 tests, 9 CSV round-trip checks")
        print(f"Maximum analytical/time-domain power error: {maximum_error:.3e} W")
        print(f"Results: {output.resolve()}")
    except Exception:
        (output / "failure.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "results")
    run(parser.parse_args().output)
