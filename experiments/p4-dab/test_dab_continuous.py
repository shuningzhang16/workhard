"""Continuous-state RLC, charge redistribution, settling and RL limit."""

import math
import unittest

from dab_continuous import simulate_continuous
from dab_deadtime import Device, LEGS, edge_windows, simulate_window
from dab_eps import simulate_eps
from dab_sps import Parameters, simulate
from dab_transient import Settings, simulate_transient


class TestContinuous(unittest.TestCase):
    def test_damped_commutation_against_independent_rk4(self):
        p, device, resistance = Parameters(), Device(), 0.5
        window = edge_windows(simulate(p, 30), 0)[0]
        state = [window["initial_current_a"], 0.0, 24.0, 0.0, 12.0, 0.0]
        factors = (1, -1, -2, 2)
        def derivative(y):
            return [(sum(a*v for a, v in zip(factors, y[1:5])) - resistance*y[0]) / p.inductance_h] + [
                -factors[j]*y[0]/(2*device.coss_f) if j in window["switched"] else 0 for j in range(4)] + [resistance*y[0]**2]
        dt = 0.1e-9
        for _ in range(200):
            a = derivative(state)
            b = derivative([x+dt*v/2 for x, v in zip(state, a)])
            c = derivative([x+dt*v/2 for x, v in zip(state, b)])
            d = derivative([x+dt*v for x, v in zip(state, c)])
            state = [x+dt*(w+2*y+2*z+v)/6 for x, w, y, z, v in zip(state, a, b, c, d)]
        rows, _ = simulate_window(window, 20e-9, resistance_ohm=resistance, sample_step_s=20e-9)
        self.assertAlmostEqual(state[0], rows[-1]["i1_a"], places=10)
        for j, leg in enumerate(LEGS):
            self.assertAlmostEqual(state[j+1], rows[-1][f"v1_{leg}_v"], places=9)
        self.assertLess(abs(state[-1] - math.fsum(r["resistor_energy_j"] for r in rows)), 1e-16)

    def test_continuity_and_pair_capacitor_turnon_energy(self):
        run = simulate_continuous(Parameters(), 0, 30, period_count=4)
        for a, b in zip(run.rows, run.rows[1:]):
            self.assertEqual(a["i1_a"], b["i0_a"])
            self.assertEqual(a["t1_s"], b["t0_s"])
            for leg in LEGS:
                self.assertEqual(a[f"v1_{leg}_v"], b[f"v0_{leg}_v"])
        for row in run.rows:
            if row["kind"] == "turnon_charge":
                self.assertEqual(row["t0_s"], row["t1_s"])
                self.assertEqual(row["i0_a"], row["i1_a"])
                expected = Device().coss_f * sum((row[f"v1_{leg}_v"]-row[f"v0_{leg}_v"])**2 for leg in LEGS)
                self.assertAlmostEqual(row["turnon_redistribution_energy_j"], expected, places=15)
        for event in run.turnons[:2]:
            self.assertEqual(event["iL_initial_a"], 0)
            self.assertAlmostEqual(event["turnon_redistribution_energy_j"], Device().coss_f*24**2, places=15)
            self.assertAlmostEqual(event["turnon_redistribution_energy_j"], 2*event["residual_coss_energy_j"], places=15)
        self.assertLess(max(abs(r["energy_residual_j"]) for r in run.rows), 1e-12)
        self.assertLess(max(abs(r["cumulative_energy_residual_j"]) for r in run.rows), 1e-10)

    def test_two_initial_currents_converge_without_reset(self):
        p = Parameters(v2_v=9)
        zero = simulate_continuous(p, 75, 54/7, deadtime_s=500e-9)
        biased = simulate_continuous(p, 75, 54/7, deadtime_s=500e-9, initial_current_a=2)
        self.assertEqual(zero.rows[0]["i0_a"], 0)
        self.assertEqual(biased.rows[0]["i0_a"], 2)
        self.assertNotEqual(zero.periods[0]["i_end_a"], biased.periods[0]["i_end_a"])
        self.assertLess(abs(zero.periods[-1]["i_end_a"]-biased.periods[-1]["i_end_a"]), 1e-8)
        self.assertLess(abs(zero.periods[-1]["p2_output_w"]-biased.periods[-1]["p2_output_w"]), 1e-6)
        for result in (zero, biased):
            self.assertLess(max(abs(r["periodic_current_difference_a"]) for r in result.periods[-10:]), 1e-8)
            self.assertTrue(all(r["leg_turnons"] == 8 for r in result.periods))

    def test_vanishing_capacitance_deadtime_matches_existing_rl(self):
        small = simulate_continuous(Parameters(), 0, 30, deadtime_s=1e-12,
                                    device=Device(coss_f=1e-15))
        reference = simulate_transient(Settings(), [30.0]*100)
        self.assertLess(abs(small.periods[-1]["p2_output_w"]-reference.periods[-1]["p2_w"]), 1e-6)
        self.assertLess(abs(small.periods[-1]["i_rms_a"]-reference.periods[-1]["i_rms_a"]), 1e-7)

    def test_event_advancement_matches_finer_deadtime_output(self):
        p = Parameters(v2_v=9)
        coarse = simulate_continuous(p, 75, 54/7, deadtime_s=500e-9, period_count=6)
        fine = simulate_continuous(p, 75, 54/7, deadtime_s=500e-9, period_count=6, deadtime_step_s=10e-9)
        self.assertLess(len(coarse.rows), len(fine.rows))
        self.assertLess(abs(coarse.periods[-1]["i_end_a"]-fine.periods[-1]["i_end_a"]), 1e-9)
        self.assertLess(abs(coarse.periods[-1]["p2_output_w"]-fine.periods[-1]["p2_output_w"]), 1e-7)
        self.assertLess(abs(coarse.periods[-1]["i_rms_a"]-fine.periods[-1]["i_rms_a"]), 1e-7)
        self.assertEqual([e["zvs_in_this_model"] for e in coarse.turnons],
                         [e["zvs_in_this_model"] for e in fine.turnons])

    def test_clamp_before_current_reversal_on_both_rails(self):
        windows = edge_windows(simulate_eps(Parameters(v2_v=9), 75, 54/7), 75)
        for after, initial in ((1, 0.05), (0, -0.05)):
            with self.subTest(incoming_high=after):
                window = dict(next(w for w in windows if w["switched"] == [0] and w["after"][0] == after))
                window["initial_current_a"] = initial
                coarse, _ = simulate_window(window, 500e-9, resistance_ohm=0.5, sample_step_s=500e-9)
                fine, _ = simulate_window(window, 500e-9, resistance_ohm=0.5, sample_step_s=1e-9)
                voltages = [r[key] for r in coarse for key in ("v0_1a_v", "v1_1a_v")]
                self.assertGreaterEqual(min(voltages), -0.8-1e-8)
                self.assertLessEqual(max(voltages), 24.8+1e-8)
                self.assertTrue(any(r["clamped_legs"] == "1a" for r in coarse))
                self.assertLess(abs(coarse[-1]["v1_1a_v"]-fine[-1]["v1_1a_v"]), 1e-8)
                self.assertLess(abs(coarse[-1]["i1_a"]-fine[-1]["i1_a"]), 1e-10)
                self.assertLess(max(abs(r["cumulative_energy_residual_j"]) for r in coarse), 1e-10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
