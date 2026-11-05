"""Check Tcl text completeness only; never execute or emulate Vivado commands."""

from pathlib import Path
import argparse
import tkinter

ROOT = Path(__file__).resolve().parents[1]
interpreter = tkinter.Tcl()
lines = [f"Tcl version: {interpreter.call('info', 'patchlevel')}",
         "Method: Tcl info complete on file text (no evaluation).",
         "This checks balanced Tcl command text only, not Vivado commands, IP parameters, synthesis or connectivity."]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, default=Path("results/top_integration/tcl_text_check.log"))
args = parser.parse_args()
for name in ("create_project.tcl", "create_bd.tcl", "export_addresses.tcl"):
    path = ROOT / "vivado" / name
    complete = bool(int(interpreter.call("info", "complete", path.read_text(encoding="utf-8"))))
    lines.append(f"vivado/{name}: complete={complete}")
    if not complete:
        raise RuntimeError("Incomplete Tcl text: " + str(path))
output = (ROOT / args.output).resolve()
output.relative_to(ROOT)
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
