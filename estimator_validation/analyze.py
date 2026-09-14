"""Analyze matched validation archives through Slurm, without changing Phase-I results."""
import array,csv,hashlib,io,json,math,os,sys,tarfile
from pathlib import Path
assert os.environ.get('SLURM_JOB_ID'),'Run analysis through Slurm'
ROOT=Path(__file__).resolve().parents[1];P=ROOT/'estimator_validation'
sys.path.insert(0,str(ROOT/'scripts'));from common import stats
OUT=P/('analysis-'+os.environ['SLURM_JOB_ID']);OUT.mkdir(exist_ok=False)
def compare(sw,q):
 if q['errno'] or q['nr']!=2 or q['read_bytes']!=40:return None,'unavailable or malformed counter group'
 if not q['running_ns'] or q['running_ns']!=q['enabled_ns']:return None,'counter group not fully scheduled'
 if q['accesses']<=0 or q['misses']>q['accesses']:return None,'invalid access/miss population ratio'
 hw=100*(1-q['misses']/q['accesses']);err=abs(sw-hw)
 return dict(pmu_hit_percent=hw,absolute_error_pp=err,relative_error_percent=100*err/hw if hw else None),''
# Meaningful arithmetic and unavailable/invalid-reference checks.
q=dict(errno=0,nr=2,read_bytes=40,enabled_ns=100,running_ns=100,accesses=100,misses=15)
d,_=compare(90,q);assert d['absolute_error_pp']==5 and math.isclose(d['relative_error_percent'],100*5/85)
assert compare(90,dict(q,misses=101))[0] is None
assert compare(90,dict(q,running_ns=0))[0] is None
assert compare(90,dict(q,errno=2))[0] is None
assert compare(90,dict(q,misses=100))[0]['relative_error_percent'] is None
allrows=[];calibrations=[];records=[];sources=[];total=0
for archive in sorted((P/'hosts').glob('*/raw-and-provenance.tar.gz')):
 host=archive.parent.name
 sources.append(dict(host=host,path=str(archive),sha256=hashlib.sha256(archive.read_bytes()).hexdigest()))
 with tarfile.open(archive) as tar:
  def j(name):return json.load(tar.extractfile(name))
  summary=j('results/full-complete.json')
  full={r['name']:r for r in summary['records']}
  values={}
  for name,r in full.items():
   assert r['returncode']==0
   raw=tar.extractfile('results/full/'+name+'/raw.u64').read()
   assert hashlib.sha256(raw).hexdigest()==r['raw_sha256']
   a=array.array('Q');a.frombytes(raw)
   if r['measurement']['little_endian']!=(sys.byteorder=='little'):a.byteswap()
   assert len(a)==1000000
   st=stats(a)
   for key in st:
    if isinstance(st[key],float):assert math.isclose(st[key],r['statistics'][key],rel_tol=1e-12,abs_tol=1e-12)
    else:assert st[key]==r['statistics'][key]
   values[name]=a;total+=len(a);records.append(r)
  hot,cold=full['None-hot'],full['None-cold']
  low,high=hot['statistics']['p95'],cold['statistics']['p05']
  threshold=(low+high)/2 if low<high else None
  calibrations.append(dict(host=host,hot_p95=low,cold_p05=high,threshold=threshold,hot_cpu=hot['cpu'],cold_cpu=cold['cpu']))
  for level in ['L1D','LL']:
   for workload in ['hot','target','cold']:
    name=level+'-'+workload
    row=dict(host=host,level=level,workload=workload,bytes={'hot':1024,'target':1048576,'cold':268435456}[workload],threshold=threshold,status='')
    if name not in full:
     row['status']='PMU event pair unavailable in smoke';allrows.append(row);continue
    r=full[name];q=r['pmu'];row.update(cpu=r['cpu'],accesses=q['accesses'],misses=q['misses'],enabled_ns=q['enabled_ns'],running_ns=q['running_ns'],raw_sha256=r['raw_sha256'],issues='; '.join(r['issues']))
    row['same_calibration_cpu']=hot['cpu']==cold['cpu']==r['cpu']
    row['accesses_per_timed_load']=q['accesses']/1000000
    if threshold is None:row['status']='timing hot/cold distributions overlap';allrows.append(row);continue
    a=values[name];row['software_hit_percent']=100*sum(v<=threshold for v in a)/len(a)
    row['sensitivity_low_percent']=100*sum(v<=low for v in a)/len(a)
    row['sensitivity_high_percent']=100*sum(v<=high for v in a)/len(a)
    blocks=[100*sum(v<=threshold for v in a[i:i+10000])/10000 for i in range(0,len(a),10000)]
    row['block_low_percent']=min(blocks);row['block_high_percent']=max(blocks)
    base=values['None-'+workload]
    row['timing_only_percent']=100*sum(v<=threshold for v in base)/len(base)
    row['observer_difference_pp']=row['software_hit_percent']-row['timing_only_percent']
    d,why=compare(row['software_hit_percent'],q)
    if d:row.update(d);row['status']='region-counter comparison; not pointer-load ground truth'
    else:row['status']=why
    if not row['same_calibration_cpu']:row['status']+='; calibration/core change'
    allrows.append(row)
