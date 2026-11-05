"""Receiver-side matching and independent loss accounting invariants."""

import math
import unittest

from dab_continuous import ContinuousRun, simulate_continuous
from dab_loss_budget import MATCH_TOL_W, loss_budget, match_actual_power, tail_metrics
from dab_sps import Parameters


class TestLossBudget(unittest.TestCase):
    def test_match_uses_receiver_in_both_directions(self):
        p = Parameters(v2_v=9)
        for direction in (1, -1):
            phase = direction*8.0
            reference = simulate_continuous(p, 75, phase)
            tail = reference.periods[-10:]
            target = math.fsum(r["p2_output_w"] if direction == 1 else -r["p1_input_w"] for r in tail)/10
            matched = match_actual_power(p, 75, target, 150e-9, (phase-1, phase+1), direction=direction)
            self.assertEqual(matched.status, "matched")
            self.assertLessEqual(abs(tail_metrics(matched.result, direction)["received_power_w"]-target), MATCH_TOL_W)
            self.assertTrue(matched.evaluations[-1]["period_converged"])
            if direction == -1:
                metrics = tail_metrics(matched.result, direction)
                self.assertAlmostEqual(metrics["received_power_w"], -metrics["p1_input_w"])
                self.assertGreater(-metrics["p2_output_w"], metrics["received_power_w"]+0.01)

    def test_unmatched_interval_does_not_fabricate_a_result(self):
        matched = match_actual_power(Parameters(v2_v=9), 0, 100, 150e-9, (5, 10))
        self.assertEqual(matched.status, "no_match_in_selected_interval")
        self.assertIsNone(matched.result)
        self.assertIsNone(matched.phase_deg)
        self.assertEqual(len(matched.evaluations), 2)
        self.assertTrue(all(r["received_power_w"] < 100 for r in matched.evaluations))

    def test_gate_counts_on_time_and_no_duplicate_capacitor_loss(self):
        p, deadtime = Parameters(v2_v=9), 150e-9
        result = simulate_continuous(p, 75, 8, deadtime_s=deadtime)
        periods_before = [dict(r) for r in result.periods]
        totals, devices = loss_budget(result, p, 75, 8)
        typical = next(r for r in totals if r["parameter_case"] == "typical_25C")
        maximum = next(r for r in totals if r["parameter_case"] == "listed_max_25C")
        self.assertAlmostEqual(typical["gate_charge_postprocess_w"], 0.0656, places=12)
        self.assertAlmostEqual(maximum["gate_charge_postprocess_w"], 0.0848, places=12)
        typical_devices = [r for r in devices if r["parameter_case"] == "typical_25C"]
        self.assertEqual([r["turnons"] for r in typical_devices], [10]*8)
        for leg in ("1a", "1b", "2a", "2b"):
            on_time = sum(r["on_time_s"] for r in typical_devices if r["device"].startswith(leg))
            self.assertAlmostEqual(on_time, 10*(1/p.frequency_hz-2*deadtime), places=12)
        model_port_loss = math.fsum(r["p1_input_w"]-r["p2_output_w"] for r in result.periods[-10:])/10
        self.assertLess(abs(typical["plant_model_loss_w"]-model_port_loss), 1e-8)
        tail_rows = [r for r in result.rows if r["period_index"] >= 90]
        hypothetical_always_on = 2*(1+p.turns_ratio**2)*1.8e-3*sum(r["integral_i2_a2_s"] for r in tail_rows)/(10/p.frequency_hz)
        self.assertLess(typical["channel_conduction_postprocess_w"], hypothetical_always_on)
        changed_diagnostic = ContinuousRun(result.rows, result.periods,
            [{**e, "residual_coss_energy_j": e["residual_coss_energy_j"]+1} for e in result.turnons])
        changed_totals, _ = loss_budget(changed_diagnostic, p, 75, 8)
        self.assertEqual([r["partial_loss_budget_w"] for r in totals], [r["partial_loss_budget_w"] for r in changed_totals])
        self.assertEqual(periods_before, result.periods)


if __name__ == "__main__":
    unittest.main(verbosity=2)
