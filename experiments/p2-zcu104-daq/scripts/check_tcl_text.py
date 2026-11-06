"""Check Tcl text completeness only; never execute or emulate Vivado commands."""

from pathlib import Path
from datetime import datetime
import argparse
import tkinter

ROOT = Path(__file__).resolve().parents[1]
interpreter = tkinter.Tcl()
lines = [f"Tcl version: {interpreter.call('info', 'patchlevel')}",
         "Method: Tcl info complete on file text (no evaluation).",
         "This checks balanced Tcl command text only, not Vivado commands, IP parameters, synthesis or connectivity."]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, help="new log file inside P2; existing files are never overwritten")
args = parser.parse_args()
for name in ("create_project.tcl", "create_bd.tcl", "export_addresses.tcl", "build_offline.tcl"):
    path = ROOT / "vivado" / name
    complete = bool(int(interpreter.call("info", "complete", path.read_text(encoding="utf-8"))))
    lines.append(f"vivado/{name}: complete={complete}")
    if not complete:
        raise RuntimeError("Incomplete Tcl text: " + str(path))
relative_output = args.output if args.output is not None else (
    Path("results") / ("tcl_text_check_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")) / "tcl_text_check.log")
output = (ROOT / relative_output).resolve()
output.relative_to(ROOT)
output.parent.mkdir(parents=True, exist_ok=args.output is not None)
with output.open("x", encoding="utf-8") as stream:
    stream.write("\n".join(lines) + "\n")
print("\n".join(lines))
print("Output: " + str(output))
