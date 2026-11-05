"""隔离的单周期 CMPA 延迟、ADC/PWM 量化；复用原控制器和 PWM 功率级。"""

import copy
import math
import re
from dataclasses import replace
from pathlib import Path

from buck_model import Parameters
from protection import ProtectedController, energy_j
from protected_switching import waveform_windows as fault_waveform_windows
from switching_buck import switching_cycle


def board_parameters():
    text = (Path(__file__).resolve().parents[1] / "firmware/board_config.h").read_text()
    names = ("P1_PWM_COUNTS", "P1_ADC_REFERENCE_V", "P1_ADC_COUNTS", "P1_VIN_DIVIDER_GAIN",
             "P1_VOUT_DIVIDER_GAIN", "P1_CURRENT_ZERO_V", "P1_CURRENT_GAIN_V_PER_A")
    # 只读取本实验头文件已有的七个十进制字面量，不实现通用 C 配置解析。
    return {name: float(re.search(r"^#define\s+" + name + r"\s+([0-9.]+)", text, re.M).group(1)) for name in names}


BOARD = board_parameters()
CASES = ("startup", "load_step", "overvoltage")
NORMAL_CASES = ("startup", "load_step", "input_step")
FAULT_CASES = ("overcurrent", "overvoltage", "undervoltage")


def quantized_measurements(input_v, output_v, current_a):
    fs, codes = BOARD["P1_ADC_REFERENCE_V"], int(BOARD["P1_ADC_COUNTS"])
    pins = (input_v / BOARD["P1_VIN_DIVIDER_GAIN"], output_v / BOARD["P1_VOUT_DIVIDER_GAIN"],
            BOARD["P1_CURRENT_ZERO_V"] + current_a * BOARD["P1_CURRENT_GAIN_V_PER_A"])
    # 假定理想等宽码箱、向下取整、端点截断；不是实测 ADC 转移曲线。
    raw = [min(codes - 1, max(0, math.floor(pin / fs * codes))) for pin in pins]
    measured = (raw[0] * (fs / codes) * BOARD["P1_VIN_DIVIDER_GAIN"],
                raw[1] * (fs / codes) * BOARD["P1_VOUT_DIVIDER_GAIN"],
                (raw[2] * (fs / codes) - BOARD["P1_CURRENT_ZERO_V"]) / BOARD["P1_CURRENT_GAIN_V_PER_A"])
    return {"raw_vin": raw[0], "raw_vout": raw[1], "raw_current": raw[2],
            "measured_input_v": measured[0], "measured_output_v": measured[1], "measured_current_a": measured[2],
            "vout_below_adc_range": int(pins[1] < 0),
            "any_adc_input_out_of_range": int(any(pin < 0 or pin >= fs for pin in pins))}


def quantized_pwm(duty):
    counts = int(duty * BOARD["P1_PWM_COUNTS"] + 0.5)  # 与固件的非负数转换相同。
    return counts, counts / BOARD["P1_PWM_COUNTS"]


def waveform_windows(case, count):
    if case == "startup":
        return [(0, 15), (990, 1010), (count - 20, count)]
    if case in ("load_step", "input_step"):
        return [(2490, 2530), (count - 20, count)]
    if case in ("overcurrent", "undervoltage"):
        return fault_waveform_windows(case, count)
    return [(2490, 2600), (3990, 4030), (count - 20, count)]


