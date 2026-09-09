#!/usr/bin/env python3
"""Isolated, resumable independent-load diagnostic using existing idle/noise controls."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import time
from common import now, sha, topology, write_json
from worker import ROOT, command, point

FILES = ['src/cache_bench.c','src/independent_load.c','scripts/common.py','scripts/worker.py',
         'scripts/independent_worker.py','config/phase1.json','config/independent-load.json']


def source_manifest():
    files={name:sha(ROOT/name) for name in FILES}
    return files,hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()


def audit_loops(disassembly, isa):
    result={}
    for name in ('serial4','parallel4'):
        match=re.search(r'<'+name+r'>:\n(.*?)(?=\n\n)',disassembly,re.S)
        if not match: raise RuntimeError('Missing '+name+' disassembly')
        text=match.group(0)
        pattern=r'ldr\s+(x\d+),\s*\[\1\]' if isa=='aarch64' else r'mov\s+\(%(\w+)\),%\1'
        registers=re.findall(pattern,text)
        if len(registers)!=4 or len(set(registers))!=(1 if name=='serial4' else 4):
            raise RuntimeError('Dependency/register audit failed: '+name)
        if not re.search(r'b\.ne' if isa=='aarch64' else r'jne',text):
            raise RuntimeError('Missing loop branch: '+name)
        result[name]=dict(disassembly=text,load_registers=registers,loads_per_iteration=4)
    return result


def setup(out,cfg,plan):
    rows,topo=topology(); inherited=sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{r['cpu'] for r in rows})
    files,digest=source_manifest();build=out/'build'/digest;build.mkdir(parents=True,exist_ok=True)
    os.chdir(build)
    if not (build/'verification.json').exists():
        for name in FILES:
            dest=build/'source'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,dest)
        flags=['-O0','-g','-std=c11','-Wall','-Wextra','-Werror','-fno-omit-frame-pointer']
        cc=shutil.which('gcc');command([cc,'--version'],build,'compiler')
        command([cc]+flags+['source/src/independent_load.c','-o','independent_load'],build,'compile')
        command([cc]+flags+['-S','source/src/independent_load.c','-o','independent_load.s'],build,'assembly')
        dis=command(['objdump','-d','independent_load'],build,'objdump')
        (build/'independent_load.dis').write_text(dis)
        loops=audit_loops(dis,platform.machine());write_json(build/'loop-audit.json',loops)
        write_json(build/'manifest.json',dict(files=files,source_digest=digest))
        write_json(build/'verification.json',dict(time=now(),source_digest=digest,binary_sha256=sha(build/'independent_load'),flags=flags))
    verified=json.loads((build/'verification.json').read_text())
    assert verified['binary_sha256']==sha(build/'independent_load')
    assert all(sha(build/'source'/name)==value for name,value in files.items())
    cfg.update(attempts=1,point_timeout_seconds=1200,_use_noise_history=True,
        _source_digest=digest,_benchmark_path=str(build/'independent_load'),
        _provenance_manifest=str((build/'manifest.json').relative_to(out)))
    env=out/('environment-'+str(time.time_ns())+'.json');cfg['_environment_record']=str(env.relative_to(out))
    write_json(env,dict(time=now(),host=platform.node(),isa=platform.machine(),kernel=platform.release(),
        python=platform.python_version(),inherited_affinity=inherited,available_affinity=sorted(os.sched_getaffinity(0)),
        topology=topo,config=cfg,plan=plan,build_verification=verified))
    return rows,digest


def run(stage,out,cfg,rows,plan,digest):
    def measure(family,streams=1,mode='chase',batch=None,seed=None,**identity):
        p=dict(mode=mode,bytes=plan['bytes'],stride=plan['stride'],offset=0,batch=batch or plan['initial_batch'],
            seed=seed or plan['seeds'][0],order='random',streams=streams,extra_args=[streams],**identity)
        return point(family,p,(out,cfg,rows,stage=='smoke'))
    if stage=='smoke':
        records=[measure('smoke',streams=s) for s in (1,4)]
        records += [measure('smoke',mode=m) for m in ('overhead','loop')]
        if not all(d.get('status') in ('passed','noisy') and d['measurement']['functional_checks_passed'] for d in records):
            raise RuntimeError('Smoke failure; inspect retained attempts')
        write_json(out/'smoke-passed.json',dict(time=now(),source_digest=digest,records=[d['attempt'] for d in records]))
        return
    gate=json.loads((out/'smoke-passed.json').read_text());assert gate['source_digest']==digest
    batch=plan['initial_batch'];calibrations=[]
    while True:
        records=[];passed=False
        for repetition in range(plan['pair_attempts']):
            group=[measure('calibration',mode=m,streams=s,batch=batch,repetition=repetition)
                   for m,s in [('overhead',1),('loop',1),('chase',1),('chase',4)]]
            clean=all(d.get('status')=='passed' for d in group) and len({d.get('selected',{}).get('cpu') for d in group})==1
            fraction=(group[0]['statistics']['median']/(batch*min(d['statistics']['median'] for d in group[2:]))) if clean else None
            records.append(dict(records=[d.get('attempt') for d in group],same_core_clean=clean,fraction=fraction))
            if clean:passed=fraction<=plan['timer_fraction_limit'];break
        calibrations.append(dict(batch=batch,attempts=records,passed=passed))
        write_json(out/'timer-gate.json',dict(time=now(),source_digest=digest,calibrations=calibrations,passed=passed,batch=batch))
        if passed:break
        if not clean or batch>=plan['maximum_batch']:raise RuntimeError('Timer calibration unresolved; retained; do not launch comparisons')
        batch*=2
    cohorts=[]
    for seed in plan['seeds']:
        for order_index,order in enumerate(plan['orders']):
            attempts=[];selected=[]
            for repetition in range(plan['pair_attempts']):
                group=[measure('comparison',streams=s,batch=batch,seed=seed,order_index=order_index,repetition=repetition) for s in order]
                clean=all(d.get('status')=='passed' for d in group) and len({d.get('selected',{}).get('cpu') for d in group})==1
                if clean:
                    clean=len({d['measurement']['ring_hash'] for d in group})==1
                attempts.append(dict(records=[d.get('attempt') for d in group],same_core_clean=clean))
                if clean:selected=[d['attempt'] for d in group];break
            cohorts.append(dict(seed=seed,order=order,order_index=order_index,attempts=attempts,selected=selected))
            write_json(out/'cohorts.json',dict(source_digest=digest,batch=batch,cohorts=cohorts,selection=plan['selection']))
    write_json(out/'full-finished.json',dict(time=now(),source_digest=digest,cohorts=len(cohorts),qualified=sum(bool(c['selected']) for c in cohorts)))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['smoke','full']);args=ap.parse_args()
    cfg=json.loads((ROOT/'config/phase1.json').read_text());plan=json.loads((ROOT/'config/independent-load.json').read_text())
    host=platform.node().split('.')[0]
    if host not in cfg['hosts']:raise RuntimeError('Only the eight assigned lab hosts may acquire data')
    out=ROOT/'machines'/host/plan['round'];out.mkdir(parents=True,exist_ok=True)
    with open(out/'worker.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        rows,digest=setup(out,cfg,plan);run(args.stage,out,cfg,rows,plan,digest)


if __name__=='__main__':main()
