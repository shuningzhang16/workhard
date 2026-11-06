"""Build the C core in a fresh directory and run native ctypes/PWM coupling."""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="host_c/closed_loop_results_" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    if not output.is_relative_to(ROOT):
        parser.error("--output must stay inside P1")
    output.mkdir(parents=True, exist_ok=False)
    build = output / "build"
    build.mkdir()
    commands = []
    launcher = ["wsl", "-d", "Ubuntu-22.04", "--"] if sys.platform == "win32" else []
    prefix = launcher + ["/usr/bin/env", "PATH=/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE=1",
                         "UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1"]
    flags = ["-std=c11", "-O1", "-g3", "-Wall", "-Wextra", "-Wpedantic", "-Wconversion",
             "-Wshadow", "-Wstrict-prototypes", "-Wmissing-prototypes", "-Werror",
             "-fno-fast-math", "-ffp-contract=off", "-fno-omit-frame-pointer",
             "-fsanitize=undefined", "-fno-sanitize-recover=all", "-fPIC", "-shared"]

    def run(arguments):
        command = prefix + arguments
        result = subprocess.run(command, cwd=ROOT, text=True, encoding="utf-8",
                                errors="replace", capture_output=True)
        commands.append({"argv": command, "returncode": result.returncode,
                         "stdout": result.stdout, "stderr": result.stderr})
        with (output / f"command_{len(commands):02d}.json").open("x", encoding="utf-8") as stream:
            json.dump(commands[-1], stream, indent=2)
        print("command " + json.dumps(arguments), flush=True)
        print(result.stdout, end="", flush=True)
        print(result.stderr, end="", file=sys.stderr, flush=True)
        if result.returncode:
            raise RuntimeError(f"Command failed ({result.returncode}); evidence retained in {output}")

    library = (build / "libbuck_control.so").relative_to(ROOT).as_posix()
    run(["/usr/bin/gcc", "--version"])
    run(["/usr/bin/uname", "-sm"])
    run(["/usr/bin/gcc", *flags, "host_c/buck_control.c", "-lm", "-o", library])
    for source in ("host_c/test_boundaries.c", "host_c/test_clear_measurements.c"):
        executable = (build / Path(source).stem).relative_to(ROOT).as_posix()
        run(["/usr/bin/gcc", *[flag for flag in flags if flag not in ("-fPIC", "-shared")],
             "-Ihost_c", "-Ifirmware", "host_c/buck_control.c", source, "-lm", "-o", executable])
        run(["./" + executable])
    python = "/usr/bin/python3" if launcher else sys.executable
    run([python, "host_c/closed_loop_worker.py", "--library", library,
         "--output", output.relative_to(ROOT).as_posix()])
    run([python, "host_c/check_c_takeover.py", "--library", library,
         "--output", output.relative_to(ROOT).as_posix()])
    with (output / "commands.json").open("x", encoding="utf-8") as stream:
        json.dump(commands, stream, indent=2)


if __name__ == "__main__":
    main()
