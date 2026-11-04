"""把现有采样保护接入实际 PWM 积分；测试器只修改输入、负载和清除请求。"""

from dataclasses import replace

from buck_model import Parameters
from protection import ProtectedController, energy_j
from switching_buck import PWM_FREQUENCY_HZ, switching_cycle


CASES = ("load_step", "overcurrent", "overvoltage", "undervoltage")


def waveform_windows(case, count):
    if case == "load_step":
        return [(2490, 2530), (count - 20, count)]
    # 故障注入与初始续流、刺激移除、显式清除、软启动结束、末态。
    return [(2490, 2600), (3240, 3260), (3990, 4030), (4990, 5010), (count - 20, count)]


def simulate_protected_switching(case, max_step_s=0.5e-6):
    if case not in CASES:
        raise ValueError(case)
    p = Parameters() if case == "load_step" else replace(Parameters(), duration_s=0.140)
    if p.control_period_s != 1 / PWM_FREQUENCY_HZ or max_step_s <= 0:
        raise ValueError("This experiment requires Ts=Tpwm=20 us and positive integration step")
    control = ProtectedController(p)
    count = round(p.duration_s / p.control_period_s)
    windows = waveform_windows(case, count)
    samples, cycles, waveform = [], [], []
    current_a = output_v = 0.0
    attempted_active_clear = attempted_residual_clear = False
    for k in range(count + 1):
        input_v, load_ohm = p.nominal_input_v, p.nominal_load_ohm
        if case == "load_step" and k >= 2500:
            load_ohm = p.stepped_load_ohm
        injection_active = case != "load_step" and 2500 <= k < 3250
        if injection_active:
            if case == "overcurrent":
                load_ohm = 0.25
            elif case == "overvoltage":
                input_v = 14.0
            else:
                input_v = 4.5
        request = False
        if case != "load_step":
            active = control.active_faults(input_v, output_v, current_a)
            if not attempted_active_clear and active:
                request = attempted_active_clear = True
            # 对实际功率级状态发命令，覆盖无活动故障但仍不满足清除条件的情况。
            elif (not attempted_residual_clear and control.state == "FAULT_LATCHED"
                  and not active and (abs(output_v) > control.limits.clear_max_abs_output_v
                                     or abs(current_a) > control.limits.clear_max_abs_current_a)):
                request = attempted_residual_clear = True
            if k == 4000:
                request = True
        command = control.update(k, input_v, output_v, current_a, request)
        samples.append({"time_s": k * p.control_period_s, "input_v": input_v,
                        "load_ohm": load_ohm, "output_v": output_v,
                        "inductor_current_a": current_a, "load_current_a": output_v / load_ohm,
                        "stored_energy_j": energy_j(current_a, output_v, p),
                        "injection_active": int(injection_active), "clear_request": int(request),
                        **command})
        if k == count:
            break
        current_a, output_v, cycle, trace = switching_cycle(
            k, current_a, output_v, command["duty"], input_v, load_ohm, p,
            max_step_s, any(a <= k < b for a, b in windows))
        cycles.append({"input_v": input_v, "state": command["state"], **cycle})
        waveform.extend({"input_v": input_v, "state": command["state"], **r} for r in trace)
    return p, samples, cycles, waveform, control.events
