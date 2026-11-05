"""Compile/link the real C28x RAM image; never connect to a probe or run target code."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CGT = ".tools/ti-cgt/ti-cgt-c2000_25.11.1.LTS"
SDK = ".tools/c2000ware-26.02"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="firmware/results")
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    if not output.is_relative_to(ROOT):
        parser.error("Output must remain inside P1")
    output.mkdir(parents=True, exist_ok=True)
    build = ROOT / ".tools/target-build"
    build.mkdir(exist_ok=True)
    prefix = ["wsl", "-d", "Ubuntu-22.04", "--"] if sys.platform == "win32" else []
    commands = []

    def run(args):
        result = subprocess.run(prefix + args, cwd=ROOT, capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
        commands.append({"argv": prefix + args, "returncode": result.returncode,
                         "stdout": result.stdout, "stderr": result.stderr})
        (output / "commands.json").write_text(json.dumps(commands, indent=2) + "\n", encoding="utf-8")
        print("command " + json.dumps(args), flush=True)
        print(result.stdout + result.stderr, end="", flush=True)
        if result.returncode:
            raise RuntimeError(f"Real target command failed ({result.returncode}); logs retained")

    compiler = CGT + "/bin/cl2000"
    flags = ["--silicon_version=28", "--large_memory_model", "--unified_memory", "--abi=eabi",
             "--float_support=fpu32", "--tmu_support=tmu0", "--vcu_support=vcu0", "--cla_support=cla2",
             "--fp_mode=strict", "--c11", "--opt_level=2", "--symdebug:dwarf",
             "--display_error_number", "--emit_warnings_as_errors",
             "--include_path=" + CGT + "/include", "--include_path=host_c", "--include_path=firmware",
             "--include_path=" + SDK + "/driverlib/f28004x/driverlib",
             "--include_path=" + SDK + "/device_support/f28004x/common/include"]
    run([compiler, "--compiler_revision"])
    objects = []
    for source in ("host_c/buck_control.c", "firmware/target_main.c", "firmware/numeric_probe.c",
                   SDK + "/device_support/f28004x/common/source/f28004x_codestartbranch.asm"):
        obj = ".tools/target-build/" + Path(source).stem + ".obj"
        run([compiler, *flags, "--compile_only", source, "--output_file=" + obj])
        if not source.endswith("numeric_probe.c"):
            objects.append(obj)
    run([compiler, *flags, "--run_linker", *objects,
         SDK + "/device_support/f28004x/common/cmd/28004x_generic_ram_lnk.cmd",
         "--library=" + SDK + "/driverlib/f28004x/driverlib/ccs/Release/driverlib_eabi.lib",
         "--library=" + CGT + "/lib/rts2800_fpu32_eabi.lib", "--rom_model", "--entry_point=code_start",
         "--stack_size=0x300", "--heap_size=0", "--warn_sections", "--emit_warnings_as_errors",
         "--output_file=.tools/target-build/p1_f280049c_ram.out",
         "--map_file=.tools/target-build/p1_f280049c_ram.map",
         "--xml_link_info=.tools/target-build/p1_f280049c_ram_link.xml"])
    run([CGT + "/bin/ofd2000", "--xml", "--output=.tools/target-build/numeric_probe.xml", ".tools/target-build/numeric_probe.obj"])
    run([CGT + "/bin/ofd2000", "--xml", "--output=.tools/target-build/p1_image.xml", ".tools/target-build/p1_f280049c_ram.out"])
    for name in ("p1_f280049c_ram.map", "p1_f280049c_ram_link.xml", "numeric_probe.xml", "p1_image.xml"):
        shutil.copy2(build / name, output / name)
    summary = {"result": "real C28x compilation and RAM link succeeded; image NOT executed",
               "compiler": "25.11.1.LTS", "c2000ware": "26.02.00.00.LTS",
               "flags": flags, "image_path": ".tools/target-build/p1_f280049c_ram.out",
               "image_file_bytes": (build / "p1_f280049c_ram.out").stat().st_size,
               "pwm": "pins stay GPIO inputs, hardware OST forced and never cleared",
               "hardware_connection": False}
    (output / "build_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
