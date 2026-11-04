"""用真实状态、开关电压和能量验证采样保护；沿用既有响应与能量容差。"""

import math
import unittest

from buck_model import metrics
from compare_pi import existing_check_failures
from protected_switching import CASES, simulate_protected_switching
from switching_buck import simulate_switching


class ProtectedSwitchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = {case: simulate_protected_switching(case) for case in CASES}

    def test_normal_load_step_matches_unprotected_pwm(self):
        p, samples, cycles, trace, events = self.results["load_step"]
        _, original, original_cycles, original_trace = simulate_switching("controlled_load_step")
        numeric_samples = [{key: r[key] for key in original[0]} for r in samples]
        self.assertEqual(existing_check_failures(numeric_samples, metrics(samples, "load_step", p), p), [])
        self.assertFalse(any(e["reason"] == "trip" for e in events))
        for a, b in zip(samples, original):
            for key, value in b.items():
                self.assertEqual(a[key], value)
        for actual, old in ((cycles, original_cycles), (trace, original_trace)):
            self.assertEqual(len(actual), len(old))
            for a, b in zip(actual, old):
                for key, value in b.items():
                    self.assertEqual(a[key], value)

    def test_fault_trip_freewheel_clear_and_physical_restart(self):
        causes = {"overcurrent": "OVERCURRENT", "overvoltage": "OUTPUT_OVERVOLTAGE",
                  "undervoltage": "INPUT_UNDERVOLTAGE"}
        for case, cause in causes.items():
            with self.subTest(case=case):
                p, samples, cycles, trace, events = self.results[case]
                self.assertEqual(len(samples), 7001)
                self.assertEqual(len(cycles), 7000)
                self.assertTrue(all(math.isfinite(r[key]) for r in samples
                                    for key in ("output_v", "inductor_current_a", "duty")))
                self.assertTrue(all(0 <= r["duty"] <= p.maximum_duty for r in samples))
                # 由物理量重算首次阈值满足，不依赖 active_faults/state 的自报结果。
                def active(r):
                    return abs(r["inductor_current_a"]) >= 2.5 or r["output_v"] >= 2.4 or r["input_v"] <= 6.0
                first = next(k for k, r in enumerate(samples) if active(r))
                trips = [e for e in events if e["reason"] == "trip"]
                self.assertEqual(len(trips), 1)
                self.assertEqual(trips[0]["time_s"], samples[first]["time_s"])
                self.assertEqual(trips[0]["latched_fault"], cause)
                self.assertTrue(2500 <= first < 3250)
                trip = samples[first]
                self.assertGreater(trip["stored_energy_j"], 1e-4)
                self.assertEqual(trip["clear_result"], "rejected_active_fault")
                latched = samples[first:4000]
                self.assertTrue(all(r["state"] == "FAULT_LATCHED" and r["latched_fault"] == cause
                                    and r["duty"] == 0 and r["reference_v"] == 0 for r in latched))
                self.assertTrue(any(not active(r) and not r["clear_request"] for r in latched))
                self.assertTrue(all(b["stored_energy_j"] <= a["stored_energy_j"] + 1e-12
                                    for a, b in zip(latched, latched[1:])))
                self.assertTrue(all(r["on_time_s"] == 0 for r in cycles[first:4000]))
                off_trace = [r for r in trace if first <= r["cycle"] < 4000]
                self.assertTrue(off_trace)
                self.assertTrue(all(r["switch_voltage_v"] == 0 and r["high_side_on"] == 0 for r in off_trace))
                # 锁存和清除两边 L/C 状态均连续，能量不能随状态转换清零。
                for k in (first, 4000):
                    before = next(r for r in reversed(trace) if r["cycle"] == k - 1)
                    after = next(r for r in trace if r["cycle"] == k)
                    for key in ("output_v", "inductor_current_a"):
                        self.assertEqual(before[key], after[key])
                        self.assertEqual(samples[k][key], after[key])
                self.assertGreater(abs(samples[first + 1]["output_v"]), 0.1)
                # 初始连续续流窗口：独立按电阻功率积分核对状态能量下降。
                window = [r for r in off_trace if r["cycle"] < 2600]
                def energy(r):
                    return p.inductance_h * r["inductor_current_a"]**2 / 2 + p.capacitance_f * r["output_v"]**2 / 2
                self.assertTrue(all(energy(b) <= energy(a) + 1e-12 for a, b in zip(window, window[1:])))
                loss = sum((b["time_s"] - a["time_s"]) *
                           (a["output_v"]**2 / a["load_ohm"] + b["output_v"]**2 / b["load_ohm"]) / 2
                           for a, b in zip(window, window[1:]))
                self.assertLess(abs(energy(window[0]) - energy(window[-1]) - loss) / energy(window[0]), 1e-4)
                rejected = [r for r in samples if r["clear_result"] == "rejected_residual_energy"]
                if case != "undervoltage":
                    self.assertEqual(len(rejected), 1)
                    self.assertFalse(active(rejected[0]))
                    self.assertTrue(abs(rejected[0]["output_v"]) > 0.1 or abs(rejected[0]["inductor_current_a"]) > 0.1)
                    self.assertEqual(rejected[0]["duty"], 0)
                else:
                    # 输入欠压一直保持到 65 ms；恢复时储能已经符合清除条件。
                    self.assertEqual(rejected, [])
                    self.assertEqual(samples[3249]["input_v"], 4.5)
                self.assertEqual(samples[3250]["input_v"], 9.0)
                self.assertEqual(samples[3250]["load_ohm"], 4.0)
                self.assertEqual(samples[3250]["state"], "FAULT_LATCHED")
                clear = samples[4000]
                self.assertEqual([r["time_s"] for r in samples if r["clear_result"] == "accepted"], [0.080])
                self.assertFalse(active(clear))
                self.assertLessEqual(abs(clear["output_v"]), 0.1)
                self.assertLessEqual(abs(clear["inductor_current_a"]), 0.1)
                self.assertEqual(clear["reference_v"], 0)
                self.assertEqual(clear["state"], "SOFT_START")
                self.assertAlmostEqual(samples[4001]["reference_v"], 0.002)
                self.assertEqual(samples[5000]["reference_v"], 2)
                self.assertEqual(samples[5000]["state"], "RUN")
                self.assertGreater(samples[5000]["output_v"], 1.5)
                self.assertAlmostEqual(samples[-1]["output_v"], 2.0, delta=0.02)
                restarted = [r for r in trace if 4000 <= r["cycle"] < 4030]
                self.assertTrue(any(r["switch_voltage_v"] == 9 for r in restarted))
                # 恢复后真实脉冲面积对应占空比，未只修改控制器标签。
                for k in range(4000, 4030):
                    period = [r for r in restarted if r["cycle"] == k]
                    voltage_area = sum((b["time_s"] - a["time_s"]) *
                                       (a["switch_voltage_v"] + b["switch_voltage_v"]) / 2
                                       for a, b in zip(period, period[1:]))
                    self.assertAlmostEqual(voltage_area / p.control_period_s, samples[k]["duty"] * samples[k]["input_v"], delta=1e-8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
