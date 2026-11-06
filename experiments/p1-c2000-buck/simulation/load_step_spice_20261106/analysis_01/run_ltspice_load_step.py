from pathlib import Path
import subprocess,time,json,runpy
ROOT=Path(__file__).resolve().parent
PARSE=runpy.run_path(r'E:\UserData\Documents\ChatGPT\硬件\.runs\ltspice_batch_fix_20261106_182049_668333\run_buck_batch_v4.py')
EXE=PARSE['EXE']; put=PARSE['put']; read_raw=PARSE['read_raw']; write_csv=PARSE['write_csv']
base=Path(r'E:\codex_ltspice_runs\load_step_20261106_181654_8690784\buck_load_step_ltspice.cir').read_text(encoding='utf-8')
circuit='\n'.join(line for line in base.splitlines() if not line.lower().startswith(('.tran','.meas','.end')))
circuit+='\n.options plotwinsize=0 numdgt=15 reltol=1e-7 abstol=1e-10 vntol=1e-9\n.save V(sw) V(out) I(L1)\n'
startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=subprocess.SW_HIDE
for name,analysis in [('step','.tran 0.05u 60m 49.6m 0.05u uic'),('post','.tran 0.05u 100m 99.6m 0.05u uic')]:
 case=ROOT/name;case.mkdir(exist_ok=False);deck=case/(name+'.cir');put(deck,circuit+analysis+'\n.end\n')
 command=[str(EXE),'-b','-ascii',str(deck)];put(case/'command.json',json.dumps(command,indent=2)+'\n')
 t=time.monotonic()
 with (case/'stdout.txt').open('xb') as stdout,(case/'stderr.txt').open('xb') as stderr:
  p=subprocess.Popen(command,cwd=case,stdout=stdout,stderr=stderr,startupinfo=startup)
  try: code=p.wait(timeout=60);timed_out=False
  except subprocess.TimeoutExpired: p.terminate();code=p.wait(timeout=10);timed_out=True
 result={'command':command,'pid':p.pid,'exit_code':code,'timed_out':timed_out,'elapsed_s':time.monotonic()-t}
 put(case/'run.json',json.dumps(result,indent=2)+'\n');print(json.dumps({'case':name,**result}),flush=True)
 if code or timed_out or not deck.with_suffix('.raw').exists(): raise RuntimeError('Preserved failed LTspice run')
 rows=read_raw(deck.with_suffix('.raw'));write_csv(case/(name+'.csv'),rows)
 print(json.dumps({'case':name,'points':len(rows),'first':rows[0],'last':rows[-1]}),flush=True)
