"""Stateful switching against the existing fixed-angle physical solver."""

import unittest

from dab_continuous import ContinuousRun, simulate_continuous
from dab_deadtime import LEGS, edge_windows
from dab_eps import simulate_eps
from dab_sps import Parameters
from dab_switching import BridgeState


def replay_fixed(p, alpha, phase, deadtime, count=12):
    schedule = edge_windows(simulate_eps(p, alpha, phase), alpha)
    bridge = BridgeState(p, schedule[0]["before"])
    periods = []
    for k in range(count):
        bridge.period_index = k
        first_row, first_turnon = len(bridge.rows), len(bridge.turnons)
        for event in schedule:
            t = k/p.frequency_hz+event["edge_time_s"]-schedule[0]["edge_time_s"]
            bridge.advance(t)
            targets = {j: event["after"][j] for j in event["switched"]}
            bridge.turn_off(targets)
            bridge.advance(t+deadtime)
            bridge.turn_on(targets)
        bridge.advance((k+1)/p.frequency_hz)
        periods.append(bridge.summarize(first_row, first_turnon))
    return ContinuousRun(bridge.rows, periods, bridge.turnons)


class TestSwitching(unittest.TestCase):
    def test_fixed_angles_match_existing_solver(self):
        for alpha, phase in ((0, 30), (0, -8), (75, 54/7), (75, -54/7)):
            for deadtime in (150e-9, 500e-9):
                with self.subTest(alpha=alpha, phase=phase, deadtime=deadtime):
                    p = Parameters(v2_v=9)
                    old = simulate_continuous(p, alpha, phase, deadtime_s=deadtime, period_count=12)
                    new = replay_fixed(p, alpha, phase, deadtime)
                    for a, b in zip(old.periods, new.periods):
                        for key in ("i_end_a", "p1_input_w", "p2_output_w", "i_rms_a",
                                    "resistor_power_w", "diode_power_w", "turnon_redistribution_power_w"):
                            self.assertLess(abs(a[key]-b[key]), 1e-8, key)
                    self.assertEqual([e["zvs_in_this_model"] for e in old.turnons],
                                     [e["zvs_in_this_model"] for e in new.turnons])

    def test_interrupted_deadtime_retains_capacitor_state(self):
        a = BridgeState(Parameters(v2_v=9), [0, 1, 0, 1], initial_current_a=-0.2)
        b = BridgeState(Parameters(v2_v=9), [0, 1, 0, 1], initial_current_a=-0.2)
        for bridge in (a, b):
            bridge.turn_off({0: 1, 1: 0})
        a.advance(500e-9)
        b.advance(47e-9)
        saved = list(b.nodes)
        self.assertNotEqual(saved, [0, 24, 0, 9])
        first = len(b.rows)
        b.advance(500e-9)
        self.assertEqual([b.rows[first][f"v0_{leg}_v"] for leg in LEGS], saved)
        self.assertLess(abs(a.current-b.current), 1e-10)
        for av, bv in zip(a.nodes, b.nodes):
            self.assertLess(abs(av-bv), 1e-8)
        self.assertLess(max(abs(r["cumulative_energy_residual_j"]) for r in b.rows), 1e-10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