fields=list(dict.fromkeys(k for r in allrows for k in r))
with (OUT/'comparison.csv').open('w') as f:
 w=csv.DictWriter(f,fields);w.writeheader();w.writerows(allrows)
(OUT/'comparison.json').write_text(json.dumps(allrows,indent=2)+'\n')
(OUT/'calibration.json').write_text(json.dumps(calibrations,indent=2)+'\n')
(OUT/'records.json').write_text(json.dumps(records,indent=2)+'\n')
(OUT/'verification.json').write_text(json.dumps(dict(job_id=os.environ['SLURM_JOB_ID'],hosts=len(sources),full_records=len(records),raw_samples_verified=total,raw_hashes_and_statistics_verified=True,arithmetic_checks=5,inputs=sources,limitations='Whole timed-region generic counters include timer/loop/stack traffic. LL ratio is conditional on accesses reaching LL. No event-ratio clipping, threshold fitting to PMUs, or modification of frozen results.'),indent=2)+'\n')
def fmt(x):return '--' if x is None else f'{x:.3f}'
lines=[]
for r in allrows:
 if r['workload']!='target':continue
 status='unavailable' if 'software_hit_percent' not in r else 'core change' if not r['same_calibration_cpu'] else 'qualified comparison'
 if 'software_hit_percent' in r and 'pmu_hit_percent' not in r:status='invalid reference'
 lines.append(' & '.join([r['host'],r['level']]+[fmt(r.get(k)) for k in ['software_hit_percent','pmu_hit_percent','absolute_error_pp','relative_error_percent']]+[status])+r' \\')
(OUT/'table.tex').write_text('\n'.join(lines)+'\n')
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig,axes=plt.subplots(1,2,figsize=(10,4),sharex=True,sharey=True)
for ax,level in zip(axes,['L1D','LL']):
 ax.plot([0,100],[0,100],'k--',linewidth=1,label='equal rates')
 for workload,marker in [('hot','o'),('target','D'),('cold','s')]:
  rr=[r for r in allrows if r['level']==level and r['workload']==workload and 'pmu_hit_percent' in r]
  ax.scatter([r['pmu_hit_percent'] for r in rr],[r['software_hit_percent'] for r in rr],marker=marker,facecolors='none',edgecolors='black',label=workload)
 ax.set(xlabel='Timed-region PMU-derived hit rate (%)',ylabel='Timing classifier (%)',title=level+' reference',xlim=(-2,102),ylim=(-2,102));ax.legend(fontsize=8);ax.grid(False)
fig.tight_layout();fig.savefig(OUT/'comparison.pdf');fig.savefig(OUT/'comparison.png',dpi=130)
print(json.dumps(dict(output=str(OUT),hosts=len(sources),samples=total,calibration=calibrations),indent=2))
