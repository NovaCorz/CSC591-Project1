#!/usr/bin/env python3
"""Submit raw baseline validation/inference after acquisition completes."""
import argparse, datetime, getpass, json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {'haswell','broadwell','skylake','cascadelake','icelake_6326','icelake_8358','sapphirerapids','genoa','turin'}

def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True); temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(data,indent=2)+'\n'); temp.replace(path)

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('constraint',choices=ALLOWED); args=parser.parse_args()
    marker=ROOT/'runs'/args.constraint/'baseline/full/collection-finished.json'
    if not marker.exists(): raise SystemExit('Refusing analysis before baseline finish marker')
    name='hz-'+args.constraint.replace('_','')[:9]+'-analysis'
    active=subprocess.run(['squeue','-h','-u',getpass.getuser(),'-n',name,'-o','%i|%T|%R'],capture_output=True,text=True,timeout=30,check=True)
    if active.stdout.strip(): raise SystemExit('Refusing duplicate analysis: '+active.stdout.strip())
    logs=ROOT/'logs'/args.constraint; logs.mkdir(parents=True,exist_ok=True)
    command=['sbatch','--parsable','--account=ece592f26_cpu','--partition=compute','--qos=normal',
             '--nodes=1','--ntasks=1','--cpus-per-task=1','--mem=4G','--time=01:00:00','--job-name='+name,
             '--output='+str(logs/'analysis.%j.stdout'),'--error='+str(logs/'analysis.%j.stderr'),
             str(ROOT/'suite/run_analysis.sh'),args.constraint]
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    path=ROOT/'submissions'/args.constraint/('analysis-'+stamp+'.json')
    record={'requested':now(),'constraint':args.constraint,'stage':'baseline_analysis','command':command}
    save(path,record); result=subprocess.run(command,capture_output=True,text=True,timeout=30)
    record.update(finished=now(),returncode=result.returncode,stdout=result.stdout,stderr=result.stderr)
    if result.returncode==0: record['job_id']=result.stdout.strip().split(';')[0]
    save(path,record); print(json.dumps({'record':str(path),'returncode':result.returncode,'job_id':record.get('job_id'),'stderr':result.stderr}))
    raise SystemExit(result.returncode)

if __name__=='__main__': main()
