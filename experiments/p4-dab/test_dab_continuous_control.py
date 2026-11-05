"""Closed-loop causality and physical switching/protection boundaries."""

import math
import unittest

from dab_continuous import simulate_continuous
from dab_continuous_control import simulate_continuous_loop, simulate_switching_control
from dab_deadtime import LEGS
from dab_sps import Parameters
from dab_transient import Settings


def assert_physics(test, run):
    for a, b in zip(run.rows, run.rows[1:]):
        test.assertEqual(a["i1_a"], b["i0_a"])
        test.assertEqual(a["t1_s"], b["t0_s"])
        for leg in LEGS:
            test.assertEqual(a[f"v1_{leg}_v"], b[f"v0_{leg}_v"])
    test.assertLess(max(abs(r["energy_residual_j"]) for r in run.rows), 1e-12)
    test.assertLess(max(abs(r["cumulative_energy_residual_j"]) for r in run.rows), 1e-10)
    for event in run.turnons:
        test.assertGreaterEqual(event["actual_off_duration_s"], 150e-9-1e-16)
        test.assertEqual(event["iL_turnon_a"], event["i_after_turnon_a"])


class TestContinuousControl(unittest.TestCase):
    def test_fixed_carrier_has_same_steady_physics(self):
        for v2, phase in ((9, 30), (9, -30), (12, 30), (12, -30)):
            p = Parameters(v2_v=v2)
            old = simulate_continuous(p, 0, phase)
            new = simulate_switching_control(Settings(circuit=p), [phase]*100)
            for key in ("p1_input_w", "p2_output_w", "i_rms_a", "i_mean_a",
                        "resistor_power_w", "diode_power_w", "turnon_redistribution_power_w"):
                self.assertLess(abs(old.periods[-1][key]-new.periods[-1][key]), 1e-6, key)
            self.assertEqual(old.periods[-1]["zvs_in_model"], new.periods[-1]["zvs_in_model"])
            assert_physics(self, new)

    def test_feedback_causality_and_original_limits(self):
        a, control = simulate_continuous_loop([5]*35+[20]*35+[-15]*35)
        b, _ = simulate_continuous_loop([5]*35+[-20]*35)
        self.assertEqual(a.periods[:35], b.periods[:35])
        for k, record in enumerate(control):
            self.assertEqual(record["feedback_source_period"], k-1)
            self.assertEqual(record["feedback_w"], a.periods[k-1]["p2_w"] if k else 0)
            self.assertLessEqual(abs(record["actual_phase_deg"]), 60)
            self.assertLessEqual(abs(record["actual_phase_deg"]-record["previous_phase_deg"]), 6+1e-12)
            rows = [r for r in a.rows if r["period_index"] == k]
            power = -math.fsum(r["source2_energy_j"] for r in rows)*a.settings.circuit.frequency_hz
            self.assertAlmostEqual(record["actual_period_p2_w"], power, places=8)
        assert_physics(self, a)

    def test_fault_during_deadtime_cancels_pending_high_turnon(self):
        # -0.54 deg trips inside dead time; -1.08 deg makes the sample coincide
        # exactly with the pending high turn-on. Protection must win both.
        for phase in (-0.54, -1.08):
            with self.subTest(phase=phase):
                run = simulate_switching_control(Settings(), [phase]*4,
                    sense_v2=lambda turns: 17 if 0.75 <= turns < 1 else 12)
                self.assertEqual(len(run.events), 1)
                self.assertAlmostEqual(run.events[0]["t_s"], 0.75/20000)
                replacements = [e for e in run.gate_events if e["cause"] == "fault_zero_bridge" and e["replaced_pending"]]
                self.assertEqual([e["leg_index"] for e in replacements], [2])
                self.assertTrue(all(e["incoming"] == "low" for e in run.turnons if e["latched"]))
                self.assertTrue(all(run.rows[-1][f"v1_{leg}_v"] == 0 for leg in LEGS))
                assert_physics(self, run)

    def test_overcurrent_explicit_recovery_without_relaxation(self):
        refs = [100]*30+[0]*40+[5]*100
        run, control = simulate_continuous_loop(refs, settings=Settings(overcurrent_a=1.6), clear_cycles=(20, 50))
        self.assertEqual([e["event"] for e in run.events], ["trip", "clear_denied", "clear_accepted"])
        trip, denied, accepted = run.events
        self.assertGreater(abs(trip["i_a"]), 1.6)
        self.assertNotEqual(denied["request_deg"], 0)
        self.assertEqual(accepted["request_deg"], 0)
        self.assertLessEqual(abs(accepted["i_a"]), 0.2)
        self.assertTrue(all(r["latched_at_end"] for r in run.periods[7:50]))
        self.assertLess(abs(sum(r["p2_w"] for r in run.periods[-10:])/10-5), 0.25)
        self.assertTrue(any(e["cause"] == "explicit_reenable" for e in run.gate_events))
        self.assertTrue(all(r["integral_after_deg"] == 0 for r in control if r["latched_before_update"]))
        assert_physics(self, run)

    def test_bus_input_strict_threshold_and_denied_unsafe_clear(self):
        refs = [5]*20+[0]*30+[5]*90
        run, _ = simulate_continuous_loop(refs, clear_cycles=(22, 40),
            sense_v2=lambda turns: 17 if 20.33 <= turns < 25 else 15)
        self.assertEqual([e["event"] for e in run.events], ["trip", "clear_denied", "clear_accepted"])
        self.assertEqual(run.events[0]["reason"], "bus_overvoltage_input")
        self.assertAlmostEqual(run.events[0]["t_s"], 20.35/20000)
        self.assertEqual(run.events[1]["sensed_v2_v"], 17)
        self.assertEqual(run.events[2]["sensed_v2_v"], 15)
        self.assertEqual(run.settings.circuit.v2_v, 12)
        assert_physics(self, run)

    def test_overlapping_and_simultaneous_deadtime_across_reversal(self):
        requests = [0.54]*8+[0]*8+[-0.54]*8
        coarse = simulate_switching_control(Settings(), requests)
        fine = simulate_switching_control(Settings(), requests, deadtime_step_s=10e-9)
        self.assertTrue(all(p["leg_turnons"] == 8 for p in coarse.periods))
        for a, b in zip(coarse.periods, fine.periods):
            self.assertLess(abs(a["p2_w"]-b["p2_w"]), 1e-7)
            self.assertLess(abs(a["i_end_a"]-b["i_end_a"]), 1e-9)
        self.assertTrue(any(sum(r[f"gate_{leg}"] == -1 for leg in LEGS) == 4 for r in coarse.rows))
        assert_physics(self, coarse)


if __name__ == "__main__":
    unittest.main(verbosity=2)
