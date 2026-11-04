"""Compile and execute the RTL testbench with Icarus Verilog (no hardware access)."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def run_logged(command, log_path, env):
    """Keep simulator output on failure as well as success."""
    with log_path.open("w", encoding="utf-8") as log:
        log.write("COMMAND " + json.dumps(command, ensure_ascii=False) + "\n")
        log.flush()
        result = subprocess.run(
            command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
            timeout=60, check=False,
        )
        log.write(f"\nEXIT_CODE {result.returncode}\n")
    if result.returncode:
        raise RuntimeError(f"Command failed; see {log_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iverilog", help="Path to an installed iverilog executable")
    parser.add_argument("--suite", choices=("source", "fifo", "all"), default="source")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    local_tool = ROOT / ".tools/ucrt64/bin/iverilog.exe"
    compiler = args.iverilog or shutil.which("iverilog")
    if not compiler and local_tool.exists():
        compiler = str(local_tool)
    if not compiler:
        parser.error("Icarus Verilog is required; no model fallback is reported as RTL simulation")
    compiler = str(Path(compiler).resolve())
    tool_dir = Path(compiler).parent
    simulator = tool_dir / ("vvp.exe" if os.name == "nt" else "vvp")
    env = os.environ.copy()
    env["PATH"] = str(tool_dir) + os.pathsep + env.get("PATH", "")
    default_output = "results/first_step" if args.suite == "source" else "results/fifo_step"
    output = (ROOT / (args.output or Path(default_output))).resolve()
    # Keep all generated artifacts within this experiment.
    output.relative_to(ROOT)
    output.mkdir(parents=True, exist_ok=True)
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    run_logged([compiler, "-V"], output / "iverilog-version.log", env)
    run_logged([str(simulator), "-V"], output / "vvp-version.log", env)
    summaries = []
    cases = []
    if args.suite in ("source", "all"):
        cases.extend((f"frames{value}", "tb_axis_pattern_source", "FRAME_WORDS", value,
                      ["rtl/axis_pattern_source.v", "tb/tb_axis_pattern_source.sv"])
                     for value in (1, 7, 16))
    if args.suite in ("fifo", "all"):
        cases.extend((f"depth{value}", "tb_axis_sync_fifo", "DEPTH", value,
                      ["rtl/axis_pattern_source.v", "rtl/axis_sync_fifo.v", "tb/tb_axis_sync_fifo.sv"])
                     for value in (1, 3, 16))
    for name, top, parameter, value, sources in cases:
        case_dir = output / name
        case_dir.mkdir(exist_ok=True)
        executable = f"build/{name}.vvp"
        compile_command = [
            compiler, "-g2012", "-Wall", "-s", top,
            f"-P{top}.{parameter}={value}",
            "-o", executable,
        ] + sources
        run_command = [
            str(simulator), executable,
            "+OUTDIR=" + case_dir.relative_to(ROOT).as_posix(),
        ]
        run_logged(compile_command, case_dir / "compile.log", env)
        run_logged(run_command, case_dir / "simulation.log", env)
        summary = json.loads((case_dir / "summary.json").read_text(encoding="utf-8"))
        if summary["result"] != "PASS":
            raise RuntimeError(f"Test did not pass: {case_dir}")
        summaries.append(summary)
        print(f"PASS {name}: {summary}")
    (output / "summary.json").write_text(
        json.dumps({"kind": "RTL simulation", "simulator": "Icarus Verilog", "cases": summaries},
                   indent=2) + "\n", encoding="utf-8",
    )
    print(f"Logs and bounded raw traces: {output}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
