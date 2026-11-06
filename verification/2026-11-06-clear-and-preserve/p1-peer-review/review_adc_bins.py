import sys
from pathlib import Path
from fractions import Fraction
repo=Path(__file__).resolve().parents[3]
root=repo/'experiments/p1-c2000-buck'
retained=repo/'.runs/p1-clear-measurement-20261106-003154'
print('Scope: native Linux host C/Python; target ISR and hardware NOT executed')
for name in ('host_c/buck_control.c','host_c/buck_control.h','firmware/adc_scaling.h','host_c/test_clear_measurements.c'):
 assert (root/name).read_bytes()==(retained/name).read_bytes(), name
 print('Retained build source equals current:',name)
sys.path[:0]=[str(root/'simulation'), str(root/'host_c')]
from io_timing_buck import adc_clear_evidence
from protection import ProtectedController
from c_controller import CController, load_library
lib=load_library(retained/'results_clear_01/build/libbuck_control.so')
step=Fraction(33,10)/4096
accepted={'voltage':[],'current':[]}
count=0
for axis in ('voltage','current'):
 for q in range(4096):
  qv,qi=(q,2048) if axis=='voltage' else (1,q)
  v=qv*float(step)*2
  i=(qi*float(step)-1.65)/0.1
  ev=adc_clear_evidence(qv,qi)
  vlo,vhi=qv*step*2,(qv+1)*step*2
  ilo,ihi=(qi*step-Fraction(165,100))/Fraction(1,10),((qi+1)*step-Fraction(165,100))/Fraction(1,10)
  should=(0<qv<4095 and 0<qi<4095 and max(abs(vlo),abs(vhi))<=Fraction(1,10) and max(abs(ilo),abs(ihi))<=Fraction(1,10))
  native=CController(lib); python=ProtectedController()
  for controller in (native,python):controller.update(0,9,0,2.5)
  a=native.update(1,9,v,i,True,ev);b=python.update(1,9,v,i,True,ev)
  assert a==b,(axis,q,a,b)
  assert (a['clear_result']=='accepted')==should,(axis,q,a,should)
  if should:accepted[axis].append(q)
  else:assert a['state']=='FAULT_LATCHED' and a['duty']==0
  count+=1
print('PASS exhaustive independent rational-bound expectations:',count,'C/Python clear decisions')
for axis,qs in accepted.items():print(axis,'accepted codes',min(qs),max(qs),'count',len(qs))
for ev in (None,{'observable':False,'max_abs_output_v':0.1,'max_abs_current_a':0.1},
 {'observable':True,'max_abs_output_v':float('nan'),'max_abs_current_a':0.1},
 {'observable':True,'max_abs_output_v':float('inf'),'max_abs_current_a':0.1},
 {'observable':True,'max_abs_output_v':-1,'max_abs_current_a':0.1},
 {'observable':True,'max_abs_output_v':0,'max_abs_current_a':0.1}):
 native=CController(lib);native.update(0,9,0,2.5)
 r=native.update(1,9,0.01,0,True,ev)
 assert r['clear_result']=='rejected_unobservable_measurement',r
print('PASS native adapter NULL/nonfinite/negative/understated evidence refuses clear')
