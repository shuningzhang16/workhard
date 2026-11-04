"""独立教学模型：理想同步 Buck 平均功率级，SI 单位；仅依赖标准库。"""

from dataclasses import dataclass


@dataclass
class Parameters:
    inductance_h: float = 220e-6
    capacitance_f: float = 470e-6
    nominal_input_v: float = 9.0
    target_v: float = 2.0
    nominal_load_ohm: float = 4.0
    stepped_load_ohm: float = 2.0
    stepped_input_v: float = 7.5
    kp_duty_per_v: float = 0.03
    ki_duty_per_v_s: float = 30.0
    maximum_duty: float = 0.95
    control_period_s: float = 20e-6
    integration_substeps: int = 4
    soft_start_s: float = 0.020
    event_time_s: float = 0.050
    duration_s: float = 0.100


class VoltagePI:
    """每次采样更新一次 PI，占空比零阶保持；条件积分抑制饱和累积。"""

    def __init__(self, parameters):
        self.p = parameters
        self.integral = 0.0

    def update(self, reference_v, measured_v):
        error = reference_v - measured_v
        candidate = self.integral + self.p.ki_duty_per_v_s * self.p.control_period_s * error
        raw = self.p.kp_duty_per_v * error + candidate
        # 只在继续积分会将输出推向更深饱和时保持积分器。
        if not ((raw > self.p.maximum_duty and error > 0) or (raw < 0 and error < 0)):
            self.integral = candidate
        command = self.p.kp_duty_per_v * error + self.integral
        return min(self.p.maximum_duty, max(0.0, command))


def plant_step(current_a, output_v, duty, input_v, load_ohm, p, dt):
    """固定占空比、输入和电阻期间的 RK4 积分；不裁剪电感电流。"""

    def derivative(i, v):
        return (duty * input_v - v) / p.inductance_h, (i - v / load_ohm) / p.capacitance_f

    a, b = derivative(current_a, output_v)
    c, d = derivative(current_a + dt * a / 2, output_v + dt * b / 2)
    e, f = derivative(current_a + dt * c / 2, output_v + dt * d / 2)
    g, h = derivative(current_a + dt * e, output_v + dt * f)
    return current_a + dt * (a + 2 * c + 2 * e + g) / 6, output_v + dt * (b + 2 * d + 2 * f + h) / 6


def simulate(case, p=None):
    p = p or Parameters()
    if case not in ("startup", "load_step", "input_step"):
        raise ValueError(f"Unknown case: {case}")
    controller = VoltagePI(p)
    current_a = output_v = 0.0
    rows = []
    event_index = round(p.event_time_s / p.control_period_s)
    count = round(p.duration_s / p.control_period_s)
    dt = p.control_period_s / p.integration_substeps
    for k in range(count + 1):
        time_s = k * p.control_period_s
        input_v = p.stepped_input_v if case == "input_step" and k >= event_index else p.nominal_input_v
        load_ohm = p.stepped_load_ohm if case == "load_step" and k >= event_index else p.nominal_load_ohm
        reference_v = p.target_v * min(time_s / p.soft_start_s, 1.0)
        duty = controller.update(reference_v, output_v)
        rows.append({
            "time_s": time_s, "input_v": input_v, "load_ohm": load_ohm,
            "reference_v": reference_v, "output_v": output_v,
            "inductor_current_a": current_a, "load_current_a": output_v / load_ohm,
            "duty": duty,
        })
        if k < count:
            for _ in range(p.integration_substeps):
                current_a, output_v = plant_step(current_a, output_v, duty, input_v, load_ohm, p, dt)
    return rows


def metrics(rows, case, p):
    """恢复：事件后进入 ±2% 并保持至记录结束，且至少有 2 ms 观察余量。"""
    event = p.soft_start_s if case == "startup" else p.event_time_s
    after = [r for r in rows if r["time_s"] >= event]
    tail = [r["output_v"] for r in rows if r["time_s"] >= p.duration_s - 0.010]
    tolerance_v = 0.02 * p.target_v
    outside = [i for i, r in enumerate(after) if abs(r["output_v"] - p.target_v) > tolerance_v]
    entry_index = outside[-1] + 1 if outside else 0
    recovery_s = None
    if entry_index < len(after) and after[-1]["time_s"] - after[entry_index]["time_s"] >= 0.002:
        recovery_s = after[entry_index]["time_s"] - event
    return {
        "case": case,
        "steady_state_error_v": sum(tail) / len(tail) - p.target_v,
        "overshoot_percent": 100 * max(0.0, max(r["output_v"] for r in rows) - p.target_v) / p.target_v,
        "post_event_max_abs_deviation_v": max(abs(r["output_v"] - p.target_v) for r in after),
        "recovery_to_2_percent_s": recovery_s,
        "event_reference_time_s": event,
    }
