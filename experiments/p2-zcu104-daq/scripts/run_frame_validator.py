"""Run a complete RTL capture, then compile and execute the host C fault matrix."""

import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess

from run_sim import ROOT, run_logged


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results/frame_validator"))
    parser.add_argument("--iverilog")
    parser.add_argument("--wsl-distro", default="Ubuntu-22.04")
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    output.relative_to(ROOT)
    output.mkdir(parents=True, exist_ok=True)
    (ROOT / "build").mkdir(exist_ok=True)
    relative_output = output.relative_to(ROOT).as_posix()
    local_tool = ROOT / ".tools/ucrt64/bin/iverilog.exe"
    compiler = args.iverilog or shutil.which("iverilog") or (str(local_tool) if local_tool.exists() else None)
    if not compiler:
        parser.error("Icarus Verilog is required for the actual RTL capture")
    compiler = str(Path(compiler).resolve())
    tool_dir = Path(compiler).parent
    simulator = tool_dir / ("vvp.exe" if os.name == "nt" else "vvp")
    env = os.environ.copy()
    env["PATH"] = str(tool_dir) + os.pathsep + env.get("PATH", "")
    run_logged([compiler, "-V"], output / "iverilog-version.log", env)
    run_logged([compiler, "-g2012", "-Wall", "-s", "tb_capture_stream",
                "-o", "build/capture_stream.vvp", "rtl/axis_pattern_source.v",
                "rtl/axis_sync_fifo.v", "rtl/daq_stream_top.v", "tb/tb_capture_stream.sv"], output / "rtl_compile.log", env)
    run_logged([str(simulator), "build/capture_stream.vvp", "+OUTDIR=" + relative_output],
               output / "rtl_simulation.log", env)
    with (output / "rtl_capture.csv").open(newline="", encoding="utf-8") as capture:
        rows = list(csv.DictReader(capture))
    if len(rows) != 84 or any(int(row["ordinal"]) != i or int(row["keep"]) != 15
                              for i, row in enumerate(rows)):
        raise RuntimeError("RTL capture is not a complete sequence of 84 full-byte beats")
    # Serialize only actually observed RTL TDATA; no generated replacement samples.
    (output / "rtl_capture_le.bin").write_bytes(
        b"".join(struct.pack("<I", int(row["data_hex"], 16)) for row in rows)
    )
    prefix = []
    if os.name == "nt":
        linux_root = subprocess.check_output(
            ["wsl", "-d", args.wsl_distro, "--exec", "wslpath", "-a", str(ROOT)],
            cwd=ROOT, text=True, encoding="utf-8", timeout=30,
        ).strip()
        prefix = ["wsl", "-d", args.wsl_distro, "--cd", linux_root, "--exec"]
    run_logged(prefix + ["gcc", "--version"], output / "gcc-version.log", env)
    compile_c = prefix + [
        "gcc", "-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror", "-Wpedantic",
        "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer",
        "-Ips", "ps/frame_validator.c", "tests/test_frame_validator.c",
        "-o", "build/test_frame_validator",
    ]
    run_logged(compile_c, output / "c_compile.log", env)
    command = prefix + ["./build/test_frame_validator", relative_output + "/rtl_capture_le.bin"]
    with (output / "fault_matrix.csv").open("w", encoding="utf-8", newline="") as matrix, \
            (output / "c_test.log").open("w", encoding="utf-8") as log:
        log.write("COMMAND " + json.dumps(command, ensure_ascii=False) + "\n")
        log.flush()
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=matrix, stderr=log, timeout=60)
        log.write(f"\nEXIT_CODE {result.returncode}\n")
    if result.returncode:
        raise RuntimeError(f"C tests failed; evidence retained in {output}")
    with (output / "fault_matrix.csv").open(newline="", encoding="utf-8") as matrix:
        cases = list(csv.DictReader(matrix))
    if len(cases) != 16 or any(case["result"] != "PASS" for case in cases):
        raise RuntimeError("C fault matrix is incomplete or contains a failure")
    summary = {"capture_origin": "RTL simulation: daq_stream_top(source -> depth-3 FIFO) -> sink",
               "capture_words": len(rows), "capture_frames": 12, "frame_words": 7,
               "capture_bytes": len(rows) * 4, "serialization": "little-endian uint32",
               "c_host": f"WSL {args.wsl_distro}" if os.name == "nt" else "native host",
               "sanitizers": ["address", "undefined"], "cases": len(cases), "passed": len(cases)}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: {len(rows)} actual RTL words; {len(cases)} C tests; evidence: {output}")


if __name__ == "__main__":
    main()
