#!/usr/bin/env python3
"""Acquire the fixed three-point timing estimator on ECE or a Slurm compute node."""
import argparse,json,os,platform,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'main_code/common/phase1/scripts'))
from common import now,sha,topology,select_idle,write_json
from classify import classify

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);p.add_argument('--smoke',action='store_true');a=p.parse_args()
 host=platform.node().split('.')[0]
 if host not in ['sunbird','thunderbird','skylark','artemisia','charnwood','crux','ookay','upgrade'] and not (os.environ.get('SLURM_JOB_ID') and os.environ.get('SLURM_STEP_ID')):
  p.error('Execute on an ECE lab host or through srun on a Slurm compute node')
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 cfg=json.loads((ROOT/'competition/parameters.json').read_text());n=2048 if a.smoke else cfg['samples_per_point']
 source=ROOT/'main_code/common/phase1/src/cache_bench.c';binary=out/'cache_bench'
 env=os.environ.copy()
 for key in ['LD_PRELOAD','VALIDATION_LEVEL','VALIDATION_OUTPUT']:env.pop(key,None)
 build=['gcc']+cfg['compiler_flags']+[str(source),'-o',str(binary)]
 compiler=subprocess.run(['gcc','--version'],capture_output=True,text=True,check=True)
 b=subprocess.run(build,capture_output=True,text=True,env=env)
 write_json(out/'build.json',dict(command=build,compiler=compiler.stdout,stdout=b.stdout,stderr=b.stderr,returncode=b.returncode,source_sha256=sha(source)))
 b.check_returncode()
 rows,topo=topology();idlecfg=dict(idle_windows=2,idle_seconds=1,idle_fraction=.05)
 run=dict(started=now(),hostname=platform.node(),platform=platform.platform(),allowed_cpus=sorted(os.sched_getaffinity(0)),topology=topo,parameters=cfg,samples=n,slurm={k:os.environ.get(k) for k in ['SLURM_JOB_ID','SLURM_STEP_ID','SLURM_JOB_CONSTRAINTS']},commands={},cpus={},binary_sha256=sha(binary))
 write_json(out/'run.json',run)
 try:
  for label,size in [('hot',cfg['hot_bytes']),('target',cfg['target_bytes']),('cold',cfg['cold_bytes'])]:
   attempt=0
   while True:
    idle=select_idle(rows,idlecfg);write_json(out/(label+'-idle-'+str(attempt)+'.json'),idle);attempt+=1
    if idle['selected']:break
    time.sleep(15)
   cpu=idle['selected']['cpu'];idlecfg['_preferred_cpu']=cpu;run['cpus'][label]=cpu
   cmd=[str(binary),'chase',str(size),'8','0',str(n),'1',str(cfg['seed']),str(cpu),'random',str(out/(label+'.u64'))]
   run['commands'][label]=cmd;write_json(out/'run.json',run)
   r=subprocess.run(cmd,capture_output=True,text=True,env=env,timeout=1800)
   (out/(label+'.json')).write_text(r.stdout);(out/(label+'.stderr')).write_text(r.stderr)
   if r.returncode:raise RuntimeError(label+' benchmark failed: '+str(r.returncode))
  run['finished']=now();write_json(out/'run.json',run)
  if len(set(run['cpus'].values()))!=1:
   result=dict(status='unresolved: idle-core reselection changed calibration CPU',cpus=run['cpus'],estimate_percent=None)
  else:result=classify(out,a.smoke)
  write_json(out/'estimate.json',result);print(json.dumps(result,indent=2))
 except Exception as e:
  write_json(out/'failure.json',dict(time=now(),error=str(e)));raise
if __name__=='__main__':main()
