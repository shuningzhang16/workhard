"""平均模型的采样保护演示；所有阈值都是教学假设，不是硬件安全值。"""

from dataclasses import dataclass, replace
import math

from buck_model import Parameters, VoltagePI, plant_step


@dataclass
class ProtectionLimits:
    overcurrent_a: float = 2.5
    output_overvoltage_v: float = 2.4
    input_undervoltage_v: float = 6.0
    clear_max_abs_output_v: float = 0.1
    clear_max_abs_current_a: float = 0.1


class ProtectedController:
    def __init__(self, p=None, limits=None):
        self.p = p or Parameters()
        self.limits = limits or ProtectionLimits()
        self.pi = VoltagePI(self.p)
        self.state = "SOFT_START"
        self.latched_fault = ""
        self.start_sample = 0
        self.events = []

    def active_faults(self, input_v, output_v, current_a):
        faults = []
        if abs(current_a) >= self.limits.overcurrent_a:
            faults.append("OVERCURRENT")
        if output_v >= self.limits.output_overvoltage_v:
            faults.append("OUTPUT_OVERVOLTAGE")
        if input_v <= self.limits.input_undervoltage_v:
            faults.append("INPUT_UNDERVOLTAGE")
        return "|".join(faults)

    def event(self, sample, old_state, reason):
        self.events.append({"time_s": sample * self.p.control_period_s,
                            "from_state": old_state, "to_state": self.state,
                            "reason": reason, "latched_fault": self.latched_fault})

    def update(self, sample, input_v, output_v, current_a, clear_request=False, clear_evidence=None):
        active = self.active_faults(input_v, output_v, current_a)
        if active and self.state != "FAULT_LATCHED":
            old_state = self.state
            self.state = "FAULT_LATCHED"
            self.latched_fault = active
            self.pi.integral = 0.0
            self.event(sample, old_state, "trip")

        clear_result = "not_requested"
        if clear_request and self.state == "FAULT_LATCHED":
            if active:
                clear_result = "rejected_active_fault"
            elif (abs(output_v) > self.limits.clear_max_abs_output_v
                  or abs(current_a) > self.limits.clear_max_abs_current_a):
                # 从带能状态直接恢复到 0 V 参考会吸收电容能量并产生反向电流。
                clear_result = "rejected_residual_energy"
            elif clear_evidence is not None and (
                    not clear_evidence["observable"]
                    or not math.isfinite(clear_evidence["max_abs_output_v"])
                    or not math.isfinite(clear_evidence["max_abs_current_a"])
                    or not clear_evidence["max_abs_output_v"] >= abs(output_v)
                    or not clear_evidence["max_abs_current_a"] >= abs(current_a)):
                clear_result = "rejected_unobservable_measurement"
            elif clear_evidence is not None and (
                    clear_evidence["max_abs_output_v"] > self.limits.clear_max_abs_output_v
                    or clear_evidence["max_abs_current_a"] > self.limits.clear_max_abs_current_a):
                clear_result = "rejected_residual_energy"
            else:
                self.state = "SOFT_START"
                self.latched_fault = ""
                self.pi.integral = 0.0
                self.start_sample = sample
                clear_result = "accepted"
            self.event(sample, "FAULT_LATCHED", "clear_" + clear_result)
        elif clear_request:
            clear_result = "ignored_not_latched"

        if self.state == "FAULT_LATCHED":
            duty = reference_v = 0.0
        else:
            elapsed_s = (sample - self.start_sample) * self.p.control_period_s
            reference_v = self.p.target_v * min(elapsed_s / self.p.soft_start_s, 1.0)
            if self.state == "SOFT_START" and sample - self.start_sample >= round(self.p.soft_start_s / self.p.control_period_s):
                self.state = "RUN"
                self.event(sample, "SOFT_START", "soft_start_complete")
            duty = self.pi.update(reference_v, output_v)
        return {"duty": duty, "reference_v": reference_v, "state": self.state,
                "active_faults": active, "latched_fault": self.latched_fault,
                "clear_result": clear_result}


def energy_j(current_a, output_v, p):
    return 0.5 * p.inductance_h * current_a**2 + 0.5 * p.capacitance_f * output_v**2


def simulate_protected(case):
    normal_cases = ("startup", "load_step", "input_step")
    fault_cases = ("overcurrent", "overvoltage", "undervoltage")
    if case not in normal_cases + fault_cases:
        raise ValueError(f"Unknown case: {case}")
    p = Parameters() if case in normal_cases else replace(Parameters(), duration_s=0.140)
    control = ProtectedController(p)
    current_a = output_v = 0.0
    rows = []
    attempted_active_clear = False
    event_sample = round(0.050 / p.control_period_s)
    end_fault_sample = round(0.065 / p.control_period_s)
    clear_sample = round(0.080 / p.control_period_s)
    count = round(p.duration_s / p.control_period_s)
    dt = p.control_period_s / p.integration_substeps
    for k in range(count + 1):
        input_v, load_ohm = p.nominal_input_v, p.nominal_load_ohm
        if case == "load_step" and k >= event_sample:
            load_ohm = p.stepped_load_ohm
        if case == "input_step" and k >= event_sample:
            input_v = p.stepped_input_v
        injection_active = case in fault_cases and event_sample <= k < end_fault_sample
        if injection_active:
            if case == "overcurrent":
                load_ohm = 0.25  # 低阻负载使 PI 供电电流上升，无人工篡改状态。
            elif case == "overvoltage":
                input_v = 14.0  # 输入上升造成实际输出动态过压。
            else:
                input_v = 4.5
        # 测试器在首次观察到故障条件时发出一次明确 clear 请求，验证拒绝。
        request = False
        if case in fault_cases:
            if not attempted_active_clear and control.active_faults(input_v, output_v, current_a):
                request = True
                attempted_active_clear = True
            if k == clear_sample:
                request = True
        command = control.update(k, input_v, output_v, current_a, request)
        rows.append({"time_s": k * p.control_period_s, "input_v": input_v,
                     "load_ohm": load_ohm, "output_v": output_v,
                     "inductor_current_a": current_a, "load_current_a": output_v / load_ohm,
                     "stored_energy_j": energy_j(current_a, output_v, p),
                     "injection_active": int(injection_active), "clear_request": int(request),
                     **command})
        if k < count:
            for _ in range(p.integration_substeps):
                # 故障时 duty=0 是理想低侧持续导通的续流支路，不是两管关断。
                # 保留原状态，允许 iL 和 vO 有符号；不将能量凭空清零。
                current_a, output_v = plant_step(current_a, output_v, command["duty"], input_v, load_ohm, p, dt)
    return p, rows, control.events
