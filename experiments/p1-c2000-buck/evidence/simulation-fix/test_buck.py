"""必要自检：独立的开环稳态关系，以及三个闭环响应的有限时域检查。"""

import math
import unittest

from buck_model import Parameters, metrics, plant_step, simulate


class BuckTests(unittest.TestCase):
    def test_open_loop_duty_relation(self):
        # 不调用 PI 或软启动；从零状态积分，检查独立解析关系 Vout=D*Vin, I=V/R。
        p = Parameters()
        current_a = output_v = 0.0
        duty = 0.25
        dt = 5e-6
        for _ in range(round(0.060 / dt)):
            current_a, output_v = plant_step(current_a, output_v, duty, 9.0, 4.0, p, dt)
        print(f"open_loop: Vout={output_v:.12f} V, expected=2.25 V; I={current_a:.12f} A, expected=0.5625 A")
        self.assertAlmostEqual(output_v, 2.25, delta=1e-5)
        self.assertAlmostEqual(current_a, 0.5625, delta=1e-5)

    def test_three_closed_loop_cases(self):
        p = Parameters()
        for case in ("startup", "load_step", "input_step"):
            with self.subTest(case=case):
                rows = simulate(case, p)
                result = metrics(rows, case, p)
                self.assertEqual(len(rows), 5001)
                self.assertTrue(all(math.isfinite(value) for row in rows for value in row.values()))
                self.assertTrue(all(0 <= r["duty"] <= p.maximum_duty for r in rows))
                self.assertEqual(rows[0]["reference_v"], 0)
                self.assertAlmostEqual(rows[1000]["reference_v"], p.target_v)
                self.assertLess(abs(result["steady_state_error_v"]), 0.02)
                self.assertLess(result["overshoot_percent"], 10)
                self.assertLess(result["post_event_max_abs_deviation_v"], 0.5)
                self.assertIsNotNone(result["recovery_to_2_percent_s"])
                self.assertLess(result["recovery_to_2_percent_s"], 0.030)


if __name__ == "__main__":
    unittest.main(verbosity=2)
