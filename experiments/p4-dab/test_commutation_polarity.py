"""Hand-calculable switching currents and SPS symmetry/boundary checks."""

import unittest

from commutation_polarity import analyze_edges, edge_summary, sps_polarity_boundary_deg
from dab_eps import simulate_eps
from dab_sps import Parameters, simulate


class TestCommutationPolarity(unittest.TestCase):
    def test_hand_matched_sps_30_degrees(self):
        events = analyze_edges(simulate(Parameters(), 30), 0)
        self.assertEqual(len(events), 8)
        self.assertEqual(edge_summary(events)["necessary_met"], 8)
        # Four voltage-edge times, each with two leg commutations.
        expected = {0: -1.0, 30: 1.0, 180: 1.0, 210: -1.0}
        for event in events:
            self.assertAlmostEqual(event["iL_primary_a"], expected[round(event["theta_deg"])], places=10)
            self.assertAlmostEqual(event["directional_current_a"], 1 if event["bridge"] == 1 else 2, places=10)
        primary_a_rise = next(e for e in events if e["incoming_device"] == "1A_high")
        secondary_a_rise = next(e for e in events if e["incoming_device"] == "2A_high")
        self.assertEqual(primary_a_rise["required_iL_sign"], "negative")
        self.assertEqual(secondary_a_rise["required_iL_sign"], "positive")
        self.assertEqual(secondary_a_rise["node_after_v"], 12)

    def test_sps_half_cycle_symmetry_and_each_device_once(self):
        for ratio in [0.75, 1, 1.25]:
            for phase in [-30, -5, 5, 30]:
                events = analyze_edges(simulate(Parameters(v2_v=12 * ratio), phase), 0)
                self.assertEqual(len({e["incoming_device"] for e in events}), 8)
                for bridge in [1, 2]:
                    for leg in ["A", "B"]:
                        a, b = [e for e in events if e["bridge"] == bridge and e["leg"] == leg]
                        self.assertAlmostEqual(b["theta_deg"] - a["theta_deg"], 180, places=10)
                        self.assertAlmostEqual(a["iL_primary_a"], -b["iL_primary_a"], places=10)
                        self.assertAlmostEqual(a["directional_current_a"], b["directional_current_a"], places=10)
                        self.assertEqual(a["polarity_status"], b["polarity_status"])

    def test_sps_direction_reversal_preserves_each_leg_polarity(self):
        for ratio in [0.75, 1, 1.25]:
            for phase in [5, 30]:
                p = Parameters(v2_v=12 * ratio)
                positive = {e["incoming_device"]: e for e in analyze_edges(simulate(p, phase), 0)}
                negative = {e["incoming_device"]: e for e in analyze_edges(simulate(p, -phase), 0)}
                for device in positive:
                    self.assertEqual(positive[device]["polarity_status"], negative[device]["polarity_status"])
                    self.assertAlmostEqual(positive[device]["directional_current_a"],
                                           negative[device]["directional_current_a"], places=10)

    def test_sps_zero_current_boundaries_and_adjacent_points(self):
        for ratio, angle in [(0.75, 22.5), (1, 0), (1.25, 18)]:
            p = Parameters(v2_v=12 * ratio)
            self.assertAlmostEqual(sps_polarity_boundary_deg(p), angle, places=10)
            for sign in [-1, 1]:
                on = edge_summary(analyze_edges(simulate(p, sign * angle), 0))
                above = edge_summary(analyze_edges(simulate(p, sign * (angle + 0.5)), 0))
                self.assertEqual(on["zero_boundary"], 8 if ratio == 1 else 4)
                self.assertEqual(on["opposed"], 0)
                self.assertEqual(above["necessary_met"], 8)
                if angle > 0:
                    below = edge_summary(analyze_edges(simulate(p, sign * (angle - 0.5)), 0))
                    self.assertEqual(below["opposed"], 4)

    def test_eps_zero_alpha_is_identical_to_sps_screen(self):
        for ratio in [0.75, 1, 1.25]:
            p = Parameters(v2_v=12 * ratio)
            for phase in [-30, 0, 30]:
                self.assertEqual(analyze_edges(simulate(p, phase), 0), analyze_edges(simulate_eps(p, 0, phase), 0))

    def test_eps_hand_case_counts_split_primary_edges(self):
        # From the linear intervals: m=3/4, alpha=75, phi=54/7 yields P=2.7 W.
        cycle = simulate_eps(Parameters(v2_v=9), 75, 54 / 7)
        self.assertAlmostEqual(cycle.metrics["p2_time_w"], 2.7, places=10)
        events = analyze_edges(cycle, 75)
        self.assertEqual(edge_summary(events)["necessary_met"], 8)
        self.assertEqual(len({round(e["theta_deg"], 9) for e in events}), 6)
        by_device = {e["incoming_device"]: e for e in events}
        self.assertAlmostEqual(by_device["1A_high"]["iL_primary_a"], -137 / 560, places=10)
        self.assertAlmostEqual(by_device["1B_high"]["iL_primary_a"], 353 / 560, places=10)
        self.assertAlmostEqual(by_device["2A_high"]["iL_primary_a"], 0.5, places=10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
