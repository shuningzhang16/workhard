"""定向验证：无误触发、持续检测故障拒绝清除、锁存、恢复及续流能量。"""

import unittest

from buck_model import Parameters, plant_step, simulate
from protection import ProtectedController, energy_j, simulate_protected


class ProtectionTests(unittest.TestCase):
    def test_normal_cases_unchanged(self):
        for case in ("startup", "load_step", "input_step"):
            with self.subTest(case=case):
                _, protected, events = simulate_protected(case)
                original = simulate(case)
                self.assertEqual(len(protected), len(original))
                self.assertFalse(any(e["reason"] == "trip" for e in events))
                for before, after in zip(original, protected):
                    for key in ("output_v", "inductor_current_a", "duty", "reference_v"):
                        self.assertEqual(before[key], after[key])

    def test_active_fault_rejects_clear_and_no_automatic_restart(self):
        for input_v, output_v, current_a, cause in (
            (9.0, 2.0, 2.5, "OVERCURRENT"),
            (9.0, 2.0, -2.5, "OVERCURRENT"),
            (9.0, 2.4, 0.5, "OUTPUT_OVERVOLTAGE"),
            (6.0, 2.0, 0.5, "INPUT_UNDERVOLTAGE"),
        ):
            with self.subTest(cause=cause, current_a=current_a):
                c = ProtectedController()
                for k in range(3):
                    result = c.update(k, input_v, output_v, current_a, clear_request=True)
                    self.assertEqual(result["state"], "FAULT_LATCHED")
                    self.assertEqual(result["latched_fault"], cause)
                    self.assertEqual(result["clear_result"], "rejected_active_fault")
                    self.assertEqual(result["duty"], 0)
                result = c.update(3, 9.0, 0.0, 0.0)
                self.assertEqual(result["state"], "FAULT_LATCHED")
                result = c.update(4, 9.0, 0.2, 0.0, clear_request=True)
                self.assertEqual(result["clear_result"], "rejected_residual_energy")
                result = c.update(5, 9.0, 0.0, 0.0, clear_request=True)
                self.assertEqual(result["state"], "SOFT_START")
                self.assertEqual(result["clear_result"], "accepted")
                self.assertEqual(result["reference_v"], 0)
                self.assertEqual(c.pi.integral, 0)

    def test_physical_injections_latch_and_restart(self):
        for case, cause in (("overcurrent", "OVERCURRENT"),
                            ("overvoltage", "OUTPUT_OVERVOLTAGE"),
                            ("undervoltage", "INPUT_UNDERVOLTAGE")):
            with self.subTest(case=case):
                p, rows, events = simulate_protected(case)
                trips = [e for e in events if e["reason"] == "trip"]
                self.assertEqual(len(trips), 1)
                self.assertEqual(trips[0]["latched_fault"], cause)
                self.assertGreaterEqual(trips[0]["time_s"], 0.050)
                self.assertLess(trips[0]["time_s"], 0.065)
                self.assertEqual(sum(r["clear_result"] == "rejected_active_fault" for r in rows), 1)
                self.assertTrue(all(r["state"] == "FAULT_LATCHED" and r["duty"] == 0
                                    for r in rows if trips[0]["time_s"] <= r["time_s"] < 0.080))
                restart = round(0.080 / p.control_period_s)
                self.assertEqual(rows[restart]["clear_result"], "accepted")
                self.assertEqual(rows[restart]["reference_v"], 0)
                self.assertAlmostEqual(rows[restart + 1]["reference_v"], 0.002)
                self.assertEqual(rows[restart + 1000]["state"], "RUN")
                self.assertEqual(rows[restart + 1000]["reference_v"], 2.0)
                self.assertLess(abs(rows[-1]["output_v"] - p.target_v), 0.02)
                fault_rows = [r for r in rows if r["state"] == "FAULT_LATCHED"]
                self.assertTrue(all(b["stored_energy_j"] <= a["stored_energy_j"] + 1e-12
                                    for a, b in zip(fault_rows, fault_rows[1:])))

    def test_freewheel_energy_balance(self):
        # 故障续流应保留储能并在负载耗散；离线理想模型允许反向电流。
        p = Parameters()
        i, v = 0.5, 2.0
        initial = energy_j(i, v, p)
        loss = 0.0
        minimum_current = i
        dt = 5e-6
        for _ in range(4000):
            next_i, next_v = plant_step(i, v, 0.0, 9.0, 4.0, p, dt)
            self.assertLessEqual(energy_j(next_i, next_v, p), energy_j(i, v, p) + 1e-12)
            loss += (v*v + next_v*next_v) / (2 * 4.0) * dt
            i, v = next_i, next_v
            minimum_current = min(minimum_current, i)
        residual = initial - energy_j(i, v, p) - loss
        print(f"freewheel: initial={initial:.12g} J, final={energy_j(i, v, p):.12g} J, "
              f"load_loss={loss:.12g} J, balance_residual={residual:.12g} J, min_i={minimum_current:.6g} A")
        self.assertLess(abs(residual) / initial, 1e-4)
        self.assertLess(minimum_current, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
