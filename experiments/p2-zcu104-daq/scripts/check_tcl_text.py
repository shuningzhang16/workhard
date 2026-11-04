"""Check Tcl text completeness only; never execute or emulate Vivado commands."""

from pathlib import Path
import tkinter

ROOT = Path(__file__).resolve().parents[1]
interpreter = tkinter.Tcl()
lines = [f"Tcl version: {interpreter.call('info', 'patchlevel')}",
         "Method: Tcl info complete on file text (no evaluation).",
         "This checks balanced Tcl command text only, not Vivado commands, IP parameters, synthesis or connectivity."]
for name in ("create_project.tcl", "create_bd.tcl"):
    path = ROOT / "vivado" / name
    complete = bool(int(interpreter.call("info", "complete", path.read_text(encoding="utf-8"))))
    lines.append(f"vivado/{name}: complete={complete}")
    if not complete:
        raise RuntimeError("Incomplete Tcl text: " + str(path))
output = ROOT / "results/top_integration/tcl_text_check.log"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
