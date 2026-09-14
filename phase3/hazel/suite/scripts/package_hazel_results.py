#!/usr/bin/env python3
"""Package already-verified timing results, on a Slurm compute node."""
import csv,datetime,hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT.parent

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def main():
 if not os.environ.get('SLURM_JOB_ID'):raise SystemExit('Slurm job required')
 out=BASE/'results'; summary=json.loads((out/'timing-only-summary.json').read_text());hosts=summary['hosts']
 follow=json.loads((BASE/'analysis/followup/verification.json').read_text())
 indep=json.loads((ROOT/'data_processed/independent-load/verification.json').read_text())
 assert follow['complete'] and indep['passed'] and set(indep['hosts'])==set(hosts)
 assert len(summary['distinct_generations'])>=5
 env=dict(os.environ,PYTHONPATH=str(BASE/'tools/python-packages'),MPLCONFIGDIR=str(out/'matplotlib-config'))
 if '--skip-plots' not in sys.argv:
  subprocess.run([sys.executable,str(ROOT/'scripts/plot_hazel_independent.py')],env=env,check=True,cwd=ROOT)
 lines=['# Hazel timing-only results','', 'Completed scope: Haswell, Cascade Lake, Ice Lake 8358, Genoa, and Turin. No published-cache verification or prediction comparison is included here.','', '| Generation | Baseline points | Follow-up points | Follow-up noisy points | Independent pairs |','|---|---:|---:|---:|---:|']
 for h in hosts:
  d=summary['details'][h]; b=d['baseline'];f=d['followup'];i=d['independent_load']
  assert b['collection_complete'] and f['acquisition_complete']
  lines.append('| '+h+' | '+str(b['verified_points'])+' | '+str(f['verified_points'])+' | '+str(f['noisy_points'])+' | '+str(i['qualified_pairs'])+'/6 |')
 lines+=['','## Files','', '- [Machine results](machine-results.csv)', '- [Cache inference table](cache-inference-table.csv)', '- [Detailed timing-only evidence and limitations](timing-only-summary.json)', '- [Follow-up verification](../analysis/followup/verification.json)', '- [Follow-up statistics](../analysis/followup/statistics.csv)', '- [Independent-load verification](../suite/data_processed/independent-load/verification.json)', '- [Independent-load table](../suite/data_processed/independent-load/summary.csv)', '- [Independent-load box plots](../suite/plots/independent-load/distributions.pdf)', '- [Baseline plots](../suite/plots/)', '- [Follow-up plots](../suite/plots/followup/)', '', '## Interpretation','', 'The independent-load diagnostic uses the approved no-calibration-gate variant for Haswell, Cascade Lake, and Ice Lake 8358. Genoa and Turin retain the original calibrated diagnostic. The variant is recorded per host. These comparisons demonstrate parallel load throughput; they are not physical cache-hit latency estimates.','', 'Timing classes and effective capacities remain conditional inferences. A blank timing-class count means unresolved, not zero cache levels. Cross-core pressure does not guarantee isolated lower-only eviction, and deeper latency classes can mix translation, cache, NUMA, and memory effects. Read the table/status fields before interpreting any numerical candidate as physical cache geometry.','', 'All failed and noisy attempts remain under ../runs/. Excluded targets were not rerun. Raw data remain in scratch storage and must be retained for reproduction.','', '## Reproduction','', 'From ../suite/, submit scripts/finalize_hazel.py through Slurm, then scripts/package_hazel_results.py. Never run raw verification or plotting on a login node. Source versions, run arguments, compiler flags, binding, seeds, and raw hashes are recorded alongside the acquisition and verification artifacts.']
 (out/'README.md').write_text('\n'.join(lines)+'\n')
 # Build the inventory on a compute node, including preserved unsuccessful attempts.
 inputs={}
 for h in hosts:
  for p in (BASE/'runs'/h).rglob('run.json'):
   d=json.loads(p.read_text())
   if 'raw' in d:inputs[str(p.relative_to(BASE))]={'record_sha256':sha(p),'raw':d['raw'],'raw_sha256':d.get('raw_sha256'),'sample_count':d.get('exact_raw_count'),'status':d.get('status')}
 (out/'raw-record-inventory.json').write_text(json.dumps(inputs,indent=2)+'\n')
 files={}
 for directory in [out,BASE/'analysis/followup',ROOT/'data_processed',ROOT/'plots',ROOT/'scripts',ROOT/'src',ROOT/'config']:
  for p in directory.rglob('*'):
   if not p.is_file() or p.is_symlink() or 'matplotlib-config' in p.parts or '__pycache__' in p.parts or p.name in ['timing-freeze.json','manifest.json']:continue
   files[str(p.relative_to(BASE))]={'bytes':p.stat().st_size,'sha256':sha(p)}
 freeze={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'job_id':os.environ['SLURM_JOB_ID'],'hostname':os.uname().nodename,'scope':'Hazel timing-only results before hardware verification; measurements and interpretation retain explicit uncertainties','hosts':hosts,'files':files,'raw_inventory':'results/raw-record-inventory.json','independent_calibration_policy':'Explicit per-host approved variant; no global calibration claim'}
 (out/'timing-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
 print(json.dumps({'packaged':True,'hosts':hosts,'files':len(files),'raw_records':len(inputs),'output':str(out)}))
if __name__=='__main__':main()
