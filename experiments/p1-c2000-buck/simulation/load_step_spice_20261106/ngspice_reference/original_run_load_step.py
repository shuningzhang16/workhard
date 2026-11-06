"""One open-loop Buck load step; fresh outputs only, no LTspice/settings access."""
import argparse
import bisect
import csv
import json
import math
from pathlib import Path
import subprocess
import sys
import time

FIELDS = ('time_s', 'switch_voltage_v', 'output_v', 'inductor_current_a')
EVENT, END, DUTY = .050, .100, 2 / 9
WINDOWS = ((.0496, .060), (.0996, .100))


def put(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(value)


def write_csv(path, rows):
    with path.open('x', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def linux(path):
    path = Path(path).resolve()
    return '/mnt/' + path.drive[0].lower() + path.as_posix()[2:]


def unique_states(rows):
    result = []
    for row in rows:
        if result and abs(row['time_s'] - result[-1]['time_s']) < 1e-14:
            if any(abs(row[key] - result[-1][key]) > 1e-8 for key in FIELDS[2:]):
                raise ValueError('L/C state jump at a duplicate PWM timestamp')
            result[-1] = row
        else:
            if result and row['time_s'] < result[-1]['time_s']:
                raise ValueError('Nonmonotonic waveform time')
            result.append(row)
    return result


def interpolator(rows):
    rows = unique_states(rows)
    times = [row['time_s'] for row in rows]
    def at(t):
        j = bisect.bisect_right(times, t)
        if j == 0:
            if times[0] - t > 1e-12:
                raise ValueError('Requested point precedes saved waveform')
            return dict(rows[0], time_s=t)
        if j == len(rows):
            if t - times[-1] > 1e-12:
                raise ValueError('Requested point follows saved waveform')
            return dict(rows[-1], time_s=t)
        a, b = rows[j - 1], rows[j]
        fraction = (t - a['time_s']) / (b['time_s'] - a['time_s'])
        return {'time_s': t, **{key: a[key] + fraction * (b[key] - a[key]) for key in FIELDS[1:]}}
    return rows, at


def crop(rows, start, stop):
    rows, at = interpolator(rows)
    return [at(start)] + [r for r in rows if start < r['time_s'] < stop] + [at(stop)]


def window_metrics(rows, start, stop):
    # SPICE may save its first point just after tstart; do not extrapolate it.
    start, stop = max(start, rows[0]['time_s']), min(stop, rows[-1]['time_s'])
    rows = crop(rows, start, stop)
    result = {'start_s': start, 'end_s': stop, 'points_including_interpolated_endpoints': len(rows)}
    for key in FIELDS[2:]:
        values = [r[key] for r in rows]
        result[key + '_mean'] = sum((b['time_s'] - a['time_s']) * (a[key] + b[key]) / 2 for a, b in zip(rows, rows[1:])) / (stop - start)
        result[key + '_pp'] = max(values) - min(values)
    return result


def response(rows):
    # Continuous saved window covers the entire response, through END.
    after = [r for r in unique_states(rows) if r['time_s'] >= EVENT]
    low = min(after, key=lambda r: r['output_v'])
    high = max(after, key=lambda r: r['output_v'])
    last_outside = max((i for i, r in enumerate(after) if abs(r['output_v'] - 2) > .04), default=-1)
    entry = last_outside + 1
    recovery = None
    if entry < len(after) and after[-1]['time_s'] - after[entry]['time_s'] >= .002:
        recovery = after[entry]['time_s'] - EVENT
    return {'output_min_v': low['output_v'], 'output_min_time_s': low['time_s'],
            'output_max_v': high['output_v'], 'output_max_time_s': high['time_s'],
            'max_abs_deviation_v': max(abs(r['output_v'] - 2) for r in after),
            'recovery_to_2_percent_s': recovery,
            'recovery_definition': 'First saved point after the last point outside 2 V +/-2%, stays within through 100 ms, at least 2 ms observation margin; no new recovery-time pass threshold.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    print('OUTPUT=' + str(output), flush=True)
    source = args.repo.resolve() / 'experiments/p1-c2000-buck/simulation'
    snapshot = output / 'python_source'
    snapshot.mkdir()
    for name in ('buck_model.py', 'switching_buck.py'):
        put(snapshot / name, (source / name).read_text(encoding='utf-8'))
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(snapshot))
    from buck_model import Parameters
    from switching_buck import switching_cycle
    p = Parameters()
    original = (source / 'ideal_buck_fixed.cir').read_text(encoding='utf-8')
    put(output / 'original_fixed.cir', original)
    circuit = '\n'.join(line for line in original.splitlines() if not line.lower().startswith(('.tran', '.meas', '.end')))
    circuit += '\n* Open-loop load step: parallel added 4-ohm conductance at 50 ms.\nBSTEP out 0 I=V(out)*(time>=50m)/4\n'
    analysis = '.tran 0.25u 100m 49.6m 0.25u uic\n'
    measures = ''.join(f'.meas tran {label}_{signal}_mean AVG {expression} FROM={start} TO={stop}\n' for label, start, stop in [('pre','49.6m','50m'),('post','99.6m','100m')] for signal, expression in [('vout','V(out)'),('il','I(L1)')])
    common = circuit + analysis + measures + '.end\n'
    put(output / 'buck_load_step.cir', common)
    # LTspice-only ideal-L clarification; this script never launches LTspice.
    put(output / 'buck_load_step_ltspice.cir', common.replace('L1 sw out 220u IC=0', 'L1 sw out 220u Rser=0 IC=0'))
    ng_deck = circuit + analysis + measures + '.control\nset wr_singlescale\nset wr_vecnames\nset numdgt=17\nrun\nwrdata ngspice_full.dat v(sw) v(out) i(L1)\nquit\n.endc\n.end\n'
    put(output / 'buck_load_step_ngspice.cir', ng_deck)
    current = voltage = 0.0
    cycles, wave, samples = [], [], []
    for k in range(5000):
        load = 4.0 if k < 2500 else 2.0
        samples.append({'time_s': k * p.control_period_s, 'output_v': voltage, 'inductor_current_a': current, 'load_ohm': load, 'duty': DUTY})
        current, voltage, cycle, trace = switching_cycle(k, current, voltage, DUTY, 9.0, load, p, .25e-6, k >= 2480)
        cycles.append(cycle)
        wave.extend({key: r[key] for key in FIELDS} for r in trace)
    samples.append({'time_s': END, 'output_v': voltage, 'inductor_current_a': current, 'load_ohm': 2.0, 'duty': DUTY})
    write_csv(output / 'python_cycles.csv', cycles)
    write_csv(output / 'python_control_samples.csv', samples)
    # Full local reference retained; compact source-window CSVs are separate below.
    write_csv(output / 'python_full.csv', wave)
    put(output / 'parameters.json', json.dumps({'case':'open-loop fixed-duty load step; no PI, protection, devices or hardware', 'vin_v':9,'duty':DUTY,'pwm_hz':50000,'L_h':220e-6,'C_f':470e-6,'load_before_ohm':4,'load_after_ohm':2,'event_s':EVENT,'end_s':END,'initial_i_a':0,'initial_v_v':0,'python_max_step_s':.25e-6,'spice_pwm_rise_fall_s':1e-9,'edge_note':'SPICE preserves existing 1 ns area-compensated PWM ramps; Python has instantaneous PWM edges. Both have a hard load step at 50 ms, a PWM period boundary. No L/C reset.','comparison_windows_s':WINDOWS,'full_output_scope_s':[.0496,.1]},indent=2)+'\n')
    ngspice = args.repo.resolve() / 'experiments/p1-c2000-buck/.tools/ngspice/usr/bin/ngspice'
    command = ['wsl.exe','-d','Ubuntu-22.04','--cd',linux(output),'--','/usr/bin/env','PATH=/usr/bin:/bin',linux(ngspice),'-n','-b','buck_load_step_ngspice.cir']
    put(output / 'ngspice_command.json', json.dumps(command,indent=2)+'\n')
    if args.prepare_only:
        print('Prepared Python reference and decks; ngspice and LTspice not run.',flush=True)
        return
    started = time.monotonic()
    with (output / 'ngspice_stdout.txt').open('xb') as out, (output / 'ngspice_stderr.txt').open('xb') as err:
        result = subprocess.run(command,stdout=out,stderr=err,timeout=60)
    put(output / 'ngspice_run.json',json.dumps({'command':command,'exit_code':result.returncode,'elapsed_s':time.monotonic()-started},indent=2)+'\n')
    if result.returncode or not (output / 'ngspice_full.dat').exists():
        raise RuntimeError('ngspice failed; original logs and all outputs preserved')
    lines = (output / 'ngspice_full.dat').read_text(encoding='utf-8').splitlines()
    spice = [dict(zip(FIELDS,map(float,line.split()))) for line in lines[1:] if line.strip()]
    python_metrics = {label:window_metrics(wave,a,b) for label,a,b in [('pre',.0496,.05),('post',.0996,.1)]}
    spice_metrics = {label:window_metrics(spice,a,b) for label,a,b in [('pre',.0496,.05),('post',.0996,.1)]}
    _, python_at = interpolator(wave)
    differences = []
    for row in spice:
        if any(a <= row['time_s'] <= b for a,b in WINDOWS):
            py = python_at(row['time_s'])
            differences.append({'time_s':row['time_s'], 'output_delta_v':row['output_v']-py['output_v'], 'current_delta_a':row['inductor_current_a']-py['inductor_current_a']})
    for label,a,b in [('step',.0498,.0506),('post',.0996,.1)]:
        write_csv(output / ('ngspice_' + label + '_window.csv'),crop(spice,max(a,spice[0]['time_s']),b))
        write_csv(output / ('python_' + label + '_window.csv'),crop(wave,a,b))
    expected_i_pp = 7 * DUTY / (220e-6 * 50000)
    expected_v_pp = expected_i_pp / (8 * 50000 * 470e-6)
    checks = {}
    for label,expected_current in [('pre',.5),('post',1.)]:
        m = spice_metrics[label]
        checks[label + '_dc_voltage_within_1e_5_v'] = abs(m['output_v_mean'] - 2) < 1e-5
        checks[label + '_dc_current_within_1e_5_a'] = abs(m['inductor_current_a_mean'] - expected_current) < 1e-5
        checks[label + '_voltage_ripple_within_2_percent'] = abs(m['output_v_pp'] / expected_v_pp - 1) < .02
        checks[label + '_current_ripple_within_2_percent'] = abs(m['inductor_current_a_pp'] / expected_i_pp - 1) < .02
    checks['finite_spice_data'] = all(math.isfinite(v) for row in spice for v in row.values())
    summary = {'case':'fixed-duty open-loop load step, not a new closed-loop validation','python':python_metrics,'ngspice':spice_metrics,'response_python':response(wave),'response_ngspice':response(spice),'comparison_windows_s':WINDOWS,'compared_spice_points':len(differences),'max_abs_output_delta_v':max(abs(r['output_delta_v']) for r in differences),'max_abs_current_delta_a':max(abs(r['current_delta_a']) for r in differences),'spice_saved_first_s':spice[0]['time_s'],'spice_saved_last_s':spice[-1]['time_s'],'spice_saved_points':len(spice),'checks':checks,'tolerances':'Existing fixed-duty DC 1e-5 V/A and ripple 2% retained; transient differences/recovery are measured, without inventing a closed-loop pass threshold.','notes':'Exact window endpoints linearly interpolated within saved data; raw outputs unchanged. Duplicate Python PWM timestamps carry continuous L/C states. No LTspice run.'}
    put(output / 'summary.json',json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2),flush=True)
    if not all(checks.values()):
        raise AssertionError('Original physical checks failed; preserved evidence, thresholds not relaxed')


if __name__ == '__main__':
    main()
