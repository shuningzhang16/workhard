"""Independent differential integration, rail conditions and physical balance."""

import unittest

from dab_deadtime import Device, edge_windows, simulate_window
from dab_eps import simulate_eps
from dab_sps import Parameters, simulate


class TestDeadtime(unittest.TestCase):
    def test_unclamped_window_against_independent_rk4(self):
        window = edge_windows(simulate(Parameters(), 30), 0)[0]
        p, device = window["parameters"], Device()
        state = [window["initial_current_a"], 0.0, 24.0, 0.0, 12.0]
        factors = (1, -1, -2, 2)
        def derivative(y):
            return [sum(a * v for a, v in zip(factors, y[1:])) / p.inductance_h] + [
                -factors[j] * y[0] / (2 * device.coss_f) if j in window["switched"] else 0
                for j in range(4)]
        dt = 0.1e-9
        for _ in range(200):
            k1 = derivative(state)
            k2 = derivative([x + dt * k / 2 for x, k in zip(state, k1)])
            k3 = derivative([x + dt * k / 2 for x, k in zip(state, k2)])
            k4 = derivative([x + dt * k for x, k in zip(state, k3)])
            state = [x + dt * (a + 2*b + 2*c + d) / 6
                     for x, a, b, c, d in zip(state, k1, k2, k3, k4)]
        rows, _ = simulate_window(window, 20e-9)
        end = rows[-1]
        self.assertAlmostEqual(state[0], end["i1_a"], places=10)
        for j, leg in enumerate(("1a", "1b", "2a", "2b")):
            self.assertAlmostEqual(state[j + 1], end[f"v1_{leg}_v"], places=9)

    def test_polarity_alone_does_not_complete_transition(self):
        eps = simulate_eps(Parameters(v2_v=9), 75, 54 / 7)
        window = next(w for w in edge_windows(eps, 75) if w["switched"] == [0])
        _, events = simulate_window(window, 150e-9)
        self.assertGreater(events[0]["initial_directional_current_a"], 0)
        self.assertGreater(events[0]["incoming_vds_at_turnon_v"], 1)
        self.assertFalse(events[0]["zvs_in_this_model"])
        zero = edge_windows(simulate(Parameters(), 0), 0)[0]
        rows, events = simulate_window(zero, 150e-9)
        self.assertTrue(all(r["i1_a"] == 0 for r in rows))
        self.assertTrue(all(not e["zvs_in_this_model"] for e in events))

    def test_coupled_current_continuity_energy_and_diode_clamp(self):
        for cycle, alpha in [(simulate(Parameters(), 30), 0),
                             (simulate_eps(Parameters(v2_v=9), 75, 54 / 7), 75)]:
            windows = edge_windows(cycle, alpha)
            self.assertEqual(sum(len(w["switched"]) for w in windows), 8)
            for window in windows:
                rows, events = simulate_window(window, 500e-9)
                self.assertEqual(rows[0]["i0_a"], window["initial_current_a"])
                for a, b in zip(rows, rows[1:]):
                    self.assertEqual(a["i1_a"], b["i0_a"])
                    self.assertEqual(a["t1_s"], b["t0_s"])
                    for leg in ("1a", "1b", "2a", "2b"):
                        self.assertEqual(a[f"v1_{leg}_v"], b[f"v0_{leg}_v"])
                self.assertLess(max(abs(r["energy_residual_j"]) for r in rows), 1e-12)
                self.assertLess(max(abs(r["cumulative_energy_residual_j"]) for r in rows), 1e-10)
                self.assertTrue(all(r["diode_energy_j"] >= 0 for r in rows))
                self.assertTrue(all(e["incoming_vds_at_turnon_v"] >= -0.80000001 for e in events))
        self.assertTrue(any(r["clamped_legs"] for r in rows))


if __name__ == "__main__":
    unittest.main(verbosity=2)
