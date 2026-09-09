#!/usr/bin/env python3
"""Supplementary THP controls; run after the primary worker exits on the host."""
import fcntl
import json
import os
from pathlib import Path
import platform
import random
import shutil
import time
from common import now, sha, topology, write_json
from worker import ROOT, command, parameters, point

def main():
    cfg=json.loads((ROOT/'config/phase1.json').read_text())
    host=platform.node().split('.')[0]
    if host not in cfg['hosts']:raise SystemExit('Only assigned ECE lab hosts are allowed')
    lock=open(ROOT/'worker.lock','w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    primary=ROOT/'machines'/host/'full'
    if not (primary/'collection-finished.json').exists():raise SystemExit('Primary collection must finish first')
    rows,topo=topology();inherited=sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{r['cpu'] for r in rows})
    out=ROOT/'machines'/host/'page_control';out.mkdir(parents=True,exist_ok=True)
    build=out/'build';build.mkdir(exist_ok=True)
    for name in ('cache_bench.c','page_control.c'):shutil.copy2(ROOT/'src'/name,build/name)
    os.chdir(build)
    flags=['-O0','-g','-std=c11','-Wall','-Wextra','-Werror','-fno-omit-frame-pointer']
    gcc=shutil.which('gcc');command([gcc,'--version'],build,'compiler')
    command([gcc]+flags+['page_control.c','-o','page_control'],build,'compile')
    dis=command(['objdump','-d','page_control'],build,'objdump');(build/'page_control.dis').write_text(dis)
    controls=[json.loads(p.read_text()) for p in primary.glob('capacity/*/complete.json')]
    if not controls:raise SystemExit('No primary batch calibration available')
    calibration=json.loads((primary/'batch-calibration.json').read_text())
    if not calibration['passed']:raise SystemExit('Primary batch calibration did not pass')
    cfg['batch']=calibration['chosen_batch']
    cfg['_benchmark_path']=str(build/'page_control')
    cfg['_source_digest']=sha(build/'page_control.c')
    cfg['_page_control']=True
    env=out/('environment-'+str(time.time_ns())+'.json')
    write_json(env,dict(time=now(),host=host,inherited_affinity=inherited,available_affinity=sorted(os.sched_getaffinity(0)),
        topology=topo,wrapper_sha256=sha(build/'page_control.c'),included_primary_sha256=sha(build/'cache_bench.c'),
        python=platform.python_version(),config=cfg,policy='Only this anonymous mapping receives MADV_HUGEPAGE; actual backing recorded from own smaps whitelist'))
    cfg['_environment_record']=str(env.relative_to(out))
    # Validate the new allocation wrapper with two SMALL functional points first.
    smoke_out=out/'smoke';smoke_out.mkdir(exist_ok=True)
    smoke_cfg=dict(cfg,_environment_record='../'+str(env.relative_to(out)))
    smoke=[point('page_control',parameters(cfg,bytes=w,page_policy='THP-request'),(smoke_out,smoke_cfg,rows,True)) for w in (32768,262144)]
    if any(r.get('status') not in ('passed','noisy') for r in smoke):
        write_json(out/'control-unavailable.json',dict(time=now(),reason='Page-control wrapper smoke failed; see retained attempts. No full control launched.'))
        return
    write_json(out/'smoke-passed.json',dict(time=now(),wrapper_sha256=cfg['_source_digest'],samples_per_point=2048))
    # Geometric control range is chosen independently of cache specifications.
    sizes=[];w=cfg['min_bytes']
    while w<=cfg['max_bytes']:sizes.append(w);w*=4
    random.Random(cfg['seed']).shuffle(sizes)
    results=[point('page_control',parameters(cfg,bytes=w,page_policy='THP-request'),(out,cfg,rows,False)) for w in sizes]
    write_json(out/'collection-finished.json',dict(time=now(),points=len(results),sizes=sizes,
        note='THP advice is not proof of actual huge-page backing. Use anon_huge_kib in each record.'))

if __name__=='__main__':main()
