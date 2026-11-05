"""Persist rail-crossing-before-current-reversal cases, without hiding errors."""

import argparse
import csv
import json
from pathlib import Path

from dab_deadtime import edge_windows, simulate_window
from dab_eps import simulate_eps
from dab_sps import Parameters


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    cycle = simulate_eps(Parameters(v2_v=9), 75, 54/7)
    windows = edge_windows(cycle, 75)
    records = []
    for label, after, initial in (("lower_rail", 1, 0.05), ("upper_rail", 0, -0.05)):
        window = dict(next(w for w in windows if w["switched"] == [0] and w["after"][0] == after))
        window["initial_current_a"] = initial
        for step in (500e-9, 1e-9):
            rows, events = simulate_window(window, 500e-9, resistance_ohm=0.5, sample_step_s=step)
            key = f"{label}_{round(step*1e9)}ns"
            path = output / f"{key}.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            record = {"case": key, "step_s": step, "initial_current_a": initial,
                "min_node_v": min(r[k] for r in rows for k in ("v0_1a_v", "v1_1a_v")),
                "max_node_v": max(r[k] for r in rows for k in ("v0_1a_v", "v1_1a_v")),
                "final_node_v": rows[-1]["v1_1a_v"], "final_current_a": rows[-1]["i1_a"],
                "max_energy_residual_j": max(abs(r["cumulative_energy_residual_j"]) for r in rows),
                "rail_violation_v": max(0, max(-0.8-r[k] for r in rows for k in ("v0_1a_v", "v1_1a_v")),
                    max(r[k]-24.8 for r in rows for k in ("v0_1a_v", "v1_1a_v")))}
            records.append(record)
            print(json.dumps(record))
    (output / "reproduction.json").write_text(json.dumps(records, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
