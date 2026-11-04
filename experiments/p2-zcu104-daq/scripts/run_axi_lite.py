"""Run the independent AXI4-Lite controlled-stream RTL test; no hardware access."""

import argparse
import json
import os
from pathlib import Path
import shutil

from run_sim import ROOT, run_logged


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results/axi_lite"))
    parser.add_argument("--iverilog")
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    output.relative_to(ROOT)
    output.mkdir(parents=True, exist_ok=True)
    (ROOT / "build").mkdir(exist_ok=True)
    local = ROOT / ".tools/ucrt64/bin/iverilog.exe"
    compiler = args.iverilog or shutil.which("iverilog") or (str(local) if local.exists() else None)
    if not compiler:
        parser.error("Icarus Verilog is required")
    compiler = str(Path(compiler).resolve())
    tool_dir = Path(compiler).parent
    simulator = tool_dir / ("vvp.exe" if os.name == "nt" else "vvp")
    env = os.environ.copy()
    env["PATH"] = str(tool_dir) + os.pathsep + env.get("PATH", "")
    run_logged([compiler, "-V"], output / "iverilog-version.log", env)
    run_logged([compiler, "-g2012", "-Wall", "-s", "tb_daq_axi_lite", "-o", "build/daq_axi_lite.vvp",
                "rtl/axis_pattern_source.v", "rtl/axis_sync_fifo.v", "rtl/daq_stream_top.v",
                "rtl/daq_axi_lite.v", "tb/tb_daq_axi_lite.sv"], output / "compile.log", env)
    run_logged([str(simulator), "build/daq_axi_lite.vvp",
                "+OUTDIR=" + output.relative_to(ROOT).as_posix()], output / "simulation.log", env)
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    if summary["result"] != "PASS":
        raise RuntimeError("AXI-Lite simulation failed")
    print(json.dumps(summary))
    print(f"RTL evidence: {output}")


if __name__ == "__main__":
    main()
