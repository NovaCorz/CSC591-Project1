#!/usr/bin/env python3
"""Redraw curated Hazel evidence from verified summaries; run in Slurm."""
import collections,json,os,sys
from pathlib import Path
assert os.environ.get('SLURM_JOB_ID'),'Use a Slurm compute job'
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(sys.argv[1]).resolve()
(OUT/'figures').mkdir(parents=True,exist_ok=True)
HOSTS=['haswell','cascadelake','icelake_8358','genoa','turin']
SHORT=['Haswell','Cascade Lake','Ice Lake 8358','Genoa','Turin']
rs=json.loads((ROOT/'hazel/analysis/evidence-records.json').read_text())
base={h:[r for r in rs if r['host']==h and r['stage']=='baseline'] for h in HOSTS}
follow={h:[r for r in rs if r['host']==h and r['stage']=='followup'] for h in HOSTS}
import csv
obs={r['machine']:r for r in csv.DictReader((ROOT/'prediction/post_hazel/outputs/hazel-observations.csv').open())}
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams.update({'font.size':13,'axes.linewidth':1.2,'pdf.fonttype':42,'axes.grid':False})
used=collections.defaultdict(list)
def plotline(ax,rs,key,scale=1,label=None):
 rs=sorted(rs,key=lambda r:r['parameters'][key]);x=[r['parameters'][key]/scale for r in rs]
 ax.plot(x,[r['statistics']['median'] for r in rs],'-o',ms=3,label=label)
 for r,v in zip(rs,x):
  if r['qualification']=='noisy':ax.plot(v,r['statistics']['median'],'x',color='black',ms=7)
 ax.fill_between(x,[r['statistics']['q1'] for r in rs],[r['statistics']['q3'] for r in rs],alpha=.12)
def boxes(ax,rs,labels):
 bs=[dict(med=r['statistics']['median'],q1=r['statistics']['q1'],q3=r['statistics']['q3'],whislo=r['statistics']['p05'],whishi=r['statistics']['p95'],fliers=[],label=l+('*' if r['qualification']=='noisy' else '')) for r,l in zip(rs,labels)]
 if bs:ax.bxp(bs,showfliers=False,medianprops={'color':'black'});ax.tick_params(axis='x',labelsize=9)
def save(fig,name):
 fig.tight_layout()
 for ext in ['pdf','png']:fig.savefig(OUT/f'figures/{name}.{ext}',bbox_inches='tight',dpi=140)
 plt.close(fig)
for kind in ['capacity','spatial','conflict','inclusion']:
 fig,axes=plt.subplots(5,2,figsize=(14,17))
 for h,name,(ax,bx) in zip(HOSTS,SHORT,axes):
  for a in [ax,bx]:a.set_prop_cycle(color=['black','0.35','0.6','0.15','0.75','0.45']);a.set_ylabel('TSC ticks/access');a.set_title(name)
  if kind=='capacity':
   rs=[r for r in follow[h] if r['family']=='capacity_control'];groups=collections.defaultdict(list)
   for r in rs:groups[r['parameters']['page'],r['parameters']['stride']].append(r)
   for (page,stride),g in sorted(groups.items()):plotline(ax,g,'bytes',1024,f'{page}, {stride} B')
   ax.set(xlabel='Working set (KiB)',xscale='log',yscale='log');ax.legend(fontsize=9)
   # Fixed representative footprints span the curve; no selection based on smoothness.
   g=sorted([r for r in rs if r['parameters']['stride']==64 and r['parameters']['page']=='huge'],key=lambda r:r['parameters']['bytes'])
   if not g:g=sorted(rs,key=lambda r:r['parameters']['bytes'])
   sel=[g[i] for i in sorted({round(j*(len(g)-1)/6) for j in range(7)})] if g else []
   boxes(bx,sel,[f"{r['parameters']['bytes']/1024:g}" for r in sel]);bx.set(xlabel='Representative footprint (KiB)',yscale='log')
  elif kind=='spatial':
   rs=[r for r in follow[h] if r['family']=='spatial_alignment'];w=min(r['parameters']['bytes'] for r in rs);rs=[r for r in rs if r['parameters']['bytes']==w];groups=collections.defaultdict(list)
   for r in rs:groups[r['parameters']['align']].append(r)
   for align,g in sorted(groups.items()):plotline(ax,g,'offset',label=f'shift {align} B')
   ax.set_xlabel('Pair offset (B)');ax.legend(fontsize=9)
   g=sorted(groups[min(groups)],key=lambda r:r['parameters']['offset']);sel=[r for r in g if 40<=r['parameters']['offset']<=88]
   boxes(bx,sel,[str(r['parameters']['offset']) for r in sel]);bx.set_xlabel('Offsets near boundary (B)')
  elif kind=='conflict':
   rs=[r for r in base[h] if r['family']=='associativity' and r['parameters']['stride'] in [4096,16384,65536,262144]];groups=collections.defaultdict(list)
   for r in rs:groups[r['parameters']['stride'],r['parameters']['seed']].append(r)
   for (stride,seed),g in sorted(groups.items()):
    g=sorted(g,key=lambda r:r['parameters']['bytes']);ax.plot([r['parameters']['bytes']/stride for r in g],[r['statistics']['median'] for r in g],'-o',ms=2,label=f'{stride//1024}K/{str(seed)[-3:]}')
   ax.set(xlabel='Congruence-candidate addresses',yscale='log');ax.legend(fontsize=7,ncol=2)
   g=groups[min(groups)];ways=int(obs[h]['l1_associativity_conditional_ways']);sel=sorted([r for r in g if ways-2<=r['parameters']['bytes']/r['parameters']['stride']<=ways+2],key=lambda r:r['parameters']['bytes'])
   boxes(bx,sel,[str(r['parameters']['bytes']//r['parameters']['stride']) for r in sel]);bx.set_xlabel('Addresses near L1 candidate')
  else:
   rs=[r for r in follow[h] if r['family']=='cross_core_reload_final']
   if not rs:rs=[r for r in follow[h] if r['family']=='cross_core_reload']
   for pressure,marker in [(False,'o'),(True,'s')]:
    g=[r for r in rs if bool(r['parameters']['offset'])==pressure];ax.scatter([r['parameters']['bytes']/1048576 for r in g],[r['statistics']['median'] for r in g],marker=marker,facecolors='none',edgecolors='black',label='pressure' if pressure else 'control')
   ax.set(xlabel='Pressure footprint (MiB)',xscale='log');ax.legend(fontsize=10)
   largest=max(r['parameters']['bytes'] for r in rs);g=[r for r in rs if r['parameters']['bytes']==largest];seed=min(r['parameters']['seed'] for r in g);sel=sorted([r for r in g if r['parameters']['seed']==seed],key=lambda r:r['parameters']['offset']);boxes(bx,sel,['pressure' if r['parameters']['offset'] else 'control' for r in sel]);bx.set_xlabel(f'Largest footprint; seed {seed}')
   for a in [ax,bx]:a.set_ylabel('TSC ticks/target reload')
  used[kind].extend(r['record_path'] for r in rs)
  used[kind+'-boxes'].extend(r['record_path'] for r in sel)
 save(fig,'hazel-'+kind)

(OUT/'plot-record-selection.json').write_text(json.dumps(dict(used),indent=2)+'\n')
