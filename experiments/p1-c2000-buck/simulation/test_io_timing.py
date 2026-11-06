"""定向验证延迟/量化接线、真实 PWM 与负压清除盲区；不修改原判据。"""

import math
import unittest

from buck_model import metrics
from compare_pi import existing_check_failures
from io_timing_buck import BOARD, CASES, quantized_measurements, quantized_pwm, simulate_io_timing
from protected_switching import simulate_protected_switching
from run_io_timing import NUMERIC_COLUMNS


class IOTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = {(case, adapted): simulate_io_timing(case, adapted) for case in CASES for adapted in (False, True)}

    def test_quantizer_endpoints_and_original_model_reuse(self):
        adc = quantized_measurements(16.5, 3.3, 0.0)
        self.assertEqual([adc[k] for k in ("raw_vin", "raw_vout", "raw_current")], [2048, 2048, 2048])
        self.assertEqual(adc["measured_output_v"], 3.3)
        self.assertEqual(adc["measured_current_a"], 0.0)
        adc = quantized_measurements(100.0, -1.9, -30.0)
        self.assertEqual([adc[k] for k in ("raw_vin", "raw_vout", "raw_current")], [4095, 0, 0])
        self.assertEqual(adc["measured_output_v"], 0.0)
        self.assertEqual(quantized_pwm(0.00025), (1, 0.0005))
        self.assertEqual(quantized_pwm(0.95), (1900, 0.95))
        for case in ("load_step", "overvoltage"):
            _, old, _, _, old_events = simulate_protected_switching(case)
            _, rows, _, _, events, _ = self.runs[case, False]
            self.assertEqual(events, old_events)
            self.assertEqual(len(rows), len(old))
            for a, b in zip(rows, old):
                for key in b:
                    self.assertEqual(a[key], b[key])

    def test_one_period_delay_and_actual_voltage_pulses(self):
        for case in CASES:
            with self.subTest(case=case):
                p, rows, _, wave, _, _ = self.runs[case, True]
                self.assertEqual(rows[0]["duty"], 0.0)
                for k, row in enumerate(rows):
                    expected = 0.0 if k == 0 or row["state"] == "FAULT_LATCHED" else math.floor(rows[k - 1]["controller_duty"] * 2000 + 0.5) / 2000
                    self.assertEqual(row["duty"], expected)
                    self.assertLessEqual(abs(row["next_pwm_duty"] - row["controller_duty"]), 1 / (2 * BOARD["P1_PWM_COUNTS"]) + 1e-15)
                    for key in ("raw_vin", "raw_vout", "raw_current"):
                        self.assertTrue(0 <= row[key] <= 4095)
                periods = {}
                for node in wave:
                    periods.setdefault(node["cycle"], []).append(node)
                for k, trace in periods.items():
                    area = sum((b["time_s"] - a["time_s"]) * (a["switch_voltage_v"] + b["switch_voltage_v"]) / 2
                               for a, b in zip(trace, trace[1:]))
                    self.assertAlmostEqual(area / p.control_period_s, rows[k]["duty"] * rows[k]["input_v"], delta=1e-8)
                if case != "overvoltage":
                    numeric = [{key: r[key] for key in NUMERIC_COLUMNS} for r in rows]
                    self.assertEqual(existing_check_failures(numeric, metrics(rows, case, p), p), [])

    def test_trip_override_energy_and_unipolar_clear_blind_spot(self):
        _, rows, _, wave, events, shadow = self.runs["overvoltage", True]
        trips = [r for r in events if r["reason"] == "trip"]
        self.assertEqual(len(trips), 1)
        first = next(k for k, r in enumerate(rows) if r["state"] == "FAULT_LATCHED")
        self.assertGreater(rows[first]["previous_pwm_duty"], 0)
        self.assertEqual(rows[first]["duty"], 0)
        off = [r for r in wave if first <= r["cycle"] < 4000]
        self.assertTrue(off)
        self.assertTrue(all(r["switch_voltage_v"] == 0 and r["high_side_on"] == 0 for r in off))
        before = next(r for r in reversed(wave) if r["cycle"] == first - 1)
        after = next(r for r in wave if r["cycle"] == first)
        self.assertEqual(before["output_v"], after["output_v"])
        self.assertEqual(before["inductor_current_a"], after["inductor_current_a"])
        latched = rows[first:4000]
        self.assertTrue(all(b["stored_energy_j"] <= a["stored_energy_j"] + 1e-12 for a, b in zip(latched, latched[1:])))
        self.assertLess(min(r["output_v"] for r in latched), -1.0)
        self.assertEqual([r["time_s"] for r in rows if r["clear_result"] == "accepted"], [])
        self.assertTrue(rows[4000]["true_clear_eligible"])
        self.assertEqual(rows[4000]["reference_v"], 0)
        self.assertEqual(rows[4000]["clear_result"], "rejected_unobservable_measurement")
        self.assertEqual(rows[-1]["state"], "FAULT_LATCHED")
        self.assertEqual(rows[4001]["reference_v"], 0)
        self.assertEqual(shadow["clear_result_if_requested"], "rejected_unobservable_measurement")
        self.assertFalse(shadow["applied_to_main_trajectory"])
        self.assertLess(shadow["true_output_v"], -1.0)
        self.assertGreater(shadow["stored_energy_j"], 0.0005)
        self.assertEqual(shadow["measured_output_v"], 0)
        original = next(r for r in rows if r["time_s"] == shadow["time_s"])
        self.assertEqual(original["state"], "FAULT_LATCHED")
        self.assertEqual(original["clear_request"], 0)
        self.assertEqual(original["duty"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
