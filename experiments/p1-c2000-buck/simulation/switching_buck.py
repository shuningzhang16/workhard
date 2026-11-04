"""理想同步 Buck 开关模型：精确 PWM 边沿分段，段内 RK4；标准库实现。"""

import math
from dataclasses import replace

from buck_model import Parameters, VoltagePI, plant_step


PWM_FREQUENCY_HZ = 50_000.0


def simulate_switching(case, max_step_s=0.5e-6):
    if case not in ("fixed_duty", "controlled_load_step"):
        raise ValueError(case)
    p = Parameters()
    if case == "fixed_duty":
        p = replace(p, duration_s=0.060)
    period_s = 1 / PWM_FREQUENCY_HZ
    # 本步限定控制器与 PWM 一比一同步，不隐式改变已有控制周期。
    if p.control_period_s != period_s or max_step_s <= 0:
        raise ValueError("This experiment requires Ts=Tpwm=20 us and positive integration step")
    count = round(p.duration_s / period_s)
    windows = [(count - 20, count)] if case == "fixed_duty" else [(2490, 2530), (count - 20, count)]
    pi = VoltagePI(p)
    current_a = output_v = 0.0
    samples, cycles, waveform = [], [], []
    for k in range(count + 1):
        start_s = k * period_s
        load_ohm = p.stepped_load_ohm if case == "controlled_load_step" and k >= 2500 else p.nominal_load_ohm
        reference_v = p.target_v if case == "fixed_duty" else p.target_v * min(start_s / p.soft_start_s, 1)
        duty = p.target_v / p.nominal_input_v if case == "fixed_duty" else pi.update(reference_v, output_v)
        samples.append({"time_s": start_s, "input_v": p.nominal_input_v,
                        "load_ohm": load_ohm, "reference_v": reference_v,
                        "output_v": output_v, "inductor_current_a": current_a,
                        "load_current_a": output_v / load_ohm, "duty": duty})
        if k == count:
            break
        keep = any(a <= k < b for a, b in windows)
        on_s = duty * period_s
        mean_v_integral = mean_i_integral = 0.0
        min_v = max_v = output_v
        min_i = max_i = current_a
        # 每一段内实际开关节点为 Vin 或 0，不使用 duty*Vin 作为开关电压。
        for gate, offset_s, segment_s in ((1, 0.0, on_s), (0, on_s, period_s - on_s)):
            if segment_s == 0:
                continue
            steps = math.ceil(segment_s / max_step_s)
            dt = segment_s / steps
            if keep:
                waveform.append({"time_s": start_s + offset_s, "cycle": k,
                                 "point": "segment_start", "high_side_on": gate,
                                 "switch_voltage_v": gate * p.nominal_input_v,
                                 "output_v": output_v, "inductor_current_a": current_a,
                                 "load_ohm": load_ohm, "duty_command": duty})
            for j in range(1, steps + 1):
                # plant_step 在 gate=0/1 时即真实两种线性拓扑，状态不重置。
                next_i, next_v = plant_step(current_a, output_v, gate, p.nominal_input_v, load_ohm, p, dt)
                mean_v_integral += (output_v + next_v) * dt / 2
                mean_i_integral += (current_a + next_i) * dt / 2
                current_a, output_v = next_i, next_v
                min_v, max_v = min(min_v, output_v), max(max_v, output_v)
                min_i, max_i = min(min_i, current_a), max(max_i, current_a)
                if keep:
                    waveform.append({"time_s": start_s + offset_s + j * dt, "cycle": k,
                                     "point": "segment_end" if j == steps else "integration",
                                     "high_side_on": gate, "switch_voltage_v": gate * p.nominal_input_v,
                                     "output_v": output_v, "inductor_current_a": current_a,
                                     "load_ohm": load_ohm, "duty_command": duty})
        cycles.append({"cycle_start_s": start_s, "cycle_end_s": (k + 1) * period_s,
                       "duty": duty, "on_time_s": on_s, "load_ohm": load_ohm,
                       "output_mean_v": mean_v_integral / period_s,
                       "current_mean_a": mean_i_integral / period_s,
                       "output_pp_v": max_v - min_v, "current_pp_a": max_i - min_i})
    return p, samples, cycles, waveform


def steady_metrics(cycles):
    tail = cycles[-20:]
    return {"window_start_s": tail[0]["cycle_start_s"], "window_end_s": tail[-1]["cycle_end_s"],
            "cycle_count": len(tail),
            "output_mean_v": sum(r["output_mean_v"] for r in tail) / len(tail),
            "current_mean_a": sum(r["current_mean_a"] for r in tail) / len(tail),
            "mean_cycle_output_pp_v": sum(r["output_pp_v"] for r in tail) / len(tail),
            "mean_cycle_current_pp_a": sum(r["current_pp_a"] for r in tail) / len(tail),
            "max_cycle_output_pp_v": max(r["output_pp_v"] for r in tail),
            "max_cycle_current_pp_a": max(r["current_pp_a"] for r in tail),
            "cycle_mean_output_span_v": max(r["output_mean_v"] for r in tail) - min(r["output_mean_v"] for r in tail)}
