"""Measure finite source/FIFO interface latency using actual Icarus RTL execution."""

import argparse
import csv
import json
import os
from pathlib import Path
import shutil

from run_sim import ROOT, run_logged


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results/performance_fifo_boundaries"))
    parser.add_argument("--iverilog")
    args = parser.parse_args()
    local_tool = ROOT / ".tools/ucrt64/bin/iverilog.exe"
    compiler = args.iverilog or shutil.which("iverilog") or (str(local_tool) if local_tool.exists() else None)
    if not compiler:
        parser.error("Icarus Verilog is required")
    compiler = Path(compiler).resolve()
    simulator = compiler.parent / ("vvp.exe" if os.name == "nt" else "vvp")
    env = os.environ.copy()
    env["PATH"] = str(compiler.parent) + os.pathsep + env.get("PATH", "")
    output = (ROOT / args.output).resolve()
    output.relative_to(ROOT)
    output.mkdir(parents=True, exist_ok=True)
    (ROOT / "build").mkdir(exist_ok=True)
    run_logged([str(compiler), "-V"], output / "iverilog-version.log", env)
    summaries = []
    for depth in (1, 3, 16):
        for backpressure in (0, 1):
            name = f"depth{depth}_b{backpressure}"
            case = output / name
            case.mkdir(exist_ok=True)
            executable = f"build/fifo_latency_{name}.vvp"
            run_logged([str(compiler), "-g2012", "-Wall", "-s", "tb_fifo_latency",
                        f"-Ptb_fifo_latency.DEPTH={depth}",
                        f"-Ptb_fifo_latency.BACKPRESSURE={backpressure}", "-o", executable,
                        "rtl/axis_pattern_source.v", "rtl/axis_sync_fifo.v", "tb/tb_fifo_latency.sv"],
                       case / "compile.log", env)
            run_logged([str(simulator), executable, "+OUTDIR=" + case.relative_to(ROOT).as_posix()],
                       case / "simulation.log", env)
            summary = json.loads((case / "summary.json").read_text(encoding="utf-8"))
            with (case / "cycles.csv").open(encoding="utf-8", newline="") as stream:
                cycles = list(csv.DictReader(stream))
            with (case / "beat_events.csv").open(encoding="utf-8", newline="") as stream:
                events = list(csv.DictReader(stream))
            with (case / "epochs.csv").open(encoding="utf-8", newline="") as stream:
                epochs = list(csv.DictReader(stream))
            delivered = [row for row in events if row["event"] == "OUTPUT"]
            dropped = [row for row in events if row["event"] == "RESET_DISCARD"]
            # Check completeness and recompute reported latencies from raw edge timestamps.
            latencies = [int(row["output_accept_cycle"]) - int(row["input_accept_cycle"]) for row in delivered]
            waits = [int(row["input_accept_cycle"]) - int(row["first_offer_cycle"]) for row in delivered]
            totals = [wait + latency for wait, latency in zip(waits, latencies)]
            if (summary["result"] != "PASS" or len(cycles) != summary["cycles"]
                    or [int(row["cycle"]) for row in cycles] != list(range(1, len(cycles) + 1))
                    or sorted(int(row["accepted_id"]) for row in events) != list(range(summary["accepted"]))
                    or len(delivered) != summary["output"] or len(dropped) != summary["reset_discarded"]
                    or summary["pending"] != 0 or sum(latencies) != summary["latency_sum_cycles"]
                    or min(latencies) != summary["latency_min_cycles"]
                    or max(latencies) != summary["latency_max_cycles"]
                    or any(int(row["fifo_residence_cycles"]) != latency for row, latency in zip(delivered, latencies))
                    or any(int(row["offer_to_output_cycles"]) != total for row, total in zip(delivered, totals))):
                raise RuntimeError(f"Incomplete or inconsistent measurement; evidence retained in {case}")
            # Audit first-offer and handshake timestamps against the complete public-port trace.
            for event in events:
                first, accept = int(event["first_offer_cycle"]), int(event["input_accept_cycle"])
                if first > accept or int(event["source_wait_cycles"]) != accept - first:
                    raise RuntimeError(f"Invalid source wait: {case}, {event}")
                for edge in range(first, accept + 1):
                    row = cycles[edge - 1]
                    if (row["resetn"] != "1" or row["in_valid"] != "1"
                            or row["in_data_hex"] != event["data_hex"]
                            or row["in_ready"] != ("1" if edge == accept else "0")):
                        raise RuntimeError(f"Offer/input timestamp disagrees with ports: {case}, edge {edge}")
                if first > 1 and cycles[first - 2]["resetn"] == "1" and cycles[first - 2]["in_valid"] == "1" and cycles[first - 2]["in_ready"] == "0":
                    raise RuntimeError(f"First offer omitted prior source wait: {case}, {event}")
                if event["event"] == "OUTPUT":
                    row = cycles[int(event["output_accept_cycle"]) - 1]
                    if row["out_valid"] != "1" or row["out_ready"] != "1" or row["out_data_hex"] != event["data_hex"]:
                        raise RuntimeError(f"Output timestamp disagrees with ports: {case}, {event}")
                elif cycles[int(event["reset_cycle"]) - 1]["resetn"] != "0":
                    raise RuntimeError(f"Discard without reset: {case}, {event}")
            for epoch in epochs:
                matching = [event for event in events if event["epoch"] == epoch["epoch"]]
                if (int(epoch["accepted"]) != len(matching)
                        or int(epoch["output"]) != sum(event["event"] == "OUTPUT" for event in matching)
                        or int(epoch["reset_discarded"]) != sum(event["event"] == "RESET_DISCARD" for event in matching)
                        or int(epoch["accepted"]) != int(epoch["output"]) + int(epoch["reset_discarded"]) + int(epoch["pending"])):
                    raise RuntimeError(f"Epoch accounting mismatch: {case}, {epoch}")
            summary["mean_fifo_residence_cycles"] = sum(latencies) / len(latencies)
            summary["mean_source_wait_cycles"] = sum(waits) / len(waits)
            summary["max_source_wait_cycles"] = max(waits)
            summary["mean_offer_to_output_cycles"] = sum(totals) / len(totals)
            summary["max_offer_to_output_cycles"] = max(totals)
            summary["trace_rows"] = len(cycles)
            summary["beat_event_rows"] = len(events)
            summaries.append(summary)
            print(f"PASS {name}: {summary['accepted']} accepted, {summary['output']} output, "
                  f"{summary['reset_discarded']} reset-discarded, latency {min(latencies)}..{max(latencies)} clocks")
    with (output / "measurements.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    (output / "summary.json").write_text(json.dumps({
        "scope": "actual Icarus source/FIFO RTL; no DMA, DDR, ADC or hardware execution",
        "latency_definition": "latency_* and fifo_residence: output_accept - input_accept; delivered beats only",
        "source_wait_definition": "input_accept - first_offer; source valid first sampled on a rising edge",
        "offer_to_output_definition": "output_accept - first_offer; not ADC acquisition or DMA latency",
        "backpressure_0": "ready throughout each 64-cycle flow phase",
        "backpressure_1": "ready for first 3 of each fixed 8-cycle period in each 64-cycle flow phase",
        "common_phases": "startup reset; flow; blocked sink for depth+8; reset 3; flow; final drain depth+8",
        "cases": summaries,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"PASS {len(summaries)} finite RTL measurements; full traces: {output}")


if __name__ == "__main__":
    main()
