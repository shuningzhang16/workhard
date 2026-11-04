"""EPS timing, physical invariants, SPS equivalence, and power matching."""

import math
import unittest

from dab_sps import Parameters, analytical_power, simulate
from dab_eps import POWER_MATCH_TOL_W, match_power, search_eps, simulate_eps, timing_rows


class TestEPS(unittest.TestCase):
    def test_alpha_zero_reproduces_sps_waveforms(self):
        for ratio in [0.75, 1, 1.25]:
            for phase in [-90, -30, 0, 17.3, 90]:
                with self.subTest(ratio=ratio, phase=phase):
                    p = Parameters(v2_v=12 * ratio)
                    sps, eps = simulate(p, phase), simulate_eps(p, 0, phase)
                    self.assertEqual(sps.segments, eps.segments)
                    for key in eps.metrics:
                        self.assertAlmostEqual(eps.metrics[key], sps.metrics[key], places=12)

    def test_zero_levels_are_built_from_legs(self):
        p = Parameters()
        rows = list(timing_rows(simulate_eps(p, 60, 20), 60))
        self.assertEqual({r["v1_v"] for r in rows}, {-24, 0, 24})
        self.assertEqual({r["v2_prime_v"] for r in rows}, {-24, 24})
        duration = rows[-1]["t1_s"]
        zero_duration = math.fsum(r["t1_s"] - r["t0_s"] for r in rows if r["v1_v"] == 0)
        self.assertAlmostEqual(zero_duration / duration, 60 / 180, places=12)
        for row in rows:
            self.assertEqual(row["v1_v"], p.v1_v * (row["q1a_high"] - row["q1b_high"]))
            self.assertEqual(row["v2_prime_v"], p.turns_ratio * p.v2_v * (row["q2a_high"] - row["q2b_high"]))
            self.assertEqual(row["q2a_high"] + row["q2b_high"], 1)

    def test_physics_and_independent_superposition_power(self):
        for ratio in [0.75, 1, 1.25]:
            p = Parameters(v2_v=12 * ratio)
            for alpha in [0, 60, 120, 180]:
                for phase in [-90, -17.3, 0, 30, 90]:
                    with self.subTest(ratio=ratio, alpha=alpha, phase=phase):
                        c = simulate_eps(p, alpha, phase)
                        expected = (analytical_power(p, phase + alpha / 2)
                                    + analytical_power(p, phase - alpha / 2)) / 2
                        self.assertLess(abs(c.metrics["p2_time_w"] - expected), 1e-9)
                        for key in ["power_balance_w", "periodic_error_a", "i_mean_a"]:
                            self.assertLess(abs(c.metrics[key]), 1e-9, key)
                        if alpha < 180 and phase != 0:
                            self.assertGreater(c.metrics["p2_time_w"] * phase, 0)

    def test_direction_symmetry_at_nonzero_internal_shift(self):
        p = Parameters(v2_v=9)
        fwd, rev = simulate_eps(p, 75, 17.3), simulate_eps(p, 75, -17.3)
        self.assertAlmostEqual(fwd.metrics["p2_time_w"], -rev.metrics["p2_time_w"], places=10)
        for key in ["i_rms_a", "i_peak_a"]:
            self.assertAlmostEqual(fwd.metrics[key], rev.metrics[key], places=10)

    def test_matching_and_finite_search_objective(self):
        for ratio in [0.75, 1, 1.25]:
            p = Parameters(v2_v=12 * ratio)
            maximum = analytical_power(p, 90)
            for fraction in [0.1, 0.5]:
                for direction in [-1, 1]:
                    target = direction * fraction * maximum
                    with self.subTest(ratio=ratio, target=target):
                        best, rows = search_eps(p, target)
                        self.assertIsNotNone(best)
                        alpha, cycle = best
                        self.assertLess(abs(cycle.metrics["p2_time_w"] - target), POWER_MATCH_TOL_W)
                        feasible = [r for r in rows if r["status"] == "matched"]
                        self.assertEqual(cycle.metrics["i_rms_a"], min(r["i_rms_a"] for r in feasible))
                        sps = next(r for r in rows if r["alpha_deg"] == 0)
                        self.assertLessEqual(cycle.metrics["i_rms_a"], sps["i_rms_a"] + 1e-12)
                        self.assertIn(alpha, range(0, 181, 15))

    def test_unreachable_targets_are_not_reported_as_matches(self):
        p = Parameters()
        for target in [-39.6, 39.6]:
            best, rows = search_eps(p, target)
            self.assertIsNone(best)
            self.assertTrue(all(r["status"] == "no_match_in_branch" for r in rows))
        self.assertIsNone(match_power(p, 3.6, 180)[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
