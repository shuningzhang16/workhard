"""Compare retained pre-fix and isolated post-fix continuous results."""

import csv
from pathlib import Path


root = Path(__file__).resolve().parent
before = root / "original" / "results_continuous"
after = root / "after" / "results_continuous"
with (before / "summary.csv").open(encoding="utf-8", newline="") as stream:
    old_rows = list(csv.DictReader(stream))
with (after / "summary.csv").open(encoding="utf-8", newline="") as stream:
    new_rows = list(csv.DictReader(stream))


def rail_violation(folder, name, v2):
    maximum = 0.0
    with (folder / f"{name}_waveform.csv").open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            for leg, bus in zip(("1a", "1b", "2a", "2b"), (24, 24, v2, v2)):
                for end in (0, 1):
                    value = float(row[f"v{end}_{leg}_v"])
                    maximum = max(maximum, -0.8-value, value-bus-0.8)
    return maximum


comparison = []
for old in old_rows:
    new = next(r for r in new_rows if all(r[key] == old[key] for key in ("case", "method", "deadtime_s")))
    name = f"{old['case']}_{old['method']}_{round(float(old['deadtime_s'])*1e9)}ns"
    record = {"case": name,
              "before_rail_violation_v": rail_violation(before, name, float(old["v2_v"])),
              "after_rail_violation_v": rail_violation(after, name, float(new["v2_v"]))}
    for key in ("p2_output_w", "i_rms_a", "last_period_zvs_in_model", "whole_run_i_peak_a",
                "resistor_power_w", "diode_power_w", "turnon_redistribution_power_w"):
        record[f"before_{key}"] = float(old[key])
        record[f"after_{key}"] = float(new[key])
        record[f"difference_{key}"] = float(new[key])-float(old[key])
    comparison.append(record)
with (root / "comparison.csv").open("w", encoding="utf-8", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=list(comparison[0]))
    writer.writeheader()
    writer.writerows(comparison)
for field in ("p2_output_w", "i_rms_a", "last_period_zvs_in_model", "whole_run_i_peak_a"):
    print(f"Maximum |change in {field}|: {max(abs(r[f'difference_{field}']) for r in comparison):.17g}")
print(f"Maximum old/new rail violation: {max(r['before_rail_violation_v'] for r in comparison):.17g} / "
      f"{max(r['after_rail_violation_v'] for r in comparison):.17g} V")
