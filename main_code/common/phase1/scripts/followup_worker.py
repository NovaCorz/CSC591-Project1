#!/usr/bin/env python3
"""Second-round, timing-only experiments. Each discovery point also has 1e6 samples."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import shutil
import time
from common import now, read_raw, sha, topology, write_json
from worker import ROOT, command, parameters, point


def arguments(cfg, **changes):
    p=parameters(cfg, **changes)
    p.setdefault('align',0);p.setdefault('page','base');p.setdefault('address_list','-')
    p['extra_args']=[p['align'],p['page'],p['address_list'],-1]
    if p['mode'] in ('probe','hot','cross','overhead'):p['timed_loads']=1
    if p['mode']=='cross':p['paired_core']=True
    return p


def run_stage(stage,out,cfg,rows,plan):
    context=out,cfg,rows,False
    rng=random.Random(cfg['seed'])
    results=[]
    def run(family,**kw):
        d=point(family,arguments(cfg,**kw),context);results.append(d);return d
    if stage=='spatial':
        # 24 B shifts a candidate 64 B boundary to an offset near 40 B;
        # it is an alignment perturbation, not a cache-size input.
        for footprint in plan['spatial_footprints']:
            for align in (0,24):
                offsets=list(range(8,137,8));rng.shuffle(offsets)
                for offset in offsets:
                    run('spatial_alignment',mode='spatial',bytes=footprint,stride=512,
                        offset=offset,align=align,seed=cfg['seed']+align)
    elif stage=='capacity':
        sizes=[1024*2**i for i in range(19)]
        coarse={}
        for page,stride in [('base',8),('huge',8),('huge',plan['spatial_candidate'])]:
            shuffled=sizes[:];rng.shuffle(shuffled)
            records=[run('capacity_control',bytes=w,page=page,stride=stride) for w in shuffled]
            coarse[page+str(stride)]=records
        # Candidate-specific refinement chosen from this round's THP sparse
        # curve, without physical-level or vendor answers. Keep all candidates.
        records=sorted([r for r in coarse['huge'+str(plan['spatial_candidate'])]
                        if r.get('status')=='passed'],key=lambda r:r['parameters']['bytes'])
        edges=[]
        for a,b in zip(records,records[1:]):
            lo,hi=a['parameters']['bytes'],b['parameters']['bytes']
            if hi==2*lo and b['statistics']['median']>1.20*a['statistics']['median']:
                edges.append([lo,hi])
        write_json(out/'capacity-refinement-plan.json',dict(time=now(),edges=edges,
            rule='Every adjacent doubled-footprint sparse THP median increase >20%; seven interior points'))
        for lo,hi in edges:
            for page in ('base','huge'):
                local=[lo+(hi-lo)*i//8 for i in range(9)];rng.shuffle(local)
                for w in local:
                    run('capacity_refinement',bytes=w,page=page,stride=plan['spatial_candidate'],
                        comparison_interval=[lo,hi])
            # Regular traversal supplies the matching prefetch diagnostic.
            for w in (lo,hi):run('capacity_regular',bytes=w,page='huge',stride=plan['spatial_candidate'],order='regular')
    elif stage=='conflict':
        smoke=out/'conflict-smoke';smoke.mkdir(exist_ok=True)
        listing=out/'smoke-addresses.txt';listing.write_text('4096\n8192\n12288\n')
        scfg=dict(cfg,_environment_record='../'+cfg['_environment_record'],_provenance_manifest='../'+cfg['_provenance_manifest'])
        tests=[point('address_list',arguments(cfg,mode=mode,bytes=65536,stride=4096,
                 address_list=str(listing),batch=6,page='huge'),(smoke,scfg,rows,True)) for mode in ('hot','probe')]
        if any(r.get('status') not in ('passed','noisy') for r in tests):raise RuntimeError('Address-list smoke failed')
        write_json(out/'conflict-smoke-passed.json',dict(time=now(),points=len(tests)))
        conflict_stage(run,out,cfg,plan)
    elif stage=='confirm':
        timer=run('followup_overhead',mode='overhead')
        hot=run('followup_hot_batch',bytes=1024)
        ratio=timer.get('statistics',{}).get('median',float('inf'))/(hot.get('statistics',{}).get('median',1)*cfg['batch'])
        write_json(out/'timer-verification.json',dict(time=now(),batch=cfg['batch'],overhead_fraction=ratio,
            passed=timer.get('status')=='passed' and hot.get('status')=='passed' and ratio<=.05,
            sources=[timer.get('attempt'),hot.get('attempt')],note='Raw data remain unsubtracted; this checks the retained primary batch for the extension kernel'))
        cohorts=[]
        candidate=plan['spatial_candidate']
        for w in plan['spatial_footprints']:
            for align in (0,24,40):
                for seed in (cfg['seed']+303,cfg['seed']+404):
                    attempts=[]
                    for repetition in range(3):
                        offsets=[candidate-align-8,candidate-align,candidate-align+8]
                        rng.shuffle(offsets)
                        group=[run('spatial_confirmation',mode='spatial',bytes=w,stride=512,
                            offset=offset,align=align,seed=seed,cohort_repetition=repetition) for offset in offsets]
                        good=all(r.get('status')=='passed' for r in group)
                        cpus={r.get('selected',{}).get('cpu') for r in group}
                        attempts.append(dict(records=[r.get('attempt') for r in group],cpus=sorted(c for c in cpus if c is not None),
                            same_core=len(cpus)==1 and None not in cpus,all_clean=good))
                        if good and len(cpus)==1:break
                    cohorts.append(dict(bytes=w,align=align,seed=seed,attempts=attempts,
                        accepted=good and len(cpus)==1))
        write_json(out/'spatial-cohorts.json',dict(time=now(),cohorts=cohorts,
            rule='First complete clean same-core triplet, at most three retained group attempts; never select by latency'))
    elif stage=='cross':
        # Warm the target ONLY on the measuring core; helper pressure addresses
        # never contain the target. Matched handshake-only controls quantify
        # synchronization traffic. This tests remote-pressure behavior, not a
        # guaranteed lower-only eviction unless independent controls support it.
        for w in plan['cross_footprints']:
            for pressure in (0,1):
                for seed in (cfg['seed'],cfg['seed']+1):
                    run('cross_core_reload',mode='cross',bytes=w,stride=plan['spatial_candidate'],
                        offset=pressure,batch=1024,page='huge',seed=seed)
            run('same_core_reload',mode='probe',bytes=w,stride=plan['spatial_candidate'],batch=1024,page='huge')
        run('target_hot',mode='hot')
    elif stage=='l2':
        l2_stage(run,out,cfg,rows,plan)
    elif stage=='l2confirm':
        lower_confirmation_stage(run,out,cfg,plan)
    else:raise ValueError(stage)
    write_json(out/(stage+'-finished.json'),dict(time=now(),stage=stage,points=len(results),
        passed=sum(r.get('status')=='passed' for r in results),
        noisy=sum(r.get('status')=='noisy' for r in results),
        failed=sum(r.get('status') not in ('passed','noisy') for r in results)))


def conflict_stage(run,out,cfg,plan):
    # Discover target-evicting virtual offset sets by chunk deletion. This is
    # exploratory training; separately seeded, newly mapped validation follows.
    # A new mapping can change physical congruence, so repeatability is mandatory
    # and LLC geometry is never equated to the size of a selected set.
    root=out/'address-sets';root.mkdir(exist_ok=True)
    searches=[]
    def center(record):
        s=record['statistics'];return (s['q1']+s['median']+s['q3'])/3
    for stride,pool in ((4096,64),(16384,96),(65536,128)):
        offsets=[stride*i for i in range(1,pool+1)]
        allocation=(pool+1)*stride
        rng=random.Random(cfg['seed']+stride);rng.shuffle(offsets)
        def measure(addresses,label,seed=cfg['seed'],mode='probe'):
            content='\n'.join(map(str,addresses))+'\n'
            digest=hashlib.sha256(content.encode()).hexdigest()
            file=root/(digest+'.txt')
            if not file.exists():file.write_text(content)
            return run('empirical_conflict',mode=mode,bytes=allocation,stride=stride,
                page='huge',batch=max(2,2*len(addresses)),seed=seed,address_list=str(file),
                address_list_sha256=digest,search_stride=stride,search_label=label,
                candidate_count=len(addresses))
        hot=measure(offsets,'hot-calibration',mode='hot')
        full=measure(offsets,'full-pool')
        search=dict(stride=stride,pool_count=pool,allocation_bytes=allocation,
            note='Virtual offsets are remapped per run. Discovery is training; held-out seed/mapping results determine repeatability. Selected set size is an effective eviction bound, not automatically cache ways.',
            hot_attempt=hot.get('attempt'),full_attempt=full.get('attempt'),trials=[])
        if hot.get('status')!='passed' or full.get('status')!='passed':
            search['status']='unresolved: noisy/failed calibration';searches.append(search);continue
        floor,ceiling=center(hot),center(full)
        search.update(hot_center=floor,full_center=ceiling)
        if ceiling-floor<max(.25,.10*floor):
            search['status']='unresolved: no sufficiently separated target-reload class';searches.append(search);continue
        threshold=floor+.75*(ceiling-floor);search['training_threshold']=threshold
        chosen=offsets[:];budget=36;chunk=max(1,len(chosen)//4)
        while chunk>=1 and budget:
            changed=False
            for start in range(0,len(chosen),chunk):
                proposal=chosen[:start]+chosen[start+chunk:]
                if not proposal:continue
                d=measure(proposal,'deletion-training');budget-=1
                accepted=d.get('status')=='passed' and center(d)>=threshold
                search['trials'].append(dict(address_count=len(proposal),attempt=d.get('attempt'),
                    status=d.get('status'),accepted=accepted,center=center(d) if 'statistics' in d else None))
                if accepted:chosen=proposal;changed=True;break
                if not budget:break
            if not changed:chunk//=2
        search['selected_offsets']=chosen;search['training_budget_exhausted']=budget==0
        validation=[]
        # Reproduce the full selected set and each of up to 32 independent
        # single-address deletions with two new permutation seeds/mappings.
        for seed in (cfg['seed']+101,cfg['seed']+202):
            r=measure(chosen,'heldout-full',seed);validation.append(dict(kind='full',seed=seed,record=r))
            r=measure(chosen,'heldout-hot',seed,mode='hot');validation.append(dict(kind='hot',seed=seed,record=r))
            for i in range(min(32,len(chosen))):
                if len(chosen)<=1:break
                r=measure(chosen[:i]+chosen[i+1:],'heldout-delete-'+str(i),seed)
                validation.append(dict(kind='delete',removed=chosen[i],seed=seed,record=r))
        search['validation']=validation;search['status']='discovery and held-out measurements collected; interpretation gated by raw verification'
        searches.append(search)
        write_json(out/'empirical-search.json',dict(time=now(),searches=searches))
    write_json(out/'empirical-search.json',dict(time=now(),searches=searches))


def lower_parameter_factory(out,period,scrub_n):
    allocation=134217728;origin=2097152
    directory=out/'address-sets';directory.mkdir(exist_ok=True)
    def params(stride,n,seed,variant=1,scrub=scrub_n,mode='probe',label='coarse'):
        fixed=[((2 if variant==1 else 4)*i+1)*period for i in range(scrub)]
        candidates=[origin+(i+1)*stride for i in range(n)]
        assert not set(fixed)&set(candidates) and 0 not in fixed+candidates
        assert all(v+8<allocation for v in fixed+candidates)
        content='\n'.join(map(str,fixed+candidates))+'\n';digest=hashlib.sha256(content.encode()).hexdigest()
        path=directory/(digest+'.txt')
        if not path.exists():path.write_text(content)
        return dict(mode=mode,bytes=allocation,stride=period,page='huge',batch=2*(scrub+n),seed=seed,
            address_list=str(path),address_list_sha256=digest,l2_candidate_stride=stride,l2_candidate_count=n,
            upper_scrub_count=scrub,upper_scrub_period=period,upper_scrub_variant=variant,l2_label=label,
            index_hypothesis='Fixed odd multiples of L1 candidate period versus target/lower-candidate next index bit zero')
    return params


def l2_stage(run,out,cfg,rows,plan):
    """Hold upper-level eviction pressure constant while scanning lower candidates.

    Odd multiples of the timing-derived L1 indexing period share its low index
    bits with T, while differing in the next bit from T and all lower candidates.
    This is a tested virtual-index hypothesis, not knowledge of physical indexing.
    Different odd scrub patterns and new seeds provide independent confirmation.
    """
    period=plan['l1_tested_period'];ways=plan['l1_ways_candidate'];scrub_n=ways+2
    allocation=134217728;origin=2097152
    params=lower_parameter_factory(out,period,scrub_n)
    smoke=out/'l2-smoke';smoke.mkdir(exist_ok=True)
    scfg=dict(cfg,_environment_record='../'+cfg['_environment_record'],_provenance_manifest='../'+cfg['_provenance_manifest'])
    checks=[point('composite_pressure',arguments(cfg,**params(period*4,n,cfg['seed'],label='functional')),
            (smoke,scfg,rows,True)) for n in (0,4)]
    if any(d.get('status') not in ('passed','noisy') for d in checks):raise RuntimeError('Composite L1-scrub / L2-candidate smoke failed')
    write_json(out/'l2-smoke-passed.json',dict(time=now(),points=2,source_sha256=cfg['_source_digest']))
    def measure(stride,n,seed,variant=1,scrub=scrub_n,mode='probe',label='coarse'):
        return run('l2_upper_calibration' if label=='upper-calibration' else 'l2_conflict',
                   **params(stride,n,seed,variant,scrub,mode,label))
    calibration=[measure(period*4,0,cfg['seed'],mode='hot',label='upper-calibration')]
    calibration += [measure(period*4,0,cfg['seed'],scrub=s,label='upper-calibration') for s in sorted({1,max(1,ways-1),ways,ways+2,ways+4})]
    def center(d):
        if 'raw' not in d:return None
        v=read_raw(out/d['raw'],d['measurement']['little_endian']);block=max(1,len(v)//10)
        means=[sum(v[i:i+block])/len(v[i:i+block]) for i in range(0,len(v),block)]
        values=sorted(means);return dict(center=(values[4]+values[5])/2,range=[min(means),max(means)],block_means=means)
    counts=[0]+list(range(2,33,2))+[48,64]
    strides=[period*4,period*16,period*64];coarse={};edges={};rng=random.Random(cfg['seed']+909)
    def sweep(stride):
        order=counts[:];rng.shuffle(order)
        records=[measure(stride,n,cfg['seed']) for n in order]
        scored=[dict(n=d['parameters']['l2_candidate_count'],score=center(d),record=d.get('attempt'),status=d.get('status')) for d in records]
        scored.sort(key=lambda d:d['n']);coarse[str(stride)]=scored
        clean=[d for d in scored if d['status']=='passed' and d['score']]
        candidates=[]
        for a,b in zip(clean,clean[1:]):
            sa,sb=a['score'],b['score']
            if sb['center']>1.05*sa['center'] and sb['range'][0]>sa['range'][1]:
                candidates.append(dict(lower_n=a['n'],upper_n=b['n'],sources=[a['record'],b['record']]))
        edges[str(stride)]=candidates
    for stride in strides:sweep(stride)
    # Refine the prospective indexing periods from measured capacity and observed
    # conflict response, including a smaller harmonic that a coarse stride misses.
    boundaries=json.loads((out/'capacity-refinement-plan.json').read_text())['edges']
    lower_candidates=[lo for lo,hi in boundaries if lo>2*plan['l1_capacity_interval'][1]]
    first_thresholds=[v[0]['upper_n'] for v in edges.values() if v]
    extras=[]
    if lower_candidates and first_thresholds:
        ratio=min(lower_candidates)/min(first_thresholds)
        low=2**max(0,int(__import__('math').floor(__import__('math').log2(ratio))))
        extras=[s for s in (low,2*low) if s>=2*period and s<=1048576 and s not in strides]
    for stride in extras:sweep(stride)
    refinement=[]
    for stride_text,candidates in edges.items():
        if not candidates:continue
        # The first stable transition above the calibrated upper-miss class is
        # investigated, rather than interpreting every higher transition as ways.
        edge=candidates[0];stride=int(stride_text)
        local=list(range(max(0,edge['lower_n']-1),edge['upper_n']+2))
        for variant in (1,2):
            for seed in (cfg['seed']+505,cfg['seed']+606):
                order=local[:];rng.shuffle(order)
                records=[measure(stride,n,seed,variant=variant,label='heldout-refinement') for n in order]
                refinement.append(dict(stride=stride,variant=variant,seed=seed,counts=local,records=[d.get('attempt') for d in records]))
    write_json(out/'l2-search.json',dict(time=now(),allocation_bytes=allocation,l1_period=period,l1_ways=ways,
        fixed_scrub_count=scrub_n,calibration_records=[d.get('attempt') for d in calibration],
        coarse_counts=counts,initial_strides=strides,additional_strides=extras,coarse=coarse,candidate_edges=edges,refinements=refinement,
        note='Fixed upper scrub and lower candidate addresses differ in the next virtual index bit. Separate calibration, two scrub patterns, two new seeds and recorded huge backing test this hypothesis. Counts remain effective thresholds unless independent capacity/indexing consistency supports a conditional way count.'))


def lower_confirmation_stage(run,out,cfg,plan):
    """Prospective saturation calibration and a bounded stronger-scrub repeat."""
    period=plan['l1_tested_period'];ways=plan['l1_ways_candidate']
    params=lower_parameter_factory(out,period,ways+4)
    def measure(stride,n,scrub,seed,variant,label,repetition=0):
        p=params(stride,n,seed,variant,scrub,label=label)
        p['calibration_repetition']=repetition
        return run('l2_saturation' if label!='strong-heldout' else 'l2_strong_conflict',**p)
    def score(d):
        values=read_raw(out/d['raw'],d['measurement']['little_endian']);block=len(values)//10
        means=sorted(sum(values[i:i+block])/len(values[i:i+block]) for i in range(0,len(values),block))
        return (means[4]+means[5])/2
    counts=sorted({1,ways,ways+2,ways+4,ways+6,ways+8,ways+12})
    cohorts=[];selected=None
    for repetition in range(3):
        group=[measure(period*4,0,s,cfg['seed']+707,1,'saturation-search',repetition) for s in counts]
        clean=all(d.get('status')=='passed' for d in group) and len({d.get('selected',{}).get('cpu') for d in group})==1
        scores=[score(d) if d.get('raw') else None for d in group]
        cohorts.append(dict(records=[d.get('attempt') for d in group],same_core_clean=clean,centers=scores,counts=counts))
        if clean:
            for i in range(1,len(counts)-2):
                centers=scores[i:i+3]
                if min(centers)>1.05*scores[0] and max(centers)/min(centers)<=1.10:
                    selected=counts[i];break
            break
    previous=json.loads((out/'l2-search.json').read_text());refinements=[];calibrations=[]
    if selected is not None:
        rng=random.Random(cfg['seed']+1101)
        for variant in (1,2):
            for seed in (cfg['seed']+707,cfg['seed']+808):
                attempts=[]
                for repetition in range(3):
                    group=[measure(period*4,0,s,seed,variant,'saturation-confirmation',repetition) for s in (1,selected,selected+4)]
                    clean=all(d.get('status')=='passed' for d in group) and len({d.get('selected',{}).get('cpu') for d in group})==1
                    attempts.append(dict(records=[d.get('attempt') for d in group],same_core_clean=clean))
                    if clean:break
                calibrations.append(dict(variant=variant,seed=seed,attempts=attempts))
        for stride_text,edges in previous['candidate_edges'].items():
            if not edges:continue
            edge=edges[0];stride=int(stride_text)
            local=list(range(max(0,edge['lower_n']-1),edge['upper_n']+2))
            for variant in (1,2):
                for seed in (cfg['seed']+707,cfg['seed']+808):
                    attempts=[]
                    for repetition in range(3):
                        order=local[:];rng.shuffle(order)
                        group=[measure(stride,n,selected,seed,variant,'strong-heldout',repetition) for n in order]
                        clean=all(d.get('status')=='passed' for d in group) and len({d.get('selected',{}).get('cpu') for d in group})==1
                        attempts.append(dict(records=[d.get('attempt') for d in group],same_core_clean=clean))
                        if clean:break
                    refinements.append(dict(stride=stride,variant=variant,seed=seed,counts=local,records=[d.get('attempt') for d in group],attempts=attempts))
    previous_plan=out/'l2-confirmation.json'
    if previous_plan.exists():
        history=out/'plan-history';history.mkdir(exist_ok=True)
        shutil.copy2(previous_plan,history/('l2-confirmation-'+sha(previous_plan)+'.json'))
    write_json(out/'l2-confirmation.json',dict(time=now(),selected_scrub_count=selected,search_cohorts=cohorts,
        calibrations=calibrations,refinements=refinements,
        rule='First same-core clean saturation scan, at most three acquisition attempts; first three consecutive tested scrub counts within 10 percent of each other and all above one-address control by 5 percent. Confirm selected count versus one and selected+4 with two patterns and two seeds, then repeat prior discovery intervals. Each refined group uses the first clean acquisition entirely on one core, at most three retained group attempts. No stable scan means no supported upper scrub; all attempts retained.'))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['smoke','spatial','capacity','conflict','cross','confirm','l2','l2confirm']);args=ap.parse_args()
    cfg=json.loads((ROOT/'config/phase1.json').read_text());host=platform.node().split('.')[0]
    if host not in cfg['hosts']:raise SystemExit('Only the eight assigned lab hosts are allowed')
    lock=open(ROOT/'followup.lock','w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    rows,topo=topology();inherited=sorted(os.sched_getaffinity(0));os.sched_setaffinity(0,{r['cpu'] for r in rows})
    plan=json.loads((ROOT/'config/followup-plan.json').read_text())['hosts'][host]
    cfg['batch']=plan['batch'];cfg['point_timeout_seconds']=1800;cfg['_use_noise_history']=True
    out=ROOT/'machines'/host/'followup-v1';out.mkdir(parents=True,exist_ok=True)
    prior_clean=[]
    for file in out.glob('*/*/complete.json'):
        previous=json.loads(file.read_text())
        if previous.get('status')=='passed':prior_clean.append(previous)
    if prior_clean:
        latest=max(prior_clean,key=lambda d:d.get('finished',''))
        cfg['_preferred_cpu']=latest['selected']['cpu']
        cfg['_preferred_cpu_reason']='Most recent quality-passing acquisition, not fastest latency; idle windows still required'
    build=out/'build';build.mkdir(exist_ok=True);os.chdir(build)
    for name in ('cache_bench.c','followup_bench.c'):shutil.copy2(ROOT/'src'/name,build/name)
    flags=['-O0','-g','-std=c11','-Wall','-Wextra','-Werror','-fno-omit-frame-pointer','-pthread']
    cc=shutil.which('gcc');command([cc,'--version'],build,'compiler')
    command([cc]+flags+['followup_bench.c','-o','followup_bench'],build,'compile')
    command([cc]+flags+['-S','followup_bench.c','-o','followup_bench.s'],build,'assembly')
    dis=command(['objdump','-d','followup_bench'],build,'objdump');(build/'followup_bench.dis').write_text(dis)
    sources={str(p.relative_to(ROOT)):sha(p) for folder in ('src','scripts','config') for p in (ROOT/folder).glob('*') if p.is_file()}
    digest=hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest()
    provenance=out/'provenance'/digest;provenance.mkdir(parents=True,exist_ok=True)
    for path in sources:
        dest=provenance/path;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/path,dest)
    write_json(provenance/'manifest.json',dict(time=now(),files=sources))
    source_digest=hashlib.sha256((sha(build/'cache_bench.c')+sha(build/'followup_bench.c')).encode()).hexdigest()
    cfg.update(_benchmark_path=str(build/'followup_bench'),_source_digest=source_digest,
               _provenance_manifest=str((provenance/'manifest.json').relative_to(out)))
    env=out/('environment-'+str(time.time_ns())+'.json')
    cfg['_environment_record']=str(env.relative_to(out))
    write_json(env,dict(time=now(),host=host,isa=platform.machine(),python=platform.python_version(),
        inherited_affinity=inherited,available_affinity=sorted(os.sched_getaffinity(0)),topology=topo,
        config=cfg,plan=plan,binary_sha256=sha(build/'followup_bench'),compiler_flags=flags))
    if args.stage=='smoke':
        smoke=out/'smoke';smoke.mkdir(exist_ok=True)
        scfg=dict(cfg,_environment_record='../'+str(env.relative_to(out)),_provenance_manifest='../'+cfg['_provenance_manifest'])
        cases=[dict(mode='overhead'),dict(mode='chase',bytes=65536),
               dict(mode='spatial',bytes=65536,stride=512,align=24,offset=40),
               dict(mode='chase',bytes=65536,page='huge'),dict(mode='hot'),
               dict(mode='probe',bytes=65536,batch=32),
               dict(mode='cross',bytes=65536,batch=32,offset=0),
               dict(mode='cross',bytes=65536,batch=32,offset=1)]
        records=[point('functional',arguments(cfg,**case),(smoke,scfg,rows,True)) for case in cases]
        if any(r.get('status') not in ('passed','noisy') for r in records):raise SystemExit('Follow-up smoke failed; attempts retained')
        write_json(out/'smoke-passed.json',dict(time=now(),source_sha256=source_digest,points=len(records)))
    else:
        gate=out/'smoke-passed.json'
        if not gate.exists() or json.loads(gate.read_text())['source_sha256']!=source_digest:raise SystemExit('Exact-source smoke gate required')
        run_stage(args.stage,out,cfg,rows,plan)

if __name__=='__main__':main()
