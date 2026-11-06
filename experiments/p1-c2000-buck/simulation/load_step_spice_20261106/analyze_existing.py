"""Analyze preserved Buck load-step files only. No simulator or user settings."""
import argparse
import bisect
import csv
import json
import math
from pathlib import Path

VALUES = ('output_v', 'inductor_current_a')


def save(path, text):
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(text)


def csv_save(path, rows):
    with path.open('x', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


class Wave:
    def __init__(self, rows):
        for a, b in zip(rows, rows[1:]):
            if b['time_s'] < a['time_s'] - 1e-14:
                raise ValueError('Input has genuinely decreasing times')
        # PWM edge endpoints can be equal or differ only by floating rounding.
        # Sort for interpolation; source files remain untouched.
        ordered = sorted(rows, key=lambda r: r['time_s'])
        self.rows = []
        for row in ordered:
            if self.rows and row['time_s'] == self.rows[-1]['time_s']:
                if any(abs(row[k] - self.rows[-1][k]) > 1e-8 for k in VALUES):
                    raise ValueError('L/C state jump at the same saved time')
                continue
            self.rows.append(row)
        self.times = [r['time_s'] for r in self.rows]

    def at(self, t):
        if not self.times[0] <= t <= self.times[-1]:
            raise ValueError('Endpoint outside saved data; extrapolation prohibited')
        j = bisect.bisect_left(self.times, t)
        if self.times[j] == t:
            return dict(self.rows[j])
        a, b = self.rows[j - 1], self.rows[j]
        f = (t - a['time_s']) / (b['time_s'] - a['time_s'])
        return {'time_s': t, **{k: a[k] + f * (b[k] - a[k]) for k in VALUES}}

    def crop(self, a, b):
        return [self.at(a)] + [r for r in self.rows if a < r['time_s'] < b] + [self.at(b)]

    def metrics(self, a, b):
        rows = self.crop(a, b)
        result = {'start_s': a, 'end_s': b, 'pwm_periods': (b-a)/20e-6}
        for key in VALUES:
            result[key + '_mean'] = sum((q['time_s']-p['time_s'])*(p[key]+q[key])/2 for p,q in zip(rows,rows[1:]))/(b-a)
            result[key + '_pp'] = max(r[key] for r in rows)-min(r[key] for r in rows)
        return result

    def response(self):
        rows = [r for r in self.rows if r['time_s'] >= .05]
        low, high = min(rows,key=lambda r:r['output_v']), max(rows,key=lambda r:r['output_v'])
        last = max((i for i,r in enumerate(rows) if abs(r['output_v']-2)>.04),default=-1)
        entry = last + 1
        recovery = rows[entry]['time_s']-.05 if entry<len(rows) and rows[-1]['time_s']-rows[entry]['time_s']>=.002 else None
        return {'minimum_output_v':low['output_v'],'minimum_time_s':low['time_s'],'maximum_output_v':high['output_v'],'maximum_time_s':high['time_s'],'max_abs_output_deviation_v':max(abs(r['output_v']-2) for r in rows),'recovery_to_2_percent_s':recovery}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    with (args.input/'python_full.csv').open(encoding='utf-8',newline='') as handle:
        py=Wave([{'time_s':float(r['time_s']),**{k:float(r[k]) for k in VALUES}} for r in csv.DictReader(handle)])
    lines=[line for line in (args.input/'ngspice_full.dat').read_text(encoding='utf-8').splitlines() if line.strip()]
    rows=[]
    for line in lines[1:]:
        t,vsw,v,i=map(float,line.split())
        rows.append({'time_s':t,'output_v':v,'inductor_current_a':i})
    ng=Wave(rows)
    # Both models use exactly the same fully covered window. No first-point extrapolation.
    end=min(.1,py.times[-1],ng.times[-1])
    windows={'pre':(.04962,.05),'post':(.0996,end)}
    stats={name:{label:wave.metrics(*bounds) for label,bounds in windows.items()} for name,wave in [('python',py),('ngspice',ng)]}
    comparison=[]
    for label in windows:
        for metric in ('output_v_mean','inductor_current_a_mean','output_v_pp','inductor_current_a_pp'):
            a,b=stats['python'][label][metric],stats['ngspice'][label][metric]
            comparison.append({'window':label,'metric':metric,'python':a,'ngspice':b,'ngspice_minus_python':b-a})
    csv_save(args.output/'comparison.csv',comparison)
    comparison_windows=[(.04962,.06),(.0996,end)]
    max_v=max_i=0.0
    compared=0
    for row in ng.rows:
        if any(a<=row['time_s']<=b for a,b in comparison_windows):
            ref=py.at(row['time_s'])
            max_v=max(max_v,abs(row['output_v']-ref['output_v']))
            max_i=max(max_i,abs(row['inductor_current_a']-ref['inductor_current_a']))
            compared+=1
    # Compact CSVs contain actual saved points only; no decimation, no extrapolated rows.
    for name,wave in [('python',py),('ngspice',ng)]:
        for label,a,b in [('step',.0498,.0506),('post',.0996,end)]:
            csv_save(args.output/(name+'_'+label+'_saved_points.csv'),[r for r in wave.rows if a<=r['time_s']<=b])
    i_pp=7*(2/9)/(220e-6*50000)
    v_pp=i_pp/(8*50000*470e-6)
    checks={}
    for label,current in [('pre',.5),('post',1.)]:
        m=stats['ngspice'][label]
        checks[label+'_dc_voltage_within_1e_5_v']=abs(m['output_v_mean']-2)<1e-5
        checks[label+'_dc_current_within_1e_5_a']=abs(m['inductor_current_a_mean']-current)<1e-5
        checks[label+'_voltage_ripple_within_2_percent']=abs(m['output_v_pp']/v_pp-1)<.02
        checks[label+'_current_ripple_within_2_percent']=abs(m['inductor_current_a_pp']/i_pp-1)<.02
    checks['finite_data']=all(math.isfinite(v) for wave in [py,ng] for row in wave.rows for v in row.values())
    summary={'case':'Fixed-duty open-loop Buck load step, not new closed-loop control','source_directory':str(args.input.resolve()),'model':'9 V, D=2/9, 50 kHz, L=220 uH, C=470 uF, i/v start at zero, 4 to 2 ohm at 50 ms','analysis_fix':'Previous analysis requested unavailable tstart. Shared pre window 49.62-50 ms has 19 whole PWM periods; post ends at common saved endpoint. No extrapolation, no simulator rerun, no threshold relaxation.','statistics':stats,'response':{'python':py.response(),'ngspice':ng.response()},'recovery_definition':'First saved point after last sample outside 2 V +/-2%, stays inside through record end and has >=2 ms observation margin. Recovery time reported without a closed-loop pass threshold.','comparison_windows_s':comparison_windows,'compared_ngspice_points':compared,'maximum_absolute_output_difference_v':max_v,'maximum_absolute_current_difference_a':max_i,'mean_method':'Time-weighted trapezoid integration with linearly interpolated endpoints inside saved coverage; extrema from saved points and those endpoints.','pwm_difference':'Existing SPICE uses area-compensated 1 ns ramps; Python PWM edges instantaneous.','saved_ranges':{name:{'start_s':wave.times[0],'end_s':wave.times[-1],'unique_state_points':len(wave.rows)} for name,wave in [('python',py),('ngspice',ng)]},'checks':checks,'full_outputs':'python_full.csv and ngspice_full.dat remain unchanged in source_directory; compact CSVs include only declared step/post windows.'}
    save(args.output/'summary.json',json.dumps(summary,indent=2)+'\n')
    for name in ('buck_load_step.cir','buck_load_step_ngspice.cir','buck_load_step_ltspice.cir','ngspice_command.json','ngspice_run.json','ngspice_stdout.txt','ngspice_stderr.txt','parameters.json'):
        with (args.output/name).open('xb') as handle:
            handle.write((args.input/name).read_bytes())
    print(json.dumps(summary,indent=2),flush=True)
    if not all(checks.values()):
        raise AssertionError('Existing DC/ripple checks failed; all new analysis outputs retained')


if __name__=='__main__':
    main()
