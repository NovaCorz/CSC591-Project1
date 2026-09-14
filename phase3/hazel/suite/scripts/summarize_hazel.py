#!/usr/bin/env python3
"""Create exact timing-only Hazel tables without repairing unresolved values."""
import argparse,csv,datetime,json,os
from pathlib import Path
from common import sha
ROOT=Path(__file__).resolve().parents[1]
GENERATIONS={'haswell':'Haswell','broadwell':'Broadwell','skylake':'Skylake-SP','cascadelake':'Cascade Lake',
 'icelake_6326':'Ice Lake-SP','icelake_8358':'Ice Lake-SP','sapphirerapids':'Sapphire Rapids','genoa':'Zen 4 / Genoa','turin':'Zen 5 / Turin'}
def main():
 p=argparse.ArgumentParser();p.add_argument('--hosts',nargs='+',required=True);a=p.parse_args()
 if not os.environ.get('SLURM_JOB_ID'):raise SystemExit('Slurm job required')
 out=ROOT.parent/'results';out.mkdir(parents=True,exist_ok=True);rows=[];details={}
 independent_path=ROOT/'data_processed/independent-load/summary.json'
 independent={d['host']:d for d in json.loads(independent_path.read_text())} if independent_path.exists() else {}
 for host in a.hosts:
  baseline=json.loads((ROOT/'data_processed'/(host+'-inference.json')).read_text())
  follow=json.loads((ROOT.parent/'analysis/followup'/(host+'-inference.json')).read_text())
  envs=sorted((ROOT.parent/'runs'/host/'baseline/full/environment-history').glob('job-*.json'))
  env=json.loads(envs[0].read_text()) if envs else {}
  l1=baseline['l1_candidate'];bounds=l1.get('capacity_interval_bytes') or [None,None]
  table=follow.get('revised_cache_table',[])
  rows.append({'constraint':host,'generation':GENERATIONS[host],'exact_cpu_model':env.get('exact_cpu_model'),
   'baseline_verified_points':baseline['verified_points'],'baseline_noisy_points':baseline['noisy_points'],
   'followup_verified_points':follow['verified_points'],'followup_noisy_points':follow['noisy_points'],
   'l1_capacity_lower_bytes':bounds[0],'l1_capacity_upper_bytes':bounds[1],
   'l1_line_candidate_bytes':l1.get('line_bytes'),'l1_ways_candidate':l1.get('ways'),
   'l1_small_class_median_native':l1.get('hit_class_statistics',{}).get('median'),'l1_unit':l1.get('unit'),
   'timing_class_count':max([model.get('chosen_classes',0) for model in follow.get('capacity',{}).get('plateau_models',[])],default=None),
   'post_refinement_inclusion_status':follow.get('post_refinement_inclusion',{}).get('status'),
   'independent_load_ratio_median':independent.get(host,{}).get('ratio_median'),
   'inference_status':'complete with explicit uncertainties' if follow.get('acquisition_complete') else 'unresolved/incomplete'})
  details[host]={'baseline':baseline,'followup':follow,'independent_load':independent.get(host),
    'slurm_environments':[str(path.relative_to(ROOT.parent)) for path in envs]}
 fields=list(rows[0]);
 with (out/'machine-results.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 table_rows=[]
 for host in a.hosts:
  for row in details[host]['followup'].get('revised_cache_table',[]):table_rows.append(row)
 if table_rows:
  fields=list(dict.fromkeys(key for row in table_rows for key in row))
  with (out/'cache-inference-table.csv').open('w',newline='') as f:
   w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows({k:json.dumps(v) if isinstance(v,(dict,list)) else v for k,v in row.items()} for row in table_rows)
 result={'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'job_id':os.environ['SLURM_JOB_ID'],'hosts':a.hosts,
  'distinct_generations':sorted({GENERATIONS[h] for h in a.hosts}),'prediction_freeze':None,
  'protocol_deviation':'Hazel timing began before a lab-only prediction freeze at the user’s explicit direction; held-out prediction-order credit cannot be recovered retroactively.',
  'scope':'Timing-only Hazel acquisition and inference. No Phase II, PMU, published cache lookup, prediction fitting, or held-out evaluation.',
  'details':details,'key_table':'machine-results.csv','cache_table':'cache-inference-table.csv',
  'limitations':['Reported fields are best-supported timing inferences, not specification facts.',
    'Unresolved/noisy points and unsuccessful attempts remain preserved.',
    'Post-refinement cross-core pressure does not prove perfectly lower-only eviction.',
    'Deeper timing classes may mix cache, translation, replacement, NUMA, and memory effects.',
    'Native TSC ticks/access are not nominal core cycles.']}
 (out/'timing-only-summary.json').write_text(json.dumps(result,indent=2)+'\n')
 manifest={str(path.relative_to(ROOT.parent)):{'bytes':path.stat().st_size,'sha256':sha(path)} for path in sorted(out.glob('*')) if path.is_file() and path.name!='manifest.json'}
 (out/'manifest.json').write_text(json.dumps({'time':result['time'],'files':manifest},indent=2)+'\n')
 print(json.dumps({'hosts':a.hosts,'distinct_generations':len(result['distinct_generations']),'results':str(out)}))
if __name__=='__main__':main()
