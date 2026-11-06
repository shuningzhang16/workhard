"""Run two LTspice R-L equivalents; report numerical differences, not PLECS results."""
from pathlib import Path
from datetime import datetime
import csv
import json
import math
import subprocess
import time
from reference_rl import reference

HERE = Path(__file__).resolve().parent
EXE = Path(r"C:\Users\Administrator\AppData\Local\Programs\ADI\LTspice\LTspice.exe")
OUTPUT_ROOT = Path(r"E:\codex_ltspice_runs")
FIELDS = ("time_s", "v1_v", "v2_primary_v", "current_a")

def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data if isinstance(data, bytes) else data.encode("utf-8"))

def json_file(path, value):
    put(path, json.dumps(value, indent=2) + "\n")

def csv_file(path, rows):
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def read_raw(path):
    data = path.read_bytes()
    encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else (
        "utf-16-le" if b"\x00" in data[:32] else "utf-8")
    lines = [line for line in data.decode(encoding).splitlines() if line.strip()]
    variables_at, values_at = lines.index("Variables:"), lines.index("Values:")
    names = [line.split()[1].lower() for line in lines[variables_at+1:values_at]]
    count = int(next(line.split(":", 1)[1] for line in lines if line.startswith("No. Points:")))
    time_offset = float(next(line.split(":", 1)[1] for line in lines if line.startswith("Offset:")))
    tokens = " ".join(lines[values_at+1:]).split()
    width = len(names) + 1
    if len(tokens) != count * width:
        raise ValueError("RAW data shape differs from its header; original retained.")
    indices = [names.index(name) for name in ("time", "v(p)", "v(s)", "i(l1)")]
    rows = []
    for index in range(count):
        pos = index * width
        if int(tokens[pos]) != index:
            raise ValueError("RAW point index differs from expected sequence.")
        values = [float(value) for value in tokens[pos+1:pos+width]]
        row = dict(zip(FIELDS, (values[column] for column in indices)))
        row["time_s"] += time_offset
        rows.append(row)
    return rows

def metrics(rows):
    span = rows[-1]["time_s"] - rows[0]["time_s"]
    if span <= 0 or any(b["time_s"] < a["time_s"] for a,b in zip(rows,rows[1:])):
        raise ValueError("Nonpositive window or descending RAW times.")
    if not all(math.isfinite(value) for row in rows for value in row.values()):
        raise ValueError("Nonfinite RAW value.")
    def integral(function):
        return sum((b["time_s"]-a["time_s"])*(function(a)+function(b))/2
                   for a,b in zip(rows,rows[1:]))
    e1 = integral(lambda r: r["v1_v"]*r["current_a"])
    e2 = integral(lambda r: r["v2_primary_v"]*r["current_a"])
    i2 = integral(lambda r: r["current_a"]**2)
    start, end = rows[0]["current_a"], rows[-1]["current_a"]
    return {"window_start_s":rows[0]["time_s"],"window_end_s":rows[-1]["time_s"],
            "saved_points":len(rows),"p1_w":e1/span,"p2_w":e2/span,
            "r_loss_w":0.5*i2/span,"i_rms_a":math.sqrt(i2/span),
            "i_peak_a":max(abs(r["current_a"]) for r in rows),
            "i_start_a":start,"i_end_a":end,
            "energy_residual_j":e1-e2-0.5*i2-0.5*100e-6*(end**2-start**2)}

def main():
    output = OUTPUT_ROOT / ("dab_rl_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    output.mkdir(parents=True, exist_ok=False)
    print("EVIDENCE_DIR="+str(output),flush=True)
    put(output/"run_dab_rl.py",Path(__file__).read_bytes())
    put(output/"reference_rl.py",(HERE/"reference_rl.py").read_bytes())
    measured, comparison, commands = {}, [], []
    for label,phase in (("forward",30),("reverse",-30)):
        case = output/label
        case.mkdir()
        circuit = case/("dab_sps_"+label+".cir")
        put(circuit,(HERE/circuit.name).read_bytes())
        command = [str(EXE),"-b","-ascii",str(circuit)]
        json_file(case/"command.json",command)
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        started = time.monotonic()
        with (case/"stdout.txt").open("xb") as stdout, (case/"stderr.txt").open("xb") as stderr:
            process = subprocess.Popen(command,cwd=case,stdout=stdout,stderr=stderr,startupinfo=startup)
            try:
                exit_code = process.wait(timeout=45)
                timed_out = False
            except subprocess.TimeoutExpired:
                process.terminate()
                exit_code = process.wait(timeout=10)
                timed_out = True
        run = {"phase_deg":phase,"command":command,"pid":process.pid,
               "exit_code":exit_code,"timed_out":timed_out,
               "elapsed_seconds":time.monotonic()-started}
        json_file(case/"run.json",run)
        commands.append(run)
        print(json.dumps(run),flush=True)
        if timed_out or exit_code != 0 or not circuit.with_suffix(".raw").is_file():
            raise RuntimeError("LTspice did not complete; partial outputs retained.")
        rows = read_raw(circuit.with_suffix(".raw"))
        csv_file(case/"waveform.csv",rows)
        actual, expected = metrics(rows), reference(phase)
        measured[label] = {"phase_deg":phase,"ltspice":actual,"analytic":expected,
                          "expected_power_sign_observed":actual["p1_w"]*phase>0 and actual["p2_w"]*phase>0}
        json_file(case/"comparison.json",measured[label])
        for name in ("p1_w","p2_w","r_loss_w","i_rms_a","i_peak_a","i_start_a","i_end_a","energy_residual_j"):
            comparison.append({"case":label,"phase_deg":phase,"metric":name,
                               "ltspice":actual[name],"analytic":expected[name],
                               "difference":actual[name]-expected[name]})
    csv_file(output/"comparison.csv",comparison)
    summary = {"scope":"Actual LTspice independent primary-referred R-L equivalents; NOT PLECS model validation, hardware, switches or control",
               "model":{"voltage_v":24,"frequency_hz":20000,"inductance_h":100e-6,"resistance_ohm":0.5,
                        "initial_current_a":0,"periods":120,"stop_time_s":0.006,
                        "recorded_window_s":[0.00595,0.006],"maximum_step_s":50e-9,
                        "source_edge_s":1e-12,"edge_placement":"centered on ideal analytic switching times"},
               "power_sign":"i flows from VP through L/R to VS; P1=mean(VP*i), P2=mean(VS*i). Positive forward; both negative in reverse.",
               "comparison_note":"Analytic reference has instantaneous edges; LTspice has explicitly declared 1 ps numerical transitions. No pass threshold is introduced.",
               "cases":measured,"commands":commands}
    json_file(output/"summary.json",summary)
    print(json.dumps(summary,indent=2),flush=True)

if __name__ == "__main__":
    main()
