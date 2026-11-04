"""Run existing offline checks, retaining each run's output without touching hardware."""

import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=("p1", "p2", "p4"))
    args = parser.parse_args()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    output = ROOT / ".runs" / run_id
    output.mkdir(parents=True)
    p1 = ROOT / "experiments/p1-c2000-buck"
    p2 = ROOT / "experiments/p2-zcu104-daq"
    p4 = ROOT / "experiments/p4-dab"
    jobs = [
        ("p1", "buck", p1 / "simulation", ["-m", "unittest", "discover", "-v"]),
        ("p2", "rtl", p2, ["scripts/run_sim.py", "--suite", "all", "--output",
                            f".runs/{run_id}/rtl"]),
        ("p2", "frame_validator", p2, ["scripts/run_frame_validator.py", "--output",
                                        f".runs/{run_id}/frame_validator"]),
        ("p4", "dab", p4, ["-m", "unittest", "discover", "-v"]),
    ]
    results = []
    for project, name, cwd, arguments in jobs:
        if args.only and project != args.only:
            continue
        command = [sys.executable, "-X", "utf8", *arguments]
        log_path = output / f"{project}_{name}.log"
        print(f"Running {project}/{name}; log: {log_path}", flush=True)
        started = time.monotonic()
        with log_path.open("w", encoding="utf-8") as log:
            log.write(f"CWD {cwd}\nCOMMAND {json.dumps(command, ensure_ascii=False)}\n")
            log.flush()
            try:
                process = subprocess.run(command, cwd=cwd, stdout=log,
                                         stderr=subprocess.STDOUT, timeout=300)
                code = process.returncode
            except (OSError, subprocess.TimeoutExpired) as error:
                log.write(f"\nRUNNER ERROR: {error}\n")
                code = -1
            log.write(f"\nEXIT_CODE {code}\n")
        result = {"project": project, "check": name, "exit_code": code,
                  "seconds": round(time.monotonic() - started, 3),
                  "log": log_path.relative_to(ROOT).as_posix()}
        if project == "p2":
            result["artifacts"] = (cwd / arguments[-1]).relative_to(ROOT).as_posix()
        results.append(result)
        print(f"{'PASS' if code == 0 else 'FAIL'} {project}/{name}", flush=True)
        if code != 0:
            print("Last 30 log lines (full output retained):", flush=True)
            print("\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-30:]),
                  flush=True)
    report = {"kind": "offline Python, RTL simulation and host C checks",
              "python": sys.version, "checks": results}
    (output / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Results: {output}")
    return int(any(result["exit_code"] != 0 for result in results))


if __name__ == "__main__":
    sys.exit(main())
