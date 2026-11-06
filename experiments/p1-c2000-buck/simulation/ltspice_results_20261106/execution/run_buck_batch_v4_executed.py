"""Run two finite LTspice Buck cases in a new ASCII directory; keep all evidence."""
from pathlib import Path
import csv
import datetime
import json
import math
import subprocess
import time

REPO = Path(r'E:\UserData\Documents\ChatGPT\硬件')
SIM = REPO / 'experiments/p1-c2000-buck/simulation'
EXE = Path(r'C:\Users\Administrator\AppData\Local\Programs\ADI\LTspice\LTspice.exe')
FIELDS = ('time_s', 'switch_voltage_v', 'output_v', 'inductor_current_a')

def put(path, text):
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(text)

def write_csv(path, rows):
    with path.open('x', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def read_csv(path):
    with path.open(encoding='utf-8', newline='') as handle:
        return [{key: float(row[key]) for key in FIELDS} for row in csv.DictReader(handle)]

def read_raw(path):
    blob = path.read_bytes()
    encoding = 'utf-16' if blob.startswith((b'\xff\xfe', b'\xfe\xff')) else ('utf-16-le' if b'\x00' in blob[:32] else 'utf-8')
    lines = [line for line in blob.decode(encoding).splitlines() if line.strip()]
    variable_start = lines.index('Variables:')
    value_start = lines.index('Values:')
    variables = [line.split()[1].lower() for line in lines[variable_start + 1:value_start]]
    expected_points = int(next(line.split(':', 1)[1] for line in lines if line.startswith('No. Points:')))
    tokens = ' '.join(lines[value_start + 1:]).split()
    width = len(variables) + 1
    if len(tokens) != expected_points * width:
        raise ValueError('ASCII raw shape differs from header; inspect preserved raw file.')
    indices = [variables.index(name) for name in ('time', 'v(sw)', 'v(out)', 'i(l1)')]
    rows = []
    for i in range(expected_points):
        offset = i * width
        if int(tokens[offset]) != i:
            raise ValueError('Unexpected raw point index.')
        values = [float(value) for value in tokens[offset + 1:offset + width]]
        row = dict(zip(FIELDS, (values[index] for index in indices)))
        row['time_s'] += float(next(line.split(':', 1)[1] for line in lines if line.startswith('Offset:')))
        rows.append(row)
    return rows

def metrics(rows):
    start, end = rows[0]['time_s'], rows[-1]['time_s']
    if not end > start or any(b['time_s'] < a['time_s'] for a, b in zip(rows, rows[1:])):
        raise ValueError('Expected nondecreasing finite-window time samples.')
    result = {'window_start_s': start, 'window_end_s': end, 'saved_points': len(rows)}
    for key in ('output_v', 'inductor_current_a'):
        values = [row[key] for row in rows]
        result[key + '_time_mean'] = sum((b['time_s'] - a['time_s']) * (a[key] + b[key]) / 2 for a, b in zip(rows, rows[1:])) / (end - start)
        result[key + '_window_pp'] = max(values) - min(values)
    return result

def main():
    identity = subprocess.check_output(['whoami'], text=True).strip()
    if identity.lower().endswith('\\codexsandboxoffline'):
        raise SystemExit('Run using the new administrator execution context.')
    output = Path(r'E:\codex_ltspice_runs') / datetime.datetime.now().strftime('buck_%Y%m%d_%H%M%S_%f')
    output.mkdir(parents=True, exist_ok=False)
    print('EVIDENCE_DIR=' + str(output), flush=True)
    source = (SIM / 'ideal_buck_fixed.cir').read_text(encoding='utf-8')
    put(output / 'original_source.cir', source)
    if 'L1 sw out 220u IC=0' not in source:
        raise ValueError('Source topology changed; inspect original_source.cir before adapting.')
    circuit = '\n'.join(line for line in source.splitlines() if not line.lower().startswith(('.tran', '.meas', '.end')))
    circuit = circuit.replace('L1 sw out 220u IC=0', 'L1 sw out 220u Rser=0 IC=0')
    circuit += '\n* LTspice-only ideal-L clarification: explicit zero series resistance.\n.options plotwinsize=0 numdgt=15 reltol=1e-7 abstol=1e-10 vntol=1e-9\n.save V(sw) V(out) I(L1)\n'
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    commands = []
    samples = {}
    for label, tran in (('steady', '.tran 0.25u 60m 59.6m 0.05u uic'), ('startup', '.tran 0.05u 200u 0 0.05u uic')):
        case = output / label
        case.mkdir(exist_ok=False)
        deck = case / (label + '.cir')
        measures = '\n'.join(line for line in source.splitlines() if line.lower().startswith('.meas')) if label == 'steady' else ''
        put(deck, circuit + tran + '\n' + measures + '\n.end\n')
        command = [str(EXE), '-b', '-ascii', str(deck)]
        put(case / 'command.json', json.dumps(command, indent=2) + '\n')
        started = time.monotonic()
        with (case / 'stdout.txt').open('xb') as stdout, (case / 'stderr.txt').open('xb') as stderr:
            process = subprocess.Popen(command, cwd=case, stdout=stdout, stderr=stderr, startupinfo=startup)
            try:
                exit_code = process.wait(timeout=45)
                timed_out = False
            except subprocess.TimeoutExpired:
                process.terminate()
                exit_code = process.wait(timeout=10)
                timed_out = True
        result = {'command': command, 'pid': process.pid, 'exit_code': exit_code, 'timed_out': timed_out, 'elapsed_seconds': time.monotonic() - started, 'outputs': {suffix: {'exists': deck.with_suffix(suffix).exists(), 'bytes': deck.with_suffix(suffix).stat().st_size if deck.with_suffix(suffix).exists() else 0} for suffix in ('.raw', '.log')}}
        put(case / 'run.json', json.dumps(result, indent=2) + '\n')
        commands.append(result)
        print(json.dumps({'label': label, **result}, indent=2), flush=True)
        if timed_out or exit_code != 0 or not deck.with_suffix('.raw').exists():
            raise RuntimeError('LTspice did not complete; all partial outputs retained.')
        samples[label] = read_raw(deck.with_suffix('.raw'))
        write_csv(case / (label + '.csv'), samples[label])
    references = {'python': SIM / 'switching_results/fixed_duty_0p25us_waveform.csv', 'ngspice': SIM / 'spice_results/steady.csv'}
    windows = {'ltspice': metrics(samples['steady'])}
    for name, path in references.items():
        rows = read_csv(path)
        write_csv(output / (name + '_reference.csv'), rows)
        windows[name] = metrics(rows)
    keys = ('output_v_time_mean', 'inductor_current_a_time_mean', 'output_v_window_pp', 'inductor_current_a_window_pp')
    comparison = []
    for key in keys:
        row = {'metric': key, **{name: value[key] for name, value in windows.items()}}
        for name in references:
            row['ltspice_minus_' + name] = windows['ltspice'][key] - windows[name][key]
            row['relative_to_' + name + '_percent'] = 100 * (windows['ltspice'][key] / windows[name][key] - 1)
        comparison.append(row)
    write_csv(output / 'comparison.csv', comparison)
    lt = windows['ltspice']
    first = samples['startup'][0]
    expected_i_pp = 7 * (2 / 9) / (220e-6 * 50000)
    expected_v_pp = expected_i_pp / (8 * 50000 * 470e-6)
    checks = {'dc_voltage_within_1e_5_v': abs(lt['output_v_time_mean'] - 2) < 1e-5, 'dc_current_within_1e_5_a': abs(lt['inductor_current_a_time_mean'] - .5) < 1e-5, 'voltage_ripple_formula_within_2_percent': abs(lt['output_v_window_pp'] / expected_v_pp - 1) < .02, 'current_ripple_formula_within_2_percent': abs(lt['inductor_current_a_window_pp'] / expected_i_pp - 1) < .02, 'initial_saved_point_within_1ns': 0 <= first['time_s'] <= 1e-9, 'initial_output_near_zero': abs(first['output_v']) < 1e-6, 'initial_current_near_zero': abs(first['inductor_current_a']) < 1e-6, 'finite_data': all(math.isfinite(value) for rows in samples.values() for row in rows for value in row.values())}
    summary = {'model': 'Ideal fixed-duty Buck, not devices, closed-loop, protection or hardware', 'identity': identity, 'circuit_adaptation': 'Explicit Rser=0 prevents LTspice default 1 milliohm; no electrical parameter otherwise changed. Compression disabled, ASCII raw, numdgt=15.', 'initial_conditions': 'L1 IC=0, C1 IC=0 and uic; same finite 1 ns area-compensated edges as ngspice. Python reference uses instantaneous edges.', 'windows': windows, 'comparison': comparison, 'startup_first_saved_point': first, 'startup_saved_points': len(samples['startup']), 'checks': checks, 'commands': commands, 'reference_files': {name: str(path) for name, path in references.items()}}
    put(output / 'summary.json', json.dumps(summary, indent=2) + '\n')
    print(json.dumps({'windows': windows, 'comparison': comparison, 'first': first, 'checks': checks}, indent=2), flush=True)
    if not all(checks.values()):
        raise AssertionError('Original DC/ripple/initial checks failed; evidence retained and no tolerances relaxed.')

if __name__ == '__main__':
    main()
