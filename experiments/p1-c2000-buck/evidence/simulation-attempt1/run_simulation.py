"""运行三个教学工况并保存完整采样 CSV、配置和指标；不访问 TI 源码。"""

import csv
import json
import platform
import sys
from dataclasses import asdict
from pathlib import Path

from buck_model import Parameters, metrics, simulate


def main():
    output = Path(__file__).resolve().parent / "results"
    output.mkdir(exist_ok=True)
    p = Parameters()
    config = {
        "result_type": "independent_ideal_averaged_model_simulation",
        "parameter_source": "teaching assumptions; not extracted from TI firmware or hardware",
        "python": sys.version, "platform": platform.platform(), "parameters": asdict(p),
        "integration_method": "RK4, fixed step; duty held for each control sample",
        "integration_step_s": p.control_period_s / p.integration_substeps,
    }
    (output / "parameters.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    summaries = []
    for case in ("startup", "load_step", "input_step"):
        rows = simulate(case, p)
        with (output / f"{case}.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        summary = metrics(rows, case, p)
        summaries.append(summary)
        print(json.dumps(summary), flush=True)
    (output / "metrics.json").write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")
    with (output / "metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)


if __name__ == "__main__":
    main()
