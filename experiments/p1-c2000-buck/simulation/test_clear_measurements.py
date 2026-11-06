"""Finite ADC-bin checks; truth is used only to construct counterexample inputs."""
import unittest

from io_timing_buck import adc_clear_evidence, quantized_measurements
from protection import ProtectedController


class ClearMeasurementTests(unittest.TestCase):
    def test_old_counterexamples_remain_latched(self):
        for v, i, reason in ((-1.906609, 0.005453, "rejected_unobservable_measurement"),
                             (0.031066, 0.104541, "rejected_residual_energy")):
            with self.subTest(v=v, i=i):
                control = ProtectedController()
                control.update(0, 9, 0, 2.5)
                adc = quantized_measurements(9, v, i)
                evidence = adc_clear_evidence(adc["raw_vout"], adc["raw_current"])
                result = control.update(1, adc["measured_input_v"], adc["measured_output_v"],
                                        adc["measured_current_a"], True, evidence)
                self.assertEqual(result["clear_result"], reason)
                self.assertEqual(result["state"], "FAULT_LATCHED")
                self.assertEqual(result["duty"], 0)

    def test_finite_interior_bins_permit_explicit_clear(self):
        for v, i in ((0.002, 0.0), (0.0985, 0.09), (0.031, -0.09)):
            with self.subTest(v=v, i=i):
                control = ProtectedController()
                control.update(0, 9, 0, 2.5)
                adc = quantized_measurements(9, v, i)
                evidence = adc_clear_evidence(adc["raw_vout"], adc["raw_current"])
                values = (adc["measured_input_v"], adc["measured_output_v"], adc["measured_current_a"])
                self.assertEqual(control.update(1, *values, False, evidence)["state"], "FAULT_LATCHED")
                result = control.update(2, *values, True, evidence)
                self.assertEqual(result["clear_result"], "accepted")
                self.assertEqual(result["reference_v"], 0)

    def test_zero_code_does_not_gain_information_with_time(self):
        evidence = adc_clear_evidence(0, 2048)
        control = ProtectedController()
        control.update(0, 9, 0, 2.5)
        for sample in (1, 4000, 50000000):
            result = control.update(sample, 9, 0, 0, True, evidence)
            self.assertEqual(result["clear_result"], "rejected_unobservable_measurement")
            self.assertEqual(result["state"], "FAULT_LATCHED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
