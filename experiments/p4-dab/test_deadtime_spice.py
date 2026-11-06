"""Keep prior evidence while rejecting missing or malformed SPICE exports."""

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from verify_deadtime_spice import execute_ngspice, read_spice_data, run


def retained_folder():
    # Deliberately retain failed and successful evidence; never auto-clean it.
    return Path(tempfile.mkdtemp(prefix="workhard-spice-test-"))


class TestSpiceOutput(unittest.TestCase):
    def test_zero_exit_cannot_reuse_old_data(self):
        for suffix in ("dat", "log"):
            output = retained_folder()
            old = output / f"case.{suffix}"
            old.write_text("old result\n", encoding="utf-8")
            with patch("verify_deadtime_spice.subprocess.run") as process:
                with self.assertRaises(FileExistsError):
                    execute_ngspice(["ngspice"], output, "case", 150e-9)
                with self.assertRaises(FileExistsError):
                    run(Path("unused.csv"), output, ["ngspice"])
                process.assert_not_called()
            self.assertEqual(old.read_text(), "old result\n")
        output = retained_folder()
        fake_exit = subprocess.CompletedProcess(["ngspice"], 0, "analysis failed; quit\n", "")
        with patch("verify_deadtime_spice.subprocess.run", return_value=fake_exit):
            with self.assertRaisesRegex(RuntimeError, "did not create"):
                execute_ngspice(["ngspice"], output, "case", 150e-9)
        self.assertFalse((output / "case.dat").exists())
        self.assertIn("analysis failed", (output / "case.log").read_text())

    def test_finite_values_and_complete_time_axis_required(self):
        output = retained_folder()
        path = output / "good.dat"
        good = "time i va vb vc vd\n2e-12 1 0 24 0 12\n1.5e-7 1 24 0 0 12\n"
        path.write_text(good, encoding="utf-8")
        self.assertEqual(len(read_spice_data(path, 150e-9)), 2)
        for number, bad in enumerate([good.replace("1.5e-7", "1e-7"), good.replace("2e-12", "2e-8"),
                                     good.replace("24", "nan"), good.replace("1.5e-7", "1e-12"),
                                     "time i va vb vc vd\n"]):
            bad_path = output / f"bad_{number}.dat"
            bad_path.write_text(bad, encoding="utf-8")
            with self.assertRaises(ValueError):
                read_spice_data(bad_path, 150e-9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