def simulate_io_timing(case, adapted, max_step_s=0.5e-6, controller=None):
    if case not in NORMAL_CASES + FAULT_CASES:
        raise ValueError(case)
    p = replace(Parameters(), duration_s=0.140) if case in FAULT_CASES else Parameters()
    control = controller if controller is not None else ProtectedController(p)
    count = round(p.duration_s / p.control_period_s)
    windows = waveform_windows(case, count)
    current_a = output_v = queued_duty = 0.0
    attempted_active_clear = attempted_residual_clear = False
    counterfactual = None
    samples, cycles, waveform = [], [], []
    for k in range(count + 1):
        injection = case in FAULT_CASES and 2500 <= k < 3250
        input_v = p.stepped_input_v if case == "input_step" and k >= 2500 else p.nominal_input_v
        load_ohm = p.stepped_load_ohm if case == "load_step" and k >= 2500 else p.nominal_load_ohm
        if injection:
            if case == "overcurrent":
                load_ohm = 0.25
            elif case == "overvoltage":
                input_v = 14.0
            else:
                input_v = 4.5
        if adapted:
            adc = quantized_measurements(input_v, output_v, current_a)
        else:
            adc = {"raw_vin": None, "raw_vout": None, "raw_current": None,
                   "measured_input_v": input_v, "measured_output_v": output_v, "measured_current_a": current_a,
                   "vout_below_adc_range": 0, "any_adc_input_out_of_range": 0}
        mv, mo, mi = (adc[key] for key in ("measured_input_v", "measured_output_v", "measured_current_a"))
        active = control.active_faults(mv, mo, mi)
        limit = control.limits
        measured_clearable = not active and abs(mo) <= limit.clear_max_abs_output_v and abs(mi) <= limit.clear_max_abs_current_a
        true_clearable = (not control.active_faults(input_v, output_v, current_a)
                          and abs(output_v) <= limit.clear_max_abs_output_v and abs(current_a) <= limit.clear_max_abs_current_a)
        request = False
        if case in FAULT_CASES:
            if not attempted_active_clear and active:
                request = attempted_active_clear = True
            elif not attempted_residual_clear and control.state == "FAULT_LATCHED" and not active and not measured_clearable:
                request = attempted_residual_clear = True
            if k == 4000:
                request = True
        before = queued_duty
        command = control.update(k, mv, mo, mi, request)
        if adapted:
            cmpa, scheduled = quantized_pwm(command["duty"])
            # 仅 CMPA 更新延迟一拍。检测出的 Trip 在本假定采样时刻立即覆盖旧命令。
            applied = 0.0 if command["state"] == "FAULT_LATCHED" else before
        else:
            cmpa, scheduled, applied = None, command["duty"], command["duty"]
        queued_duty = scheduled
        unsafe_candidate = command["state"] == "FAULT_LATCHED" and measured_clearable and not true_clearable
        if unsafe_candidate and counterfactual is None:
            # 只复制控制器验证一次假想 clear；不应用到主功率级，主轨迹继续锁存。
            shadow = copy.deepcopy(control)
            result = shadow.update(k, mv, mo, mi, True)
            counterfactual = {"time_s": k * p.control_period_s, "true_output_v": output_v,
                              "true_current_a": current_a, "measured_output_v": mo, "measured_current_a": mi,
                              "stored_energy_j": energy_j(current_a, output_v, p),
                              "clear_result_if_requested": result["clear_result"], "applied_to_main_trajectory": False}
        samples.append({"time_s": k * p.control_period_s, "input_v": input_v, "load_ohm": load_ohm,
                        "output_v": output_v, "inductor_current_a": current_a, "load_current_a": output_v / load_ohm,
                        "stored_energy_j": energy_j(current_a, output_v, p), **adc,
                        "injection_active": int(injection), "clear_request": int(request), **command,
                        "controller_duty": command["duty"], "cmpa_counts": cmpa, "next_pwm_duty": scheduled,
                        "previous_pwm_duty": before, "duty": applied,
                        "measured_clear_eligible": int(measured_clearable), "true_clear_eligible": int(true_clearable),
                        "unsafe_clear_candidate": int(unsafe_candidate)})
        if k == count:
            break
        current_a, output_v, cycle, trace = switching_cycle(
            k, current_a, output_v, applied, input_v, load_ohm, p, max_step_s,
            any(a <= k < b for a, b in windows))
        cycles.append({"input_v": input_v, "state": command["state"], **cycle})
        waveform.extend({"input_v": input_v, "state": command["state"], **r} for r in trace)
    return p, samples, cycles, waveform, control.events, counterfactual
