"""Create self-authored PLECS input models; never query/export demo results."""
from pathlib import Path
import argparse
import json


def q(value):
    return json.dumps(str(value), ensure_ascii=True)


def build(phase, name):
    blocks = []
    signals = {}
    def component(kind, name, x, y, params=None, direction='right', extra=''):
        body = '\n'.join(f'      Parameter {{ Variable {q(k)} Value {q(v)} Show off }}' for k,v in (params or {}).items())
        blocks.append(f'''    Component {{
      Type {kind}
      Name {q(name)}
      Show on
      Position [{x}, {y}]
      Direction {direction}
      Flipped off
      LabelPosition south
{body}
{extra}
    }}''')
    def wire(terminals):
        source, *destinations = terminals
        text = f'    Connection {{ Type Wire SrcComponent {q(source[0])} SrcTerminal {source[1]}\n'
        for dest in destinations:
            text += f'      Branch {{ DstComponent {q(dest[0])} DstTerminal {dest[1]} }}\n'
        blocks.append(text+'    }')
    def signal(src, dst):
        signals.setdefault(src, []).append(dst)

    for side, voltage, left in ((1, 24, 160), (2, 12, 820)):
        component('DCVoltageSource', f'Vdc{side}', left-100, 210, {'V':voltage}, 'up')
        for leg, x in (('a',left),('b',left+140)):
            for switch,y in (('H',140),('L',280)):
                component('MosfetWithDiode',f'Q{side}{leg}{switch}',x,y,
                          {'Ron':0,'s_init':0,'thermal':'','Rth':0,'Np':1,'T_init':25}, 'up')
        wire([(f'Vdc{side}',1),(f'Q{side}aH',1),(f'Q{side}bH',1)])
        wire([(f'Vdc{side}',2),(f'Q{side}aL',2),(f'Q{side}bL',2)])
        delay = 0 if side==1 else phase/360/20000
        for suffix,hi,lo,y in (('plus',1,0,390),('minus',0,1,445)):
            pulse=f'Gate{side}_{suffix}'
            component('PulseGenerator',pulse,left-60,y,{'Hi':hi,'Lo':lo,'f':20000,'DutyCycle':0.5,'Delay':format(delay,'.17g'),'DataType':10})
            targets=[f'Q{side}aH',f'Q{side}bL'] if suffix=='plus' else [f'Q{side}aL',f'Q{side}bH']
            for target in targets:signal((pulse,1),(target,3))
    component('Inductor','L_100uH',380,180,{'L':'100e-6','i_init':0})
    component('Resistor','R_0p5ohm',465,180,{'R':0.5})
    component('Ammeter','iL',545,180)
    component('Transformer','n_2_to_1',650,230,{'Windings':'[1 1]','n':'[2 1]','Polarity':'+','Lm':'inf','im0':0})
    component('Voltmeter','v1',230,210,{},'up')
    component('Voltmeter','v2',890,210,{},'up')
    wire([('Q1aH',2),('Q1aL',1),('L_100uH',1),('v1',1)])
    wire([('L_100uH',2),('R_0p5ohm',1)])
    wire([('R_0p5ohm',2),('iL',1)])
    wire([('iL',2),('n_2_to_1',1)])
    wire([('Q1bH',2),('Q1bL',1),('n_2_to_1',2),('v1',2)])
    wire([('Q2aH',2),('Q2aL',1),('n_2_to_1',3),('v2',1)])
    wire([('Q2bH',2),('Q2bL',1),('n_2_to_1',4),('v2',2)])
    component('Gain','n_times_v2',610,410,{'K':2})
    signal(('v2',3),('n_times_v2',1))
    scope_extra='''      Location [100, 100; 1000, 700]
      Axes "3"
      TimeRange "0"
      ScrollingMode "1"
      SingleTimeAxis "1"
      Open "0"
      Ts "-1"
      SampleLimit "0"
      XAxisLabel "Time / s"
      ShowLegend "1"
'''
    for label in ('v1 / V','n*v2 / V','iL / A'):
        scope_extra += f'      Axis {{ Name {q(label)} AutoScale 1 MinValue -1 MaxValue 1 Signals {{}} SignalTypes [] AxisLabel {q(label)} }}\n'
    component('Scope','Bridge voltages and current',1100,210,extra=scope_extra)
    signal(('v1',3),('Bridge voltages and current',1))
    signal(('n_times_v2',2),('Bridge voltages and current',2))
    signal(('iL',3),('Bridge voltages and current',3))
    for suffix,x,voltage in (('P1',280,('v1',3)),('P2',580,('n_times_v2',2))):
        component('SignalMux',f'Mux_{suffix}',x,550,{'Width':2})
        signal(voltage,(f'Mux_{suffix}',2))
        signal(('iL',3),(f'Mux_{suffix}',3))
        component('Product',f'Instant_{suffix}',x+60,550,{'Inputs':'*','IconShape':1,'DataType':10})
        signal((f'Mux_{suffix}',1),(f'Instant_{suffix}',2))
        component('PeriodicAverage',f'Average_{suffix}',x+130,550,{'T_average':'1/20000'})
        signal((f'Instant_{suffix}',1),(f'Average_{suffix}',2))
        component('Display',f'{suffix}_W',x+220,550,{'Notation':1,'Precision':7},extra='      Frame [-50, -14; 50, 14]')
        signal((f'Average_{suffix}',1),(f'{suffix}_W',1))
    component('Math','i_squared',200,650,{'Operator':1})
    signal(('iL',3),('i_squared',2))
    component('PeriodicAverage','Average_i_squared',320,650,{'T_average':'1/20000'})
    signal(('i_squared',1),('Average_i_squared',2))
    component('Math','RMS',440,650,{'Operator':2})
    signal(('Average_i_squared',1),('RMS',2))
    component('Display','Irms_A',560,650,{'Notation':1,'Precision':7},extra='      Frame [-50, -14; 50, 14]')
    signal(('RMS',1),('Irms_A',1))
    component('Gain','R_times_mean_i2',440,730,{'K':0.5})
    signal(('Average_i_squared',1),('R_times_mean_i2',1))
    component('Display','R_loss_W',560,730,{'Notation':1,'Precision':7},extra='      Frame [-50, -14; 50, 14]')
    signal(('R_times_mean_i2',2),('R_loss_W',1))
    for src,destinations in signals.items():
        text=f'    Connection {{ Type Signal SrcComponent {q(src[0])} SrcTerminal {src[1]}\n'
        for dest in destinations:
            text+=f'      Branch {{ DstComponent {q(dest[0])} DstTerminal {dest[1]} }}\n'
        blocks.append(text+'    }')
    return f'''Plecs {{
  Name {q(name)}
  Version "5.0"
  CircuitModel "ContStateSpace"
  StartTime "0"
  TimeSpan "0.006"
  Solver "dopri"
  MaxStep "5e-7"
  InitStep "-1"
  FixedStep "5e-7"
  Refine "1"
  ZCStepSize "1e-10"
  RelTol "1e-8"
  AbsTol "1e-9"
  InitialState "1"
  InitializationCommands ""
  Schematic {{
    Location [0, 50; 1250, 870]
    ZoomFactor 1
    SliderPosition [0, 0]
    ShowBrowser off
{chr(10).join(blocks)}
  }}
}}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path,help='New directory; an existing path is refused')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    for phase,label in ((30,'forward'),(-30,'reverse')):
        name=f'dab_sps_{label}'
        path=args.output/(name+'.plecs')
        path.write_text(build(phase,name),encoding='utf-8')
        print(path)

if __name__=='__main__':main()
