"""Read-only XML and Tcl text inspection; never evaluates project Tcl."""
from pathlib import Path
import argparse
import json
import tkinter
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[4])
parser.add_argument("--project-script", type=Path)
args = parser.parse_args()
repo = args.repo.resolve()
p2 = repo / "experiments/p2-zcu104-daq"
vendor = repo / "vendor/xilinx-boardstore-2025.2"
board_dir = vendor / "boards/Xilinx/zcu104/1.1"
project_script = (args.project_script or p2 / "vivado/create_project.tcl").resolve()
print("METHOD: XML parsing / file references / Tcl info complete only; no Tcl evaluation or Vivado.")
print("REPO:", repo)
print("PROJECT_SCRIPT:", project_script)
record = json.loads((vendor / "download_record.json").read_text(encoding="utf-8-sig"))
assert record["ref"] == "2025.2"
total = 0
for entry in record["files"]:
    target = vendor / entry["path"]
    actual = target.stat().st_size
    assert actual == entry["bytes"], (target, actual, entry["bytes"])
    total += actual
    print("Recorded source size matches:", entry["path"], actual)
print("Original source files:", len(record["files"]), "bytes:", total)
for name in ("LICENSE", "LICENSE.md", "boards/Xilinx/zcu104/1.1/LICENSE"):
    text = (vendor / name).read_text(encoding="utf-8")
    assert 'Apache License, Version 2.0' in text
    print("Apache-2.0 notice:", name)
assert (vendor / "LICENSE").read_bytes() == (vendor / "LICENSE.md").read_bytes()
apache = (vendor / "APACHE-2.0.txt").read_text(encoding="utf-8")
assert "Version 2.0, January 2004" in apache and "END OF TERMS AND CONDITIONS" in apache
print("Apache full license present:", (vendor / "APACHE-2.0.txt").stat().st_size, "bytes")

board = ET.parse(board_dir / "board.xml").getroot()
pins = ET.parse(board_dir / "part0_pins.xml").getroot()
preset = ET.parse(board_dir / "preset.xml").getroot()
part0 = board.find("./components/component[@name='part0']")
assert part0 is not None
assert board.attrib["vendor"] == "xilinx.com"
assert board.attrib["name"] == "zcu104"
assert board.findtext("file_version") == "1.1"
assert part0.attrib["part_name"] == pins.attrib["part_name"] == "xczu7ev-ffvc1156-2-e"
print("Board:", board.attrib["vendor"] + ":" + board.attrib["name"] + ":part0:" + board.findtext("file_version"))
print("Part:", part0.attrib["part_name"])
references = {value for node in board.iter() for value in node.attrib.values()
              if value.endswith((".xml", ".jpeg", ".jpg", ".png", ".tcl"))}
item = json.loads((board_dir / "xitem.json").read_text(encoding="utf-8"))
references.add(item["config"]["items"][0]["infra"]["logo"])
for reference in sorted(references):
    assert (board_dir / reference).is_file(), reference
    print("Local board reference exists:", reference)
assert board.attrib["preset_file"] == "preset.xml"
required = {node.attrib["preset_proc"] for node in board.iter() if "preset_proc" in node.attrib}
provided = {node.attrib["preset_proc_name"] for node in preset.iter() if "preset_proc_name" in node.attrib}
assert required <= provided, sorted(required - provided)
assert "zynq_ultra_ps_e_preset" in required
ps_preset = preset.find("./ip_preset[@preset_proc_name='zynq_ultra_ps_e_preset']/ip")
assert ps_preset is not None and ps_preset.attrib["name"] == "zynq_ultra_ps_e"
print("Referenced preset names resolved:", ", ".join(sorted(required)))
print("PS preset IP:", ps_preset.attrib)
relative_board = (p2 / ".." / ".." / "vendor/xilinx-boardstore-2025.2/boards/Xilinx").resolve()
assert relative_board == board_dir.parent.parent.resolve()
print("Fixed repository path resolves:", relative_board)
interpreter = tkinter.Tcl()
print("Tcl version:", interpreter.call("info", "patchlevel"))
for name in ("create_project.tcl", "create_bd.tcl", "export_addresses.tcl", "build_offline.tcl"):
    path = project_script if name == "create_project.tcl" else p2 / "vivado" / name
    text = path.read_text(encoding="utf-8")
    complete = bool(int(interpreter.call("info", "complete", text)))
    print(name + ": complete=" + str(complete))
    assert complete
print("PASS: static checks only. Vivado catalog, BD, synthesis, implementation and A53 BSP remain unexecuted.")
