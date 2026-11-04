"""Causal feedback, tracking, anti-windup, protection, and original physics."""

import unittest

from dab_power_loop import scenarios, segment_metrics, simulate_power_loop


class TestPowerLoop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = {name: simulate_power_loop(refs, **options) for name, refs, options in scenarios()}

    def test_feedback_is_from_exactly_previous_completed_period(self):
        for run, controls in self.results.values():
            for k, record in enumerate(controls):
                self.assertEqual(record["feedback_source_period"], k - 1)
                self.assertEqual(record["feedback_w"], 0 if k == 0 else run.periods[k - 1]["p2_w"])
        a, _ = simulate_power_loop([5] * 20 + [20] * 10)
        b, _ = simulate_power_loop([5] * 20 + [-20] * 10)
        self.assertEqual(a.periods[:20], b.periods[:20])

    def test_reachable_steps_and_reversal_settle(self):
        for name in ["step_and_reverse", "saturation_return"]:
            run, controls = self.results[name]
            for metric in segment_metrics(name, run, controls):
                if metric["target_w"] == 100:
                    continue
                with self.subTest(name=name, target=metric["target_w"]):
                    self.assertTrue(metric["settled_in_observed_window"])
                    self.assertLess(abs(metric["tail_mean_error_w"]), metric["tolerance_band_w"])
            self.assertFalse(run.events)
        self.assertLess(self.results["step_and_reverse"][0].periods[-1]["p2_w"], 0)

    def test_saturation_and_conditional_integration(self):
        run, controls = self.results["saturation_return"]
        plateau = controls[140:180]
        self.assertTrue(all(r["amplitude_limited"] for r in plateau))
        self.assertTrue(all(r["integral_frozen"] for r in plateau))
        self.assertEqual(len({r["integral_after_deg"] for r in plateau}), 1)
        metrics = segment_metrics("saturation_return", run, controls)
        self.assertFalse(metrics[1]["settled_in_observed_window"])
        self.assertTrue(metrics[2]["settled_in_observed_window"])
        for records in [c for _, c in self.results.values()]:
            for r in records:
                if r["integral_frozen"]:
                    self.assertEqual(r["integral_change_deg"], 0)
                elif r["controller_mode"] == "active":
                    self.assertAlmostEqual(r["integral_change_deg"], r["integral_proposal_deg"], places=12)

    def test_limits_slew_and_protection_restore(self):
        for run, controls in self.results.values():
            for r in controls:
                self.assertLessEqual(abs(r["actual_phase_deg"]), run.settings.phase_limit_deg)
                if not r["latched_at_end"]:
                    self.assertLessEqual(abs(r["actual_phase_deg"] - r["previous_phase_deg"]),
                                         run.settings.phase_slew_deg_per_period + 1e-12)
        run, controls = self.results["protected_recovery"]
        self.assertEqual([e["event"] for e in run.events], ["trip", "clear_denied", "clear_accepted"])
        self.assertEqual(run.events[0]["reason"], "overcurrent")
        self.assertGreater(abs(run.events[0]["i_a"]), 1.6)
        self.assertNotEqual(run.events[1]["request_deg"], 0)
        self.assertEqual(run.events[2]["request_deg"], 0)
        self.assertTrue(all(r["integral_after_deg"] == 0 for r in controls if r["latched_before_update"]))
        self.assertLess(abs(run.periods[-1]["p2_w"] - 5), 0.25)
        self.assertFalse(run.periods[-1]["latched_at_end"])

    def test_state_continuity_and_unchanged_energy_tolerances(self):
        for run, _ in self.results.values():
            for previous, following in zip(run.rows, run.rows[1:]):
                self.assertEqual(previous["i1_a"], following["i0_a"])
                self.assertEqual(previous["t1_s"], following["t0_s"])
            self.assertLess(max(abs(r["energy_residual_j"]) for r in run.rows), 1e-12)
            self.assertLess(max(abs(r["cumulative_energy_residual_j"]) for r in run.rows), 1e-10)
            self.assertGreaterEqual(min(r["er_j"] for r in run.rows), -1e-15)


if __name__ == "__main__":
    unittest.main(verbosity=2)
