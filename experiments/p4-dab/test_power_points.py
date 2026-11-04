"""Physical continuity, causal feedback, and unchanged voltage protection."""

import math
import unittest

from dab_power_loop import simulate_power_loop
from dab_sps import Parameters
from dab_transient import Settings
from run_power_points import parameter_points, references


class TestPowerPoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = {name: simulate_power_loop(references(), settings=settings)
                       for name, settings in parameter_points()}

    def test_actual_fixed_buses_and_causal_feedback(self):
        for name, (run, control) in self.results.items():
            with self.subTest(point=name):
                p = run.settings.circuit
                self.assertEqual(len(run.periods), 800)
                self.assertEqual({s["sensed_v2_v"] for s in run.samples}, {p.v2_v})
                for row in run.rows:
                    if not row["latched"]:
                        self.assertEqual(abs(row["v1_v"]), p.v1_v)
                        self.assertEqual(abs(row["v2_prime_v"]), p.turns_ratio * p.v2_v)
                for k, record in enumerate(control):
                    self.assertEqual(record["feedback_source_period"], k - 1)
                    self.assertEqual(record["feedback_w"], 0 if k == 0 else run.periods[k - 1]["p2_w"])
                    self.assertLessEqual(abs(record["actual_phase_deg"]), 60)
                    if not record["latched_at_end"]:
                        self.assertLessEqual(abs(record["actual_phase_deg"] - record["previous_phase_deg"]), 6 + 1e-12)

    def test_retained_state_and_original_energy_tolerances(self):
        for name, (run, _) in self.results.items():
            with self.subTest(point=name):
                self.assertEqual(run.rows[0]["i0_a"], 0)
                for a, b in zip(run.rows, run.rows[1:]):
                    self.assertEqual(a["i1_a"], b["i0_a"])
                    self.assertEqual(a["t1_s"], b["t0_s"])
                self.assertLess(max(abs(r["energy_residual_j"]) for r in run.rows), 1e-12)
                self.assertLess(max(abs(r["cumulative_energy_residual_j"]) for r in run.rows), 1e-10)
                self.assertGreaterEqual(min(r["er_j"] for r in run.rows), -1e-15)

    def test_original_strict_voltage_boundary(self):
        boundary, _ = self.results["v2_15_r_0p5"]
        self.assertEqual(boundary.settings.sensed_v2_limit_v, 15)
        self.assertEqual(boundary.settings.overcurrent_a, 8)
        self.assertFalse(any(e["reason"] == "bus_overvoltage_input" for e in boundary.events))
        self.assertTrue(all(s["sensed_v2_v"] == 15 for s in boundary.samples))
        # One-period detector check, not an additional parameter performance run.
        over, _ = simulate_power_loop([5], settings=Settings(circuit=Parameters(v2_v=15)),
                                     sense_v2=lambda _: math.nextafter(15.0, math.inf))
        self.assertEqual([(e["event"], e["reason"]) for e in over.events],
                         [("trip", "bus_overvoltage_input")])
        self.assertTrue(over.periods[-1]["latched_at_end"])
        self.assertTrue(all(r["v1_v"] == r["v2_prime_v"] == 0 for r in over.rows))


if __name__ == "__main__":
    unittest.main(verbosity=2)
