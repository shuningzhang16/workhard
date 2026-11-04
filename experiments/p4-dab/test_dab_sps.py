"""Physics checks independent of saved results; run with unittest."""

import math
import unittest

from dab_sps import Parameters, simulate, waveform_rows


class TestSPS(unittest.TestCase):
    def test_known_matched_30_degree_solution(self):
        # 48 V across 100 uH for T/12 gives 2 A change, hence +/-1 A.
        for phase, power in [(30, 20), (-30, -20)]:
            with self.subTest(phase=phase):
                m = simulate(Parameters(), phase).metrics
                self.assertAlmostEqual(m["p2_time_w"], power, places=10)
                self.assertAlmostEqual(m["i_peak_a"], 1, places=10)
                self.assertAlmostEqual(m["i_rms_a"], math.sqrt(8 / 9), places=10)

    def test_zero_phase_with_and_without_voltage_mismatch(self):
        matched = simulate(Parameters(), 0).metrics
        self.assertAlmostEqual(matched["i_peak_a"], 0, places=12)
        for v2 in [9, 15]:
            with self.subTest(v2=v2):
                m = simulate(Parameters(v2_v=v2), 0).metrics
                self.assertAlmostEqual(m["p2_time_w"], 0, places=10)
                self.assertAlmostEqual(m["i_peak_a"], 0.75, places=10)
                self.assertAlmostEqual(m["i_rms_a"], 0.75 / math.sqrt(3), places=10)

    def test_scan_power_energy_and_periodicity(self):
        for ratio in [0.75, 1, 1.25]:
            for phase in range(-90, 91, 15):
                with self.subTest(ratio=ratio, phase=phase):
                    m = simulate(Parameters(v2_v=12 * ratio), phase).metrics
                    for key in ["power_error_w", "power_balance_w",
                                "i_mean_a", "periodic_error_a"]:
                        self.assertLess(abs(m[key]), 1e-9, key)

    def test_direction_symmetry_and_non_grid_phase(self):
        parameters = Parameters(v1_v=18, v2_v=10, turns_ratio=1.5,
                                frequency_hz=35_000, inductance_h=65e-6)
        forward = simulate(parameters, 17.3).metrics
        reverse = simulate(parameters, -17.3).metrics
        self.assertGreater(forward["p2_time_w"], 0)
        self.assertAlmostEqual(forward["p2_time_w"], -reverse["p2_time_w"], places=10)
        for key in ["i_peak_a", "i_rms_a"]:
            self.assertAlmostEqual(forward[key], reverse[key], places=10)
        self.assertLess(abs(forward["power_error_w"]), 1e-9)

    def test_turns_ratio_referral_and_inductance_scaling(self):
        original = simulate(Parameters(), 30).metrics
        referred = simulate(Parameters(v2_v=24, turns_ratio=1), 30).metrics
        doubled_l = simulate(Parameters(inductance_h=200e-6), 30).metrics
        for key in ["p2_time_w", "i_peak_a", "i_rms_a"]:
            self.assertAlmostEqual(original[key], referred[key], places=10)
            self.assertAlmostEqual(original[key] / 2, doubled_l[key], places=10)

    def test_waveform_export_preserves_ode_and_integrals(self):
        cycle = simulate(Parameters(v2_v=15), -30)
        rows = list(waveform_rows(cycle))
        duration = rows[-1]["t1_s"] - rows[0]["t0_s"]
        self.assertAlmostEqual(duration, 2 / cycle.parameters.frequency_hz, places=14)
        for previous, current in zip(rows, rows[1:]):
            self.assertAlmostEqual(previous["t1_s"], current["t0_s"], places=14)
            self.assertAlmostEqual(previous["iL1_a"], current["iL0_a"], places=10)
        for row in rows:
            dt = row["t1_s"] - row["t0_s"]
            self.assertAlmostEqual(row["iL1_a"] - row["iL0_a"],
                                   row["vL_v"] / cycle.parameters.inductance_h * dt,
                                   places=10)
        power = math.fsum(r["p2_avg_w"] * (r["t1_s"] - r["t0_s"]) for r in rows) / duration
        rms = math.sqrt(math.fsum(
            (r["iL0_a"]**2 + r["iL0_a"] * r["iL1_a"] + r["iL1_a"]**2)
            / 3 * (r["t1_s"] - r["t0_s"]) for r in rows
        ) / duration)
        self.assertAlmostEqual(power, cycle.metrics["p2_time_w"], places=10)
        self.assertAlmostEqual(rms, cycle.metrics["i_rms_a"], places=10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
