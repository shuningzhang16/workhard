"""Checks for retained state, analytic RL dynamics, and sampled fault behavior."""

import math
import unittest

from dab_transient import Settings, rl_step, run_teaching_scenarios, simulate_transient


class TestTransient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = run_teaching_scenarios()

    def test_rl_exact_dc_decay_and_composition(self):
        inductance, resistance, dt = 100e-6, 0.5, 20e-6
        i1, area, square = rl_step(2, 0, dt, inductance, resistance)
        self.assertAlmostEqual(i1, 2 * math.exp(-resistance * dt / inductance), places=12)
        self.assertAlmostEqual(resistance * square,
                               0.5 * inductance * (2**2 - i1**2), places=12)
        i1, area, square = rl_step(3, 1.5, dt, inductance, resistance)
        self.assertAlmostEqual(i1, 3, places=12)
        self.assertAlmostEqual(area, 3 * dt, places=12)
        self.assertAlmostEqual(square, 9 * dt, places=12)
        full = rl_step(-0.6, 48, dt, inductance, resistance)
        first = rl_step(-0.6, 48, dt / 2, inductance, resistance)
        second = rl_step(first[0], 48, dt / 2, inductance, resistance)
        self.assertAlmostEqual(full[0], second[0], places=12)
        self.assertAlmostEqual(full[1], first[1] + second[1], places=12)
        self.assertAlmostEqual(full[2], first[2] + second[2], places=12)

    def test_constant_condition_converges_to_rl_periodic_solution(self):
        run = self.runs["constant_forward"]
        p, resistance = run.settings.circuit, run.settings.series_resistance_ohm
        tau, period = p.inductance_h / resistance, 1 / p.frequency_hz
        delta = period * 30 / 360
        # Half-cycle map for matched voltages: +48V for delta, then 0V.
        forcing = (2 * p.v1_v / resistance * (-math.expm1(-delta / tau))
                   * math.exp(-(period / 2 - delta) / tau))
        expected_i0 = -forcing / (1 + math.exp(-period / (2 * tau)))
        self.assertLess(abs(run.rows[-1]["i1_a"] - expected_i0), 1e-9)
        self.assertEqual(run.rows[0]["i0_a"], 0.37)
        self.assertGreater(abs(run.periods[0]["i_mean_a"]), 0.1)
        self.assertGreater(run.periods[-1]["p2_w"], 0)
        self.assertLess(abs(run.periods[-1]["i_mean_a"]), 1e-9)

    def test_reversal_and_exact_state_continuity(self):
        for run in self.runs.values():
            for previous, following in zip(run.rows, run.rows[1:]):
                self.assertEqual(previous["i1_a"], following["i0_a"])
                self.assertEqual(previous["t1_s"], following["t0_s"])
        run = self.runs["direction_reversal"]
        self.assertFalse(run.events)
        self.assertGreater(run.periods[59]["p2_w"], 0)
        self.assertLess(run.periods[-1]["p2_w"], 0)
        phases = [0] + [r["scheduled_phase_deg"] for r in run.periods]
        self.assertTrue(all(abs(b - a) <= 6 for a, b in zip(phases, phases[1:])))
        self.assertTrue(all(abs(x) <= 60 for x in phases))
        oc = self.runs["overcurrent_recovery"]
        self.assertEqual(oc.periods[0]["request_deg"], 120)
        self.assertEqual(oc.periods[0]["limited_target_deg"], 60)

    def test_overcurrent_latches_requires_explicit_clear_and_dissipates(self):
        run = self.runs["overcurrent_recovery"]
        self.assertEqual([e["event"] for e in run.events], ["trip", "clear_denied", "clear_accepted"])
        trip, _, clear = run.events
        self.assertEqual(trip["reason"], "overcurrent")
        self.assertGreater(abs(trip["i_a"]), run.settings.overcurrent_a)
        stopped = [r for r in run.rows if trip["t_s"] <= r["t0_s"] < clear["t_s"]]
        self.assertTrue(stopped)
        for row in stopped:
            self.assertEqual(row["latched"], 1)
            self.assertEqual(row["v1_v"], 0)
            self.assertEqual(row["v2_prime_v"], 0)
            self.assertLessEqual(abs(row["i1_a"]), abs(row["i0_a"]))
        lost_energy = stopped[0]["inductor_e0_j"] - stopped[-1]["inductor_e1_j"]
        self.assertLess(abs(lost_energy - math.fsum(r["er_j"] for r in stopped)), 1e-12)
        self.assertTrue(any(r["latched"] and not r["active_fault"] for r in run.samples))
        self.assertEqual(clear["request_deg"], 0)
        self.assertLessEqual(abs(clear["i_a"]), run.settings.clear_current_a)
        self.assertFalse(run.periods[-1]["latched_at_end"])
        self.assertLess(run.periods[-1]["p2_w"], 0)

    def test_bus_input_detection_is_sampled_and_does_not_change_plant(self):
        run = self.runs["bus_input_recovery"]
        trip, denied, cleared = run.events
        self.assertEqual(trip["reason"], "bus_overvoltage_input")
        period = 1 / run.settings.circuit.frequency_hz
        self.assertGreaterEqual(trip["t_s"], 20.33 * period)
        self.assertLessEqual(trip["t_s"] - 20.33 * period, period / run.settings.samples_per_period)
        self.assertEqual(denied["event"], "clear_denied")
        self.assertEqual(denied["sensed_v2_v"], 17)
        self.assertEqual(cleared["event"], "clear_accepted")
        self.assertEqual({r["v2_prime_v"] for r in run.rows}, {-24, 0, 24})
        self.assertEqual(run.settings.circuit.v2_v, 12)

    def test_fast_recovery_still_retrips_without_relaxing_threshold(self):
        run = simulate_transient(Settings(overcurrent_a=1.6),
                                 [120.0] * 20 + [0.0] * 30 + [-30.0] * 50,
                                 clear_cycles=(10, 40))
        self.assertEqual([e["event"] for e in run.events],
                         ["trip", "clear_denied", "clear_accepted", "trip"])
        self.assertGreater(abs(run.events[-1]["i_a"]), 1.6)
        self.assertTrue(run.periods[-1]["latched_at_end"])

    def test_independent_energy_ledger(self):
        for name, run in self.runs.items():
            with self.subTest(name=name):
                self.assertLess(max(abs(r["energy_residual_j"]) for r in run.rows), 1e-12)
                self.assertLess(max(abs(r["cumulative_energy_residual_j"]) for r in run.rows), 1e-10)
                self.assertGreaterEqual(min(r["er_j"] for r in run.rows), -1e-15)
                energy_change = run.rows[-1]["inductor_e1_j"] - run.rows[0]["inductor_e0_j"]
                net = math.fsum(r["e1_j"] - r["e2_j"] - r["er_j"] for r in run.rows)
                self.assertLess(abs(net - energy_change), 1e-10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
