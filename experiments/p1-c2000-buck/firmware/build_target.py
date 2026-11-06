"""Compile/link the real C28x RAM image; never connect to a probe or run target code."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from inspect_target import inspect_results

ROOT = Path(__file__).resolve().parents[1]
CGT = ".tools/ti-cgt/ti-cgt-c2000_25.11.1.LTS"
SDK = ".tools/c2000ware-26.02"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="firmware/results_" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    if not output.is_relative_to(ROOT):
        parser.error("Output must remain inside P1")
    output.mkdir(parents=True, exist_ok=False)
    build = output / "build"
    build.mkdir()
    prefix = ["wsl", "-d", "Ubuntu-22.04", "--"] if sys.platform == "win32" else []
    commands = []

    def run(args):
        result = subprocess.run(prefix + args, cwd=ROOT, capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
        commands.append({"argv": prefix + args, "returncode": result.returncode,
                         "stdout": result.stdout, "stderr": result.stderr})
        with (output / f"command_{len(commands):02d}.json").open("x", encoding="utf-8") as stream:
            json.dump(commands[-1], stream, indent=2)
        print("command " + json.dumps(args), flush=True)
        lines = (result.stdout + result.stderr).splitlines()
        advice = [line for line in lines if "advice #" in line]
        print("\n".join(line for line in lines if "advice #" not in line), flush=True)
        if advice:
            print(f"{len(advice)} compiler performance advice lines retained in commands.json", flush=True)
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
        obj = (build / (Path(source).stem + ".obj")).relative_to(ROOT).as_posix()
        run([compiler, *flags, "--compile_only", source, "--output_file=" + obj])
        if not source.endswith("numeric_probe.c"):
            objects.append(obj)
    run([compiler, *flags, "--run_linker", *objects,
         SDK + "/device_support/f28004x/common/cmd/28004x_generic_ram_lnk.cmd",
         "--library=" + SDK + "/driverlib/f28004x/driverlib/ccs/Release/driverlib_eabi.lib",
         "--library=" + CGT + "/lib/rts2800_fpu32_eabi.lib", "--rom_model", "--entry_point=code_start",
         "--diag_remark=10063", "--issue_remarks",
         "--stack_size=0x300", "--heap_size=0", "--warn_sections", "--emit_warnings_as_errors",
         "--output_file=" + (build / "p1_f280049c_ram.out").relative_to(ROOT).as_posix(),
         "--map_file=" + (build / "p1_f280049c_ram.map").relative_to(ROOT).as_posix(),
         "--xml_link_info=" + (build / "p1_f280049c_ram_link.xml").relative_to(ROOT).as_posix()])
    run([CGT + "/bin/ofd2000", "--xml", "--obj_display=none,header,sections,rawdata", "--output=" + (build / "numeric_probe.xml").relative_to(ROOT).as_posix(), (build / "numeric_probe.obj").relative_to(ROOT).as_posix()])
    run([CGT + "/bin/ofd2000", "--xml", "--obj_display=none,header,sections,symbols,norawdata", "--output=" + (build / "p1_image.xml").relative_to(ROOT).as_posix(), (build / "p1_f280049c_ram.out").relative_to(ROOT).as_posix()])
    for name in ("p1_f280049c_ram.map", "p1_f280049c_ram_link.xml", "numeric_probe.xml", "p1_image.xml"):
        shutil.copy2(build / name, output / name)
    numeric = inspect_results(output)
    summary = {"result": "real C28x compilation and RAM link succeeded; image NOT executed",
               "compiler": "25.11.1.LTS", "c2000ware": "26.02.00.00.LTS",
               "flags": flags, "image_path": (build / "p1_f280049c_ram.out").relative_to(ROOT).as_posix(),
               "image_file_bytes": (build / "p1_f280049c_ram.out").stat().st_size,
               "pwm": "pins stay GPIO inputs, hardware OST forced and never cleared",
               "hardware_connection": False, "target_numeric_format": numeric["target_format"],
               "max_abs_compiled_constant_difference": numeric["max_abs_constant_difference"]}
    (output / "build_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    with (output / "commands.json").open("x", encoding="utf-8") as stream:
        json.dump(commands, stream, indent=2)
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
