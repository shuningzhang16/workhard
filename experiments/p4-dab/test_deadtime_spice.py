"""Prevent a successful process exit from masking a missing/truncated export."""

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from verify_deadtime_spice import execute_ngspice, read_spice_data


class TestSpiceOutput(unittest.TestCase):
    def test_zero_exit_cannot_reuse_old_data(self):
        with tempfile.TemporaryDirectory(prefix=".spice_test_", dir=Path(__file__).resolve().parent) as folder:
            output = Path(folder)
            (output / "case.dat").write_text("old result\n", encoding="utf-8")
            fake_exit = subprocess.CompletedProcess(["ngspice"], 0, "analysis failed; quit\n", "")
            with patch("verify_deadtime_spice.subprocess.run", return_value=fake_exit):
                with self.assertRaisesRegex(RuntimeError, "did not create"):
                    execute_ngspice(["ngspice"], output, "case", 150e-9)
            self.assertFalse((output / "case.dat").exists())
            self.assertIn("analysis failed", (output / "case.log").read_text())

    def test_finite_values_and_complete_time_axis_required(self):
        with tempfile.TemporaryDirectory(prefix=".spice_test_", dir=Path(__file__).resolve().parent) as folder:
            path = Path(folder) / "data.dat"
            good = "time i va vb vc vd\n2e-12 1 0 24 0 12\n1.5e-7 1 24 0 0 12\n"
            path.write_text(good, encoding="utf-8")
            self.assertEqual(len(read_spice_data(path, 150e-9)), 2)
            for bad in [good.replace("1.5e-7", "1e-7"), good.replace("2e-12", "2e-8"),
                        good.replace("24", "nan"), good.replace("1.5e-7", "1e-12"),
                        "time i va vb vc vd\n"]:
                path.write_text(bad, encoding="utf-8")
                with self.assertRaises(ValueError):
                    read_spice_data(path, 150e-9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
