#!/usr/bin/env python3
"""Additional Phase-I tests; separate data and no changes to frozen earlier rounds."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import re
import shutil
import time
from common import now, sha, topology, write_json
from worker import ROOT, command, point
from followup_worker import arguments

ROUND = 'uncertainty-v1'


def conflict_offsets(period, stride, count, scrub, variant=1):
    # Every address shares the timing-derived L1 index hypothesis. Fixed odd
    # multiples spread scrub traffic over other candidate lower-level indices.
    if stride % (2*period):
        raise ValueError('Candidate stride must preserve the next index bit')
    fixed = [((2 if variant == 1 else 4)*i+1)*period for i in range(scrub)]
    lower = [2097152+i*stride for i in range(count)]
    result = fixed+lower
    if len(set(result)) != len(result) or any(v % 8 for v in result):
        raise ValueError('Invalid conflict construction')
    return result


def detected_edges(records, axis):
    rows = sorted(records, key=lambda r: r['parameters'][axis])
    edges = []
    for a,b in zip(rows, rows[1:]):
        if a.get('status') != 'passed' or b.get('status') != 'passed': continue
        sa,sb = a['statistics'],b['statistics']
        if a['selected']['cpu'] != b['selected']['cpu']: continue
        if sb['median'] > 1.15*sa['median'] and sb['q1'] > sa['q3']:
            edges.append([a['parameters'][axis],b['parameters'][axis]])
    return edges


def blocked_pairs(records):
    """Remeasure every coarse pair invalidated by quality/core mismatch, regardless of effect."""
    rows=sorted(records,key=lambda r:r['parameters']['candidate_count'])
    return [[a['parameters']['candidate_count'],b['parameters']['candidate_count']] for a,b in zip(rows,rows[1:])
        if a.get('status')!='passed' or b.get('status')!='passed'
        or a.get('selected',{}).get('cpu')!=b.get('selected',{}).get('cpu')]


def clean_cross_core_pairs(records):
    rows=sorted(records,key=lambda r:r['parameters']['bytes'])
    return [[a['parameters']['bytes'],b['parameters']['bytes']] for a,b in zip(rows,rows[1:])
        if a.get('status')==b.get('status')=='passed' and a['selected']['cpu']!=b['selected']['cpu']]


def setup(host, cfg, plan, out):
    rows, topo = topology()
    inherited = sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{r['cpu'] for r in rows})
    cfg.update(batch=plan['batch'],point_timeout_seconds=1800,_use_noise_history=True)
    prior = [json.loads(p.read_text()) for p in out.glob('*/*/complete.json')]
    if prior: cfg['_preferred_cpu'] = max(prior,key=lambda d:d['finished'])['selected']['cpu']
    build = out/'build'; build.mkdir(parents=True,exist_ok=True); os.chdir(build)
    for name in ('cache_bench.c','followup_bench.c'): shutil.copy2(ROOT/'src'/name,build/name)
    flags = ['-O0','-g','-std=c11','-Wall','-Wextra','-Werror','-fno-omit-frame-pointer','-pthread']
    cc = shutil.which('gcc')
    command([cc,'--version'],build,'compiler')
    command([cc]+flags+['followup_bench.c','-o','followup_bench'],build,'compile')
    command([cc]+flags+['-S','followup_bench.c','-o','followup_bench.s'],build,'assembly')
    dis = command(['objdump','-d','followup_bench'],build,'objdump')
    (build/'followup_bench.dis').write_text(dis)
    excerpt = re.search(r'<chase>:\n(.*?)(?=\n\n)',dis,re.S)
    if not excerpt: raise RuntimeError('No dependent loop listing')
    text = excerpt.group(0)
    okay = ('ldr' in text and 'b.ne' in text) if platform.machine()=='aarch64' else ('mov' in text and 'jne' in text)
    if not okay: raise RuntimeError('Native loop pattern failed')
    (build/'critical-loop.txt').write_text(text)
    files = {str(p.relative_to(ROOT)):sha(p) for folder in ('src','scripts','config') for p in (ROOT/folder).glob('*') if p.is_file()}
    digest = hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
    prov = out/'provenance'/digest
    for path in files:
        dest=prov/path; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(ROOT/path,dest)
    write_json(prov/'manifest.json',dict(time=now(),files=files))
    source = hashlib.sha256((sha(build/'cache_bench.c')+sha(build/'followup_bench.c')).encode()).hexdigest()
    cfg.update(_benchmark_path=str(build/'followup_bench'),_source_digest=source,
               _provenance_manifest=str((prov/'manifest.json').relative_to(out)))
    env=out/('environment-'+str(time.time_ns())+'.json');cfg['_environment_record']=str(env.relative_to(out))
    write_json(env,dict(time=now(),host=host,isa=platform.machine(),kernel=platform.release(),python=platform.python_version(),
        inherited_affinity=inherited,available_affinity=sorted(os.sched_getaffinity(0)),topology=topo,
        config=cfg,plan=plan,compiler_flags=flags,binary_sha256=sha(build/'followup_bench'),loop_pattern_passed=okay))
    return rows


def execute(stage,out,cfg,rows,plan):
    results=[]
    def run(family,**params):
        d=point(family,arguments(cfg,**params),(out,cfg,rows,stage in ('smoke','repair_smoke')));results.append(d);return d
    def addresses(offsets):
        content='\n'.join(map(str,offsets))+'\n';digest=hashlib.sha256(content.encode()).hexdigest()
        path=out/'address-sets'/(digest+'.txt');path.parent.mkdir(exist_ok=True)
        if not path.exists():path.write_text(content)
        return dict(address_list=str(path),address_list_sha256=digest)
    def chain(stride,n,scrub,seed,variant,label,**extra):
        offsets=conflict_offsets(plan['l1_period'],stride,n,scrub,variant)
        return run('batched_conflict',bytes=max(4194304,max(offsets)+4096),stride=8,page='huge',seed=seed,
            conflict_stride=stride,candidate_count=n,scrub_count=scrub,variant=variant,series=label,
            nodes=len(offsets),**addresses(offsets),**extra)
    if stage=='smoke':
        run('smoke',mode='overhead')
        run('smoke',bytes=65536,page='huge')
        run('smoke',mode='spatial',bytes=65536,stride=256,align=24,offset=40,page='huge')
        chain(65536,5,plan['l1_ways']+2,cfg['seed']+901,1,'smoke')
        if any(d.get('status') not in ('passed','noisy') for d in results):raise RuntimeError('Functional smoke failed')
        write_json(out/'smoke-passed.json',dict(time=now(),source_sha256=cfg['_source_digest'],records=[d['attempt'] for d in results]))
    elif stage=='repair_smoke':
        for variant in (1,2):chain(65536,5,plan['l1_ways']+2,cfg['seed']+1601,variant,'repair-smoke')
        if any(d.get('status') not in ('passed','noisy') for d in results):raise RuntimeError('Repair smoke failed')
        write_json(out/'repair-smoke-passed.json',dict(time=now(),source_sha256=cfg['_source_digest'],records=[d['attempt'] for d in results]))
    elif stage=='controls':
        timer=run('timer',mode='overhead');hot=run('timer',bytes=1024)
        if 'statistics' not in timer or 'statistics' not in hot:raise RuntimeError('Timer control failed')
        ratio=timer['statistics']['median']/(hot['statistics']['median']*cfg['batch'])
        passed=timer['status']==hot['status']=='passed' and ratio<=.05
        write_json(out/'timer-gate.json',dict(time=now(),passed=passed,fraction=ratio,limit=.05,
            sources=[timer['attempt'],hot['attempt']],note='Unsubtracted native timer units; batch amortizes overhead'))
        if not passed:raise RuntimeError('Timer overhead/quality gate failed')
    elif stage=='conflict':
        if not plan['conflict_required']:
            write_json(out/'conflict-not-required.json',dict(reason='Existing repeated capacity-consistent L2 candidate; targeted new method applies to Crux and Thunderbird'))
        else:
            discoveries=[]
            for scrub in (0,plan['l1_ways']+2):
                for stride in plan['conflict_strides']:
                    counts=plan['conflict_counts'][:];random.Random(cfg['seed']+scrub+stride).shuffle(counts)
                    records=[chain(stride,n,scrub,cfg['seed']+901,1,'discovery') for n in counts]
                    edges=detected_edges(records,'candidate_count')
                    discoveries.append(dict(stride=stride,scrub=scrub,edges=edges,records=[r.get('attempt') for r in records]))
            write_json(out/'conflict-refinement-plan.json',dict(time=now(),discoveries=discoveries,
                rule='Every clean same-core adjacent >15% median increase with disjoint IQRs; repeat the entire integer interval and its neighbors in two new seeds and two scrub patterns. No edge means no forced candidate.'))
            for discovery in discoveries:
                counts=sorted({n for lo,hi in discovery['edges'] for n in range(max(2,lo-1),hi+2)})
                for variant in ((1,2) if discovery['scrub'] else (1,)):
                    for seed in (cfg['seed']+1001,cfg['seed']+1101):
                        order=counts[:];random.Random(seed+variant).shuffle(order)
                        for n in order:chain(discovery['stride'],n,discovery['scrub'],seed,variant,'heldout')
    elif stage=='repair':
        previous=json.loads((out/'conflict-refinement-plan.json').read_text())
        repairs=[];confirmations=[]
        for discovery in previous['discoveries']:
            originals=[json.loads((out/ref/'run.json').read_text()) for ref in discovery['records']]
            pairs=blocked_pairs(originals)
            for interval in pairs:
                attempts=[];accepted=[]
                for repetition in range(3):
                    order=interval[:];random.Random(cfg['seed']+1601+repetition).shuffle(order)
                    group=[chain(discovery['stride'],n,discovery['scrub'],cfg['seed']+1601,1,'discovery-repair',
                        repair_interval=interval,repair_repetition=repetition) for n in order]
                    clean=all(d.get('status')=='passed' for d in group) and len({d.get('selected',{}).get('cpu') for d in group})==1
                    attempts.append(dict(records=[d.get('attempt') for d in group],same_core_clean=clean))
                    if clean:accepted=group;break
                edges=detected_edges(accepted,'candidate_count') if accepted else []
                repairs.append(dict(stride=discovery['stride'],scrub=discovery['scrub'],interval=interval,
                    attempts=attempts,accepted_records=[d['attempt'] for d in accepted],edges=edges))
                for lo,hi in edges:
                    counts=list(range(max(2,lo-1),hi+2))
                    for variant in ((1,2) if discovery['scrub'] else (1,)):
                        for seed in (cfg['seed']+1801,cfg['seed']+1901):
                            cohorts=[];selected=[]
                            for repetition in range(3):
                                order=counts[:];random.Random(seed+variant+repetition).shuffle(order)
                                group=[chain(discovery['stride'],n,discovery['scrub'],seed,variant,'repair-heldout',
                                    repair_interval=[lo,hi],repair_repetition=repetition) for n in order]
                                clean=all(d.get('status')=='passed' for d in group) and len({d.get('selected',{}).get('cpu') for d in group})==1
                                cohorts.append(dict(records=[d.get('attempt') for d in group],same_core_clean=clean))
                                if clean:selected=group;break
                            confirmations.append(dict(stride=discovery['stride'],scrub=discovery['scrub'],interval=[lo,hi],
                                variant=variant,seed=seed,counts=counts,attempts=cohorts,accepted_records=[d['attempt'] for d in selected]))
                write_json(out/'conflict-repair.json',dict(time=now(),repairs=repairs,confirmations=confirmations,
                    rule='All coarse adjacent pairs with noise or core mismatch are remeasured, regardless of direction/effect. First clean same-core cohort of at most three retained attempts; refine every qualifying repaired edge in new seeds/patterns.'))
        write_json(out/'conflict-repair.json',dict(time=now(),repairs=repairs,confirmations=confirmations,
            rule='All coarse adjacent pairs with noise or core mismatch are remeasured, regardless of direction/effect. First clean same-core cohort of at most three retained attempts; refine every qualifying repaired edge in new seeds/patterns.'))
    elif stage=='capacity_repair':
        groups={}
        for directory in sorted(out.glob('capacity_repeat/*')):
            file=directory/('complete.json' if (directory/'complete.json').exists() else 'unresolved.json')
            if not file.exists():continue
            d=json.loads(file.read_text());p=d['parameters'];groups.setdefault((p['page'],p['seed']),[]).append(d)
        targets=[dict(page=page,seed=seed,interval=pair) for (page,seed),g in sorted(groups.items()) for pair in clean_cross_core_pairs(g)]
        write_json(out/'capacity-matched-plan.json',dict(time=now(),targets=targets,
            rule='Every adjacent original capacity pair whose individual runs passed but CPUs differ, regardless of effect. Noise-only pairs already exhausted ordinary retries and remain flagged.'))
        cohorts=[]
        for target in targets:
            def cohort(counts,label):
                attempts=[];accepted=[]
                for repetition in range(3):
                    order=counts[:];random.Random(target['seed']+repetition).shuffle(order)
                    group=[run('capacity_matched',bytes=w,stride=64,page=target['page'],seed=target['seed'],
                        series=label,repair_interval=target['interval'],repair_repetition=repetition) for w in order]
                    clean=all(d.get('status')=='passed' for d in group) and len({d.get('selected',{}).get('cpu') for d in group})==1
                    attempts.append(dict(records=[d.get('attempt') for d in group],same_core_clean=clean))
                    if clean:accepted=group;break
                result=dict(**target,series=label,counts=counts,attempts=attempts,accepted_records=[d['attempt'] for d in accepted])
                cohorts.append(result)
                return accepted
            accepted=cohort(target['interval'],'matched-pair')
            if detected_edges(accepted,'bytes'):
                lo,hi=target['interval'];counts=sorted({((lo+(hi-lo)*i//4)//64)*64 for i in range(5)})
                cohort(counts,'matched-refinement')
            write_json(out/'capacity-matched.json',dict(time=now(),cohorts=cohorts))
        write_json(out/'capacity-matched.json',dict(time=now(),cohorts=cohorts))
    elif stage=='capacity':
        if plan['capacity_interval']:
            lo,hi=plan['capacity_interval'];grid=sorted(set([lo//2,hi*2]+[lo+(hi-lo)*i//8 for i in range(9)]))
            for page in ('huge','base'):
                for seed in (cfg['seed']+1201,cfg['seed']+1301):
                    order=grid[:];random.Random(seed).shuffle(order)
                    records=[run('capacity_repeat',bytes=w,stride=64,page=page,seed=seed,series='grid') for w in order]
                    edges=detected_edges(records,'bytes')
                    write_json(out/('capacity-plan-'+page+'-'+str(seed)+'.json'),dict(time=now(),edges=edges,grid=grid,
                        sources=[r.get('attempt') for r in records],rule='Three interior points in every same-core clean >15% IQR-separated interval'))
                    refined=sorted({((a+(b-a)*i//4)//64)*64 for a,b in edges for i in (1,2,3)}-set(grid))
                    random.Random(seed+1).shuffle(refined)
                    for w in refined:run('capacity_repeat',bytes=w,stride=64,page=page,seed=seed,series='refined')
                    for w in (lo,hi):run('capacity_regular_repeat',bytes=w,stride=64,page=page,seed=seed,order='regular')
    elif stage=='spatial':
        cohorts=[]
        for footprint in plan['spatial_allocations']:
            for align in (0,24):
                for seed in (cfg['seed']+1401,cfg['seed']+1501):
                    attempts=[]
                    for repetition in range(2):
                        offsets=[64-align-8,64-align,64-align+8];random.Random(seed+repetition).shuffle(offsets)
                        records=[run('spatial_residency',mode='spatial',bytes=footprint,stride=256,page='huge',align=align,
                            offset=offset,seed=seed,cohort_repetition=repetition) for offset in offsets]
                        okay=all(d.get('status')=='passed' for d in records) and len({d['selected']['cpu'] for d in records if 'selected' in d})==1
                        attempts.append(dict(records=[d.get('attempt') for d in records],same_core_clean=okay))
                        if okay:break
                    cohorts.append(dict(bytes=footprint,align=align,seed=seed,attempts=attempts))
        write_json(out/'spatial-cohorts.json',dict(time=now(),cohorts=cohorts,
            limitation='Allocation is not cache occupancy: pairs spaced 256 B occupy approximately allocation/4 below and allocation/2 above a 64 B boundary, conditional on that candidate. Residency is an experimental hypothesis, not an independently isolated cache level.'))
    else:raise ValueError(stage)
    write_json(out/(stage+'-finished.json'),dict(time=now(),stage=stage,records=[d.get('attempt') for d in results],
        points=len(results),passed=sum(d.get('status')=='passed' for d in results),noisy=sum(d.get('status')=='noisy' for d in results),
        failed=sum(d.get('status') not in ('passed','noisy') for d in results)))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['smoke','controls','conflict','capacity','spatial','repair_smoke','repair','capacity_repair']);args=ap.parse_args()
    cfg=json.loads((ROOT/'config/phase1.json').read_text());host=platform.node().split('.')[0]
    if host not in cfg['hosts']:raise SystemExit('Only assigned lab hosts')
    lock=open(ROOT/'uncertainty.lock','w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    out=ROOT/'machines'/host/ROUND;out.mkdir(parents=True,exist_ok=True)
    plan=json.loads((ROOT/'config/uncertainty-plan.json').read_text())['hosts'][host]
    rows=setup(host,cfg,plan,out)
    if args.stage!='smoke':
        gate=out/'smoke-passed.json'
        if not gate.exists() or json.loads(gate.read_text())['source_sha256']!=cfg['_source_digest']:raise SystemExit('Exact-source smoke required')
    if args.stage not in ('smoke','controls'):
        if not json.loads((out/'timer-gate.json').read_text())['passed']:raise SystemExit('Timer gate required')
    if args.stage=='repair':
        gate=out/'repair-smoke-passed.json'
        if not gate.exists() or json.loads(gate.read_text())['source_sha256']!=cfg['_source_digest']:raise SystemExit('Repair smoke required')
    execute(args.stage,out,cfg,rows,plan)

if __name__=='__main__':main()
