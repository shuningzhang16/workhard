"""Capture real RTL output and test the portable packet receiver on the host."""

import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys

from run_sim import ROOT, run_logged


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results/simple_s2mm"))
    parser.add_argument("--wsl-distro", default="Ubuntu-22.04")
    parser.add_argument("--iverilog")
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    output.relative_to(ROOT)
    output.mkdir(parents=True, exist_ok=True)
    relative = output.relative_to(ROOT).as_posix()
    env = os.environ.copy()
    capture_command = [sys.executable, "scripts/run_frame_validator.py", "--output",
                       relative + "/capture", "--wsl-distro", args.wsl_distro]
    if args.iverilog:
        capture_command.extend(["--iverilog", args.iverilog])
    run_logged(capture_command, output / "capture_runner.log", env)
    prefix = []
    if os.name == "nt":
        linux_root = subprocess.check_output(
            ["wsl", "-d", args.wsl_distro, "--exec", "wslpath", "-a", str(ROOT)],
            cwd=ROOT, text=True, encoding="utf-8", timeout=30).strip()
        prefix = ["wsl", "-d", args.wsl_distro, "--cd", linux_root, "--exec"]
    run_logged(prefix + ["gcc", "-std=c11", "-O1", "-g", "-Wall", "-Wextra",
                        "-Werror", "-Wpedantic", "-fsanitize=address,undefined",
                        "-fno-sanitize-recover=all", "-fno-omit-frame-pointer",
                        "-Ips", "ps/frame_validator.c", "ps/simple_s2mm.c",
                        "tests/test_simple_s2mm.c", "-o", "build/test_simple_s2mm"],
               output / "c_compile.log", env)
    command = prefix + ["./build/test_simple_s2mm", relative + "/capture/rtl_capture_le.bin"]
    with (output / "fault_matrix.csv").open("w", encoding="utf-8", newline="") as matrix, \
            (output / "c_test.log").open("w", encoding="utf-8") as log:
        log.write("COMMAND " + json.dumps(command, ensure_ascii=False) + "\n")
        log.flush()
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=matrix, stderr=log, timeout=60)
        log.write(f"\nEXIT_CODE {result.returncode}\n")
    if result.returncode:
        raise RuntimeError(f"Receiver tests failed; evidence retained in {output}")
    with (output / "fault_matrix.csv").open(encoding="utf-8", newline="") as matrix:
        cases = list(csv.DictReader(matrix))
    if len(cases) != 13 or any(case["result"] != "PASS" for case in cases):
        raise RuntimeError("Receiver fault matrix incomplete or failed")
    summary = {"scope": "host control flow, boundaries and callback order only",
               "payload": "capture/rtl_capture_le.bin from actual RTL simulation",
               "hardware_dma_executed": False, "standalone_adapter_compiled": False,
               "packet_bytes": 28, "success_packets": 12, "poll_limit_per_packet": 3,
               "c_host": f"WSL {args.wsl_distro}" if os.name == "nt" else "native host",
               "sanitizers": ["address", "undefined"], "cases": len(cases), "passed": len(cases)}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: {len(cases)} receiver cases; actual RTL payload; evidence: {output}")


if __name__ == "__main__":
    main()
