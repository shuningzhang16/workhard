"""Synthesize the stream top to generic cells and replay the existing capture test."""

import argparse
import csv
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
P2 = ROOT / "experiments/p2-zcu104-daq"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--yosys", default=".tools/yosys/usr/bin/yosys" if os.name == "nt" else "yosys")
    parser.add_argument("--iverilog")
    args = parser.parse_args()
    output = (ROOT / (args.output or Path(".runs") / datetime.now().strftime("yosys-%Y%m%d-%H%M%S-%f"))).resolve()
    output.relative_to(ROOT)
    output.mkdir(parents=True, exist_ok=True)
    local_iverilog = P2 / ".tools/ucrt64/bin/iverilog.exe"
    compiler = args.iverilog or shutil.which("iverilog") or str(local_iverilog)
    compiler = Path(compiler).resolve()
    vvp = compiler.with_name("vvp.exe" if os.name == "nt" else "vvp")
    env = os.environ.copy()
    env["PATH"] = str(compiler.parent) + os.pathsep + env.get("PATH", "")
    yosys = (["wsl", "-d", "Ubuntu-22.04", "--exec", "env",
              "LD_LIBRARY_PATH=.tools/yosys/usr/lib/x86_64-linux-gnu", args.yosys]
             if os.name == "nt" else [args.yosys])

    def run(command, name):
        with (output / name).open("w", encoding="utf-8") as log:
            log.write("COMMAND " + json.dumps([str(x) for x in command], ensure_ascii=False) + "\n")
            log.flush()
            result = subprocess.run(command, cwd=ROOT, env=env, stdout=log,
                                    stderr=subprocess.STDOUT, timeout=120)
            log.write(f"\nEXIT_CODE {result.returncode}\n")
        if result.returncode:
            raise RuntimeError(f"Command failed; evidence retained in {output / name}")

    relative = output.relative_to(ROOT).as_posix()
    rtl = [f"experiments/p2-zcu104-daq/rtl/{name}.v"
           for name in ("axis_pattern_source", "axis_sync_fifo", "daq_stream_top")]
    run(yosys + ["-V"], "yosys-version.log")
    script = "\n".join([
        "read_verilog -sv " + " ".join(rtl),
        "chparam -set FRAME_WORDS 7 -set FIFO_DEPTH 3 daq_stream_top",
        "synth -top daq_stream_top -flatten -noabc", "check -assert", "stat",
        f"write_verilog -noattr {relative}/daq_stream_mapped.v",
        f"write_json {relative}/netlist.json", "",
    ])
    (output / "synthesis.ys").write_text(script, encoding="utf-8")
    run(yosys + ["-s", relative + "/synthesis.ys"], "synthesis.log")
    original_tb = (P2 / "tb/tb_capture_stream.sv").read_text(encoding="utf-8")
    instance = "daq_stream_top #(.FRAME_WORDS(FRAME_WORDS), .FIFO_DEPTH(3)) dut"
    if original_tb.count(instance) != 1:
        raise ValueError("Capture test instantiation changed; adapt the fixed-parameter netlist test explicitly")
    # The netlist has already elaborated parameters; all test stimuli/checks stay intact.
    (output / "tb_mapped.sv").write_text(original_tb.replace(instance, "daq_stream_top dut"), encoding="utf-8")
    for kind, sources in (("rtl", rtl + ["experiments/p2-zcu104-daq/tb/tb_capture_stream.sv"]),
                          ("mapped", [relative + "/daq_stream_mapped.v", relative + "/tb_mapped.sv"])):
        (output / kind).mkdir(exist_ok=True)
        executable = relative + "/" + kind + ".vvp"
        run([str(compiler), "-g2012", "-Wall", "-s", "tb_capture_stream", "-o", executable, *sources], kind + "-compile.log")
        run([str(vvp), executable, "+OUTDIR=" + relative + "/" + kind], kind + "-simulation.log")
    captures = []
    for kind in ("rtl", "mapped"):
        with (output / kind / "rtl_capture.csv").open(newline="", encoding="utf-8") as stream:
            captures.append(list(csv.DictReader(stream)))
    if len(captures[0]) != 84 or captures[0] != captures[1]:
        raise AssertionError("RTL/netlist capture differs; both original traces retained")
    design = json.loads((output / "netlist.json").read_text(encoding="utf-8"))
    cells = design["modules"]["daq_stream_top"]["cells"]
    counts = {}
    for cell in cells.values():
        counts[cell["type"]] = counts.get(cell["type"], 0) + 1
    summary = {"kind": "generic synthesis without ABC or device mapping; no hardware timing result",
               "frame_words": 7, "fifo_depth": 3, "captured_words": len(captures[0]),
               "all_capture_fields_equal": True, "cell_count": len(cells), "cell_types": counts}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: generic netlist and RTL both captured 84 identical beats; logs: {output}")


if __name__ == "__main__":
    main()
