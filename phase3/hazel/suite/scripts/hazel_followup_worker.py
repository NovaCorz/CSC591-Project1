#!/usr/bin/env python3
"""Slurm-only adapter for the verified Phase-I follow-up timing worker."""
import argparse, fcntl, hashlib, json, os
from pathlib import Path
import platform, shutil, sys, time, traceback

import followup_worker
from common import now, sha, topology, write_json
from worker import command

ROOT=Path(__file__).resolve().parents[1]
STAGES=['smoke','spatial','capacity','confirm','conflict','cross','l2','l2confirm','inclusion_final']

class SegmentDeadline(Exception): pass

def model():
    with open('/proc/cpuinfo') as source:
        return next((line.split(':',1)[1].strip() for line in source if line.startswith('model name') and ':' in line),'unavailable')

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('stage',choices=STAGES); args=parser.parse_args()
    constraint=os.environ.get('HAZEL_CONSTRAINT'); job=os.environ.get('SLURM_JOB_ID')
    allowed=json.loads((ROOT/'config/phase1.json').read_text())['hosts']
    if not job: raise SystemExit('Refusing to run outside Slurm')
    if constraint not in allowed: raise SystemExit('Invalid HAZEL_CONSTRAINT')
    plan_path=ROOT.parent/'analysis'/constraint/'followup-plan.json'
    if not plan_path.exists(): raise SystemExit('Verified target-specific follow-up plan is missing')
    plan=json.loads(plan_path.read_text())
    if not plan.get('ready'): raise SystemExit('Timing-derived follow-up plan is unresolved: '+str(plan.get('missing_inputs')))
    out=ROOT.parent/'runs'/constraint/'followup-v1'; out.mkdir(parents=True,exist_ok=True)
    rows,topo=topology(); inherited=sorted(os.sched_getaffinity(0))
    if len(inherited)<2: raise RuntimeError('Two allocated physical CPUs required for idle alternative/cross-core controls')
    by_socket={}
    for row in rows:
        if row['cpu'] in inherited:
            by_socket.setdefault(row['socket'],set()).add(row['core'])
    if not any(len(cores)>=2 for cores in by_socket.values()):
        write_json(out/('allocation-failure-'+job+'.json'),dict(time=now(),job_id=job,
            affinity=inherited,allocated=[row for row in rows if row['cpu'] in inherited],
            reason='No two allocated physical cores share a socket; waiting cannot resolve this allocation'))
        raise RuntimeError('Unsuitable Slurm allocation: no same-socket physical core pair')

    config=json.loads((ROOT/'config/phase1.json').read_text())
    config.update(batch=plan['batch'],point_timeout_seconds=1800,_use_noise_history=True,
                  _hazel_constraint=constraint,_slurm_job_id=job,
                  _affinity_policy='Retain inherited Slurm mask; never expand to unallocated CPUs')
    prior=[]
    for path in out.glob('*/*/complete.json'):
        row=json.loads(path.read_text())
        if row.get('status')=='passed': prior.append(row)
    if prior:
        latest=max(prior,key=lambda row:row.get('finished',''))
        config['_preferred_cpu']=latest['selected']['cpu']
        config['_preferred_cpu_reason']='Most recent quality-passing acquisition; every idle window still required'
    build=out/'build'; build.mkdir(exist_ok=True); os.chdir(build)
    for name in ('cache_bench.c','followup_bench.c'): shutil.copy2(ROOT/'src'/name,build/name)
    flags=['-O0','-g','-std=c11','-Wall','-Wextra','-Werror','-fno-omit-frame-pointer','-pthread']
    compiler=shutil.which('gcc'); command([compiler,'--version'],build,'compiler')
    command([compiler]+flags+['followup_bench.c','-o','followup_bench'],build,'compile')
    command([compiler]+flags+['-S','followup_bench.c','-o','followup_bench.s'],build,'assembly')
    disassembly=command(['objdump','-d','followup_bench'],build,'objdump'); (build/'followup_bench.dis').write_text(disassembly)
    sources={str(path.relative_to(ROOT)):sha(path) for folder in ('src','scripts','config') for path in (ROOT/folder).glob('*') if path.is_file()}
    digest=hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest()
    provenance=out/'provenance'/digest; provenance.mkdir(parents=True,exist_ok=True)
    for relative in sources:
        dest=provenance/relative; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(ROOT/relative,dest)
    write_json(provenance/'manifest.json',{'time':now(),'files':sources,'plan':str(plan_path),'plan_sha256':sha(plan_path)})
    source_digest=hashlib.sha256((sha(build/'cache_bench.c')+sha(build/'followup_bench.c')).encode()).hexdigest()
    config.update(_benchmark_path=str(build/'followup_bench'),_source_digest=source_digest,
                  _provenance_manifest=str((provenance/'manifest.json').relative_to(out)))
    env=out/'environment-history'/('job-'+job+'.json'); env.parent.mkdir(exist_ok=True)
    config['_environment_record']=str(env.relative_to(out))
    write_json(env,{'time':now(),'constraint':constraint,'stage':args.stage,'hostname':platform.node(),
        'exact_cpu_model':model(),'isa':platform.machine(),'python':sys.version,
        'inherited_and_available_affinity':inherited,'topology':rows,'topology_command':topo,
        'slurm':{k:v for k,v in os.environ.items() if k.startswith('SLURM_')},
        'config':config,'plan':plan,'binary_sha256':sha(build/'followup_bench'),'compiler_flags':flags,
        'git_source_commit':'1f687d7f6eec0cf79e74afc57118db013aa036c3','prediction_freeze':None,
        'protocol_deviation':'Execution explicitly authorized without section 8.6.1 prediction freeze.'})
    end=int(os.environ.get('SLURM_JOB_END_TIME','0') or 0); margin=120 if args.stage=='smoke' else 2100
    original=followup_worker.point
    def bounded(family,params,context):
        if end and time.time()+margin>=end: raise SegmentDeadline('Insufficient Slurm time for another follow-up point')
        return original(family,params,context)
    followup_worker.point=bounded
    lock_path=out/('worker-'+args.stage+'.lock')
    with open(lock_path,'w') as lock:
      fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
      try:
        if args.stage=='smoke':
            smoke=out/'smoke'; smoke.mkdir(exist_ok=True)
            smoke_config=dict(config,_environment_record='../'+config['_environment_record'],_provenance_manifest='../'+config['_provenance_manifest'])
            cases=[dict(mode='overhead'),dict(mode='chase',bytes=65536),dict(mode='spatial',bytes=65536,stride=512,align=24,offset=40),
                   dict(mode='chase',bytes=65536,page='huge'),dict(mode='hot'),dict(mode='probe',bytes=65536,batch=32),
                   dict(mode='cross',bytes=65536,batch=32,offset=0),dict(mode='cross',bytes=65536,batch=32,offset=1)]
            records=[bounded('functional',followup_worker.arguments(config,**case),(smoke,smoke_config,rows,True)) for case in cases]
            if any(row.get('status') not in ('passed','noisy') for row in records): raise RuntimeError('Follow-up smoke failed')
            write_json(out/'smoke-passed.json',{'time':now(),'source_sha256':source_digest,'points':len(records)})
        elif args.stage=='inclusion_final':
            gate=out/'smoke-passed.json'
            if not gate.exists() or json.loads(gate.read_text())['source_sha256']!=source_digest: raise RuntimeError('Exact-source follow-up smoke required')
            if not (out/'l2confirm-finished.json').exists(): raise RuntimeError('Final inclusion controls require completed hierarchy refinements')
            context=(out,config,rows,False); results=[]
            for footprint in plan['cross_footprints']:
                for pressure in (0,1):
                    for seed in (config['seed']+2001,config['seed']+2002):
                        params=followup_worker.arguments(config,mode='cross',bytes=footprint,
                            stride=plan['spatial_candidate'],offset=pressure,batch=1024,page='huge',seed=seed)
                        results.append(bounded('cross_core_reload_final',params,context))
                params=followup_worker.arguments(config,mode='probe',bytes=footprint,
                    stride=plan['spatial_candidate'],batch=1024,page='huge',seed=config['seed']+2003)
                results.append(bounded('same_core_reload_final',params,context))
            params=followup_worker.arguments(config,mode='hot',seed=config['seed']+2004)
            results.append(bounded('target_hot_final',params,context))
            write_json(out/'inclusion_final-finished.json',{'time':now(),'stage':'inclusion_final','points':len(results),
                'passed':sum(row.get('status')=='passed' for row in results),'noisy':sum(row.get('status')=='noisy' for row in results),
                'limitation':'Matched cross-core pressure is post-refinement evidence. It does not prove that helper pressure evicts only one lower level or that every upper copy remains resident.'})
        else:
            gate=out/'smoke-passed.json'
            if not gate.exists() or json.loads(gate.read_text())['source_sha256']!=source_digest: raise RuntimeError('Exact-source follow-up smoke required')
            followup_worker.run_stage(args.stage,out,config,rows,plan)
        write_json(out/('segment-'+job+'.json'),{'time':now(),'job_id':job,'stage':args.stage,'status':'stage_complete'})
      except SegmentDeadline as exc:
        write_json(out/('segment-'+job+'.json'),{'time':now(),'job_id':job,'stage':args.stage,'status':'continuation_required','reason':str(exc)})
        raise SystemExit(75)
      except Exception as exc:
        write_json(out/('failure-'+job+'.json'),{'time':now(),'job_id':job,'stage':args.stage,'error':str(exc),'traceback':traceback.format_exc()})
        raise

if __name__=='__main__': main()
