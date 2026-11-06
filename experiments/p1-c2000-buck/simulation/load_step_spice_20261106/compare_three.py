"""Read completed LTspice/ngspice/Python runs; no simulation or settings access."""
import argparse
import csv
import json
import math
from pathlib import Path
from analyze_existing import Wave, VALUES, save, csv_save


def csv_wave(path):
    with path.open(encoding='utf-8',newline='') as handle:
        return Wave([{'time_s':float(r['time_s']),**{k:float(r[k]) for k in VALUES}} for r in csv.DictReader(handle)])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lt',required=True,type=Path)
    parser.add_argument('--ng',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    py=csv_wave(args.ng/'python_full.csv')
    lines=[x for x in (args.ng/'ngspice_full.dat').read_text(encoding='utf-8').splitlines() if x.strip()]
    ngrows=[]
    for line in lines[1:]:
        t,vsw,v,i=map(float,line.split())
        ngrows.append({'time_s':t,'output_v':v,'inductor_current_a':i})
    ng=Wave(ngrows)
    lt_step=csv_wave(args.lt/'step/step.csv')
    lt_post=csv_wave(args.lt/'post/post.csv')
    end_step=min(.06,lt_step.times[-1],ng.times[-1],py.times[-1])
    end_post=min(.1,lt_post.times[-1],ng.times[-1],py.times[-1])
    windows={'pre':(.04962,.05),'post':(.0996,end_post)}
    models={'python':{'pre':py,'post':py},'ngspice':{'pre':ng,'post':ng},'ltspice':{'pre':lt_step,'post':lt_post}}
    stats={name:{label:parts[label].metrics(*bounds) for label,bounds in windows.items()} for name,parts in models.items()}
    comparison=[]
    for label in windows:
        for metric in ('output_v_mean','inductor_current_a_mean','output_v_pp','inductor_current_a_pp'):
            row={'window':label,'metric':metric,**{name:stats[name][label][metric] for name in models}}
            row.update({f'ltspice_minus_{name}':row['ltspice']-row[name] for name in ('python','ngspice')})
            comparison.append(row)
    csv_save(args.output/'comparison.csv',comparison)
    responses={name:Wave(wave.crop(.05,end_step)).response() for name,wave in [('python',py),('ngspice',ng),('ltspice',lt_step)]}
    differences={}
    for name,reference in [('python',py),('ngspice',ng)]:
        differences[name]={}
        for label,target,a,b in [('step',lt_step,.04962,end_step),('post',lt_post,.0996,end_post)]:
            max_v=max_i=0.;count=0
            for row in target.rows:
                if a<=row['time_s']<=b:
                    other=reference.at(row['time_s'])
                    max_v=max(max_v,abs(row['output_v']-other['output_v']))
                    max_i=max(max_i,abs(row['inductor_current_a']-other['inductor_current_a']))
                    count+=1
            differences[name][label]={'start_s':a,'end_s':b,'ltspice_points_compared':count,'max_abs_output_difference_v':max_v,'max_abs_current_difference_a':max_i}
    for name,parts in models.items():
        for label,wave,a,b in [('step',parts['pre'],.0498,.0506),('last_period',parts['post'],.09998,end_post)]:
            csv_save(args.output/(name+'_'+label+'_saved_points.csv'),[r for r in wave.rows if a<=r['time_s']<=b])
    i_pp=7*(2/9)/(220e-6*50000);v_pp=i_pp/(8*50000*470e-6)
    checks={}
    for label,current in [('pre',.5),('post',1.)]:
        m=stats['ltspice'][label]
        checks[label+'_dc_voltage_within_1e_5_v']=abs(m['output_v_mean']-2)<1e-5
        checks[label+'_dc_current_within_1e_5_a']=abs(m['inductor_current_a_mean']-current)<1e-5
        checks[label+'_voltage_ripple_within_2_percent']=abs(m['output_v_pp']/v_pp-1)<.02
        checks[label+'_current_ripple_within_2_percent']=abs(m['inductor_current_a_pp']/i_pp-1)<.02
    checks['finite_data']=all(math.isfinite(v) for wave in (py,ng,lt_step,lt_post) for row in wave.rows for v in row.values())
    summary={'case':'Open-loop fixed-duty ideal Buck load step, NOT a new closed-loop validation','input_directories':{'ltspice':str(args.lt.resolve()),'ngspice_and_python':str(args.ng.resolve())},'statistics':stats,'response_observed_50_to_60ms':responses,'response_observation_end_s':end_step,'response_definition':'First saved point after the last point outside 2 V +/-2%, remaining inside through 60 ms with at least 2 ms margin. This comparison does not claim LTspice remains inside throughout 60-100 ms.','ltspice_runs':'step and post were independent zero-state integrations to 60 ms and 100 ms. The latter provides a separate terminal steady window.','pointwise_differences':differences,'checks':checks,'numerical_settings':'LTspice max step 50 ns, reltol 1e-7, abstol 1e-10, vntol 1e-9. Python and ngspice max step 250 ns. Existing DC 1e-5 and ripple 2% limits retained; transient differences are reported, not a new pass gate.','waveform_scope':'Compact CSVs contain actual saved state points in 49.8-50.6 ms and 99.98-100 ms only. Complete source CSV/raw remain local. CSV Offset has already been restored by the execution parser.','integration':'Shared pre window 49.62-50 ms (19 PWM periods); shared post 99.6-common100ms endpoint. Time-weighted trapezoid integration with endpoint interpolation only inside coverage; no extrapolation.','pwm_edges':'SPICE uses 1 ns area-compensated ramps; Python uses instantaneous edges.','source_saved_points':{'python':len(py.rows),'ngspice':len(ng.rows),'ltspice_step':len(lt_step.rows),'ltspice_post':len(lt_post.rows)}}
    save(args.output/'summary.json',json.dumps(summary,indent=2)+'\n')
    for case in ('step','post'):
        for filename in (case+'.cir',case+'.log','run.json'):
            source=args.lt/case/filename
            if source.exists():
                with (args.output/(case+'_'+filename)).open('xb') as handle:handle.write(source.read_bytes())
    for filename in ('execution_stdout.txt','execution_stderr.txt','run_ltspice_load_step.py'):
        source=args.lt/filename
        if source.exists():
            with (args.output/filename).open('xb') as handle:handle.write(source.read_bytes())
    print(json.dumps(summary,indent=2),flush=True)
    if not all(checks.values()):
        raise AssertionError('Original DC/ripple checks failed; evidence retained, no limits relaxed')


if __name__=='__main__':
    main()
