#!/usr/bin/env python3
"""Submit ordered, resumable follow-up stages without duplicate jobs."""
import argparse, datetime, getpass, json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
STAGES=['smoke','spatial','capacity','confirm','conflict','cross','l2','l2confirm','inclusion_final']
MAP={'haswell':('compute','normal'),'broadwell':('compute','normal'),'skylake':('compute_partners','short'),
     'cascadelake':('compute','normal'),'icelake_6326':('compute_partners','short'),'icelake_8358':('compute_partners','short'),
     'sapphirerapids':('compute_partners','short'),'genoa':('compute_partners','short'),'turin':('compute_partners','short')}
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True); temp=path.with_suffix('.tmp'); temp.write_text(json.dumps(data,indent=2)+'\n'); temp.replace(path)
def main():
    parser=argparse.ArgumentParser(); parser.add_argument('constraint',choices=MAP); parser.add_argument('stage',nargs='?',choices=STAGES)
    parser.add_argument('--continuation-of'); parser.add_argument('--next-after',choices=STAGES); args=parser.parse_args()
    if args.next_after:
        index=STAGES.index(args.next_after)
        if index+1==len(STAGES):
            print(json.dumps({'constraint':args.constraint,'pipeline':'followup_complete'})); return
        stage=STAGES[index+1]
    else: stage=args.stage
    if not stage: raise SystemExit('A stage or --next-after is required')
    plan=ROOT/'analysis'/args.constraint/'followup-plan.json'
    if not plan.exists() or not json.loads(plan.read_text()).get('ready'): raise SystemExit('Verified follow-up plan not ready')
    if stage!='smoke' and not (ROOT/'runs'/args.constraint/'followup-v1/smoke-passed.json').exists(): raise SystemExit('Follow-up smoke gate missing')
    predecessor={'spatial':'smoke','capacity':'spatial','confirm':'capacity','conflict':'confirm','cross':'conflict','l2':'cross','l2confirm':'l2','inclusion_final':'l2confirm'}.get(stage)
    if predecessor and predecessor!='smoke' and not (ROOT/'runs'/args.constraint/'followup-v1'/(predecessor+'-finished.json')).exists():
        raise SystemExit('Predecessor stage is incomplete: '+predecessor)
    partition,qos=MAP[args.constraint]; name='hz-'+args.constraint.replace('_','')[:8]+'-f'+str(STAGES.index(stage))
    active=subprocess.run(['squeue','-h','-u',getpass.getuser(),'-n',name,'-o','%i|%T|%R'],capture_output=True,text=True,timeout=30,check=True)
    active_ids={line.split('|')[0].split('_',1)[0] for line in active.stdout.splitlines() if line.strip()}
    if args.continuation_of:
        if active_ids-{args.continuation_of}: raise SystemExit('Another stage job is active: '+active.stdout.strip())
    elif active_ids: raise SystemExit('Refusing duplicate active stage: '+active.stdout.strip())
    # Three physical CPUs ensure a same-socket pair on these observed two-socket targets.
    cpus=3 if args.constraint in ('icelake_8358','genoa','turin') else 2
    logs=ROOT/'logs'/args.constraint; logs.mkdir(parents=True,exist_ok=True)
    command=['sbatch','--parsable','--account=ece592f26_cpu','--partition='+partition,'--qos='+qos,'--constraint='+args.constraint,
             '--nodes=1','--ntasks=1','--cpus-per-task='+str(cpus),'--distribution=block:block','--ntasks-per-core=1','--hint=nomultithread','--mem=2G','--time=01:55:00','--job-name='+name,
             '--output='+str(logs/('followup-'+stage+'.%j.stdout')),'--error='+str(logs/('followup-'+stage+'.%j.stderr')),
             '--export=ALL,HAZEL_CONSTRAINT='+args.constraint+',HAZEL_STAGE='+stage]
    if args.continuation_of: command.append('--dependency=afterany:'+args.continuation_of)
    command.append(str(ROOT/'suite/run_followup_segment.sh'))
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ'); path=ROOT/'submissions'/args.constraint/('followup-'+stage+'-'+stamp+'.json')
    record={'requested':now(),'constraint':args.constraint,'stage':'followup_'+stage,'continuation_of':args.continuation_of,'command':command,'prediction_freeze':None}
    save(path,record); result=subprocess.run(command,capture_output=True,text=True,timeout=30); record.update(finished=now(),returncode=result.returncode,stdout=result.stdout,stderr=result.stderr)
    if result.returncode==0: record['job_id']=result.stdout.strip().split(';')[0]
    save(path,record); print(json.dumps({'record':str(path),'returncode':result.returncode,'job_id':record.get('job_id'),'stderr':result.stderr}))
    raise SystemExit(result.returncode)
if __name__=='__main__': main()
