"""Regenerate the README's source-data chart (requires the plots extra)."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from collections import Counter
import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter
from sim2blender.amodel import PROJECT_ROOT,read_model
model=read_model(PROJECT_ROOT/'examples/models/winch_cage.amodel')
components={c['component_id']:c for c in model.cells}
counts=Counter(c['component_tag'] for c in components.values())
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'svg.fonttype':'none'})
fig,(left,right)=plt.subplots(1,2,figsize=(11,3.8),gridspec_kw={'width_ratios':[1,1.5]})
colors=['#486779','#d49b4f','#239c86']
left.barh(['Beams','Ropes','Net groups'],[counts['beam'],counts['truss'],counts['membrane']],color=colors)
left.set_title('Active components',loc='left',fontweight='bold',pad=18)
for i,v in enumerate([counts['beam'],counts['truss'],counts['membrane']]):left.text(v+.5,i,str(v),va='center')
left.set_xlim(0,30);left.set_xlabel('Component count');left.invert_yaxis()
values=[components[i]['geometry']['diameter']*1000 for i in (1,49,32,52,12)]
labels=['Floater tube','Grid rope','Net support rope','Winch rope','Net twine']
right.barh(labels,values,color=[colors[0],colors[1],colors[1],colors[1],colors[2]])
right.set_xscale('log');right.set_xlim(1,1200);right.set_xticks([1,10,100,1000]);right.xaxis.set_major_formatter(ScalarFormatter())
right.set_title('Source diameters',loc='left',fontweight='bold',pad=18);right.set_xlabel('Millimetres · logarithmic scale');right.invert_yaxis()
for i,v in enumerate(values):right.text(v*1.08,i,f'{v:g} mm',va='center',fontsize=10)
for ax in (left,right):
 ax.spines[['top','right','left']].set_visible(False);ax.tick_params(axis='y',length=0)
 ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
fig.tight_layout(w_pad=3)
out=PROJECT_ROOT/'docs/assets/source-geometry.svg';fig.savefig(out,bbox_inches='tight');plt.close(fig)
print(f'Saved {out}')
