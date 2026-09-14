#!/usr/bin/env python3
"""Submit one final compute validator once minimum required coverage is ready."""
import datetime,getpass,json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
GENERATIONS={'haswell':'Haswell','broadwell':'Broadwell','skylake':'Skylake-SP','cascadelake':'Cascade Lake','icelake_6326':'Ice Lake-SP','icelake_8358':'Ice Lake-SP','sapphirerapids':'Sapphire Rapids','genoa':'Zen 4 / Genoa','turin':'Zen 5 / Turin'}
def main():
 hosts=[]
 for host in GENERATIONS:
  try:follow=json.loads((ROOT/'analysis/followup'/(host+'-inference.json')).read_text())
  except (OSError,ValueError):continue
  if follow.get('acquisition_complete') and (ROOT/'runs'/host/'page_control/collection-finished.json').exists() and (ROOT/'runs'/host/'independent-load-v1/full-finished.json').exists():hosts.append(host)
 generations={GENERATIONS[h] for h in hosts}
 if len(generations)<5 or 'haswell' not in hosts or 'turin' not in hosts or not ({'genoa','turin'}&set(hosts)):
  print(json.dumps({'submitted':False,'reason':'coverage gate pending','hosts':hosts,'generations':sorted(generations)}));return
 active=subprocess.run(['squeue','-h','-u',getpass.getuser(),'-n','hz-finalize','-o','%i|%T|%R'],capture_output=True,text=True,timeout=30,check=True)
 if active.stdout.strip():print(json.dumps({'submitted':False,'reason':'finalizer already active','active':active.stdout.strip()}));return
 logs=ROOT/'logs/final';logs.mkdir(parents=True,exist_ok=True)
 command=['sbatch','--parsable','--account=ece592f26_cpu','--partition=compute','--qos=normal','--nodes=1','--ntasks=1','--cpus-per-task=1','--mem=8G','--time=04:00:00','--job-name=hz-finalize',
  '--output='+str(logs/'finalize.%j.stdout'),'--error='+str(logs/'finalize.%j.stderr'),'--wrap=srun --cpu-bind=cores python3 '+str(ROOT/'suite/scripts/finalize_hazel.py')]
 result=subprocess.run(command,capture_output=True,text=True,timeout=30)
 stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ');record={'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'ready_hosts':hosts,'command':command,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
 path=ROOT/'submissions/final'/('finalize-'+stamp+'.json');path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(record,indent=2)+'\n')
 print(json.dumps({'submitted':result.returncode==0,'job_id':result.stdout.strip() if result.returncode==0 else None,'record':str(path)}));raise SystemExit(result.returncode)
if __name__=='__main__':main()
