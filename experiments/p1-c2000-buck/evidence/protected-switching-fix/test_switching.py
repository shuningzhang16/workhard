"""开关模型的定向检查，沿用平均模型原有响应条件。"""

import unittest

from compare_pi import existing_check_failures
from buck_model import metrics
from switching_buck import PWM_FREQUENCY_HZ, simulate_switching, steady_metrics


class SwitchingTests(unittest.TestCase):
    def test_fixed_duty_voltage_switching_and_ripple(self):
        p, _, cycles, trace = simulate_switching("fixed_duty")
        steady = steady_metrics(cycles)
        duty = p.target_v / p.nominal_input_v
        i_pp = (p.nominal_input_v - p.target_v) * duty / (p.inductance_h * PWM_FREQUENCY_HZ)
        v_pp = i_pp / (8 * PWM_FREQUENCY_HZ * p.capacitance_f)
        self.assertEqual(set(r["switch_voltage_v"] for r in trace), {0.0, 9.0})
        self.assertAlmostEqual(steady["output_mean_v"], 2.0, delta=1e-5)
        self.assertAlmostEqual(steady["current_mean_a"], 0.5, delta=1e-5)
        self.assertLess(abs(steady["mean_cycle_current_pp_a"] / i_pp - 1), 0.02)
        self.assertLess(abs(steady["mean_cycle_output_pp_v"] / v_pp - 1), 0.02)
        self.assertLess(steady["cycle_mean_output_span_v"], 1e-5)
        switch_integral = sum((b["time_s"] - a["time_s"]) * (a["switch_voltage_v"] + b["switch_voltage_v"]) / 2
                              for a, b in zip(trace, trace[1:]))
        window = trace[-1]["time_s"] - trace[0]["time_s"]
        self.assertAlmostEqual(switch_integral / window, 9 * duty, delta=1e-8)
        # 边沿左右重复时间点用于表达电压跳变，电感/电容状态必须连续。
        for a, b in zip(trace, trace[1:]):
            if abs(a["time_s"] - b["time_s"]) < 1e-14:
                self.assertEqual(a["output_v"], b["output_v"])
                self.assertEqual(a["inductor_current_a"], b["inductor_current_a"])

    def test_controlled_disturbance_and_step_refinement(self):
        p, samples, cycles, _ = simulate_switching("controlled_load_step")
        _, fine, fine_cycles, _ = simulate_switching("controlled_load_step", 0.25e-6)
        self.assertEqual(samples[2499]["load_ohm"], 4.0)
        self.assertEqual(samples[2500]["load_ohm"], 2.0)
        self.assertEqual(existing_check_failures(samples, metrics(samples, "load_step", p), p), [])
        self.assertEqual(existing_check_failures(fine, metrics(fine, "load_step", p), p), [])
        self.assertTrue(all(a["time_s"] == b["time_s"] for a, b in zip(samples, fine)))
        self.assertLess(max(abs(a["output_v"] - b["output_v"]) for a, b in zip(samples, fine)), 1e-6)
        a, b = steady_metrics(cycles), steady_metrics(fine_cycles)
        self.assertLess(abs(a["mean_cycle_output_pp_v"] / b["mean_cycle_output_pp_v"] - 1), 0.01)


if __name__ == "__main__":
    unittest.main(verbosity=2)
