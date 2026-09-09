#!/usr/bin/env python3
"""Verify all supplemental data; report effective transitions without cache answers."""
import argparse
import collections
import concurrent.futures
import csv
import itertools
import json
import time
from pathlib import Path
from analyze_followup import verify
from common import now,sha,write_json

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data_processed/uncertainty'


def snapshot_inputs(hosts):
    paths=set()
    for host in hosts:
        root=ROOT/'machines'/host/'uncertainty-v1'
        paths.update(root.glob('*.json'))
        paths.update(root.glob('*/*/attempt-*/run.json'))
        paths.update(root.glob('*/*/attempt-*/idle.json'))
        paths.update(root.glob('provenance/*/manifest.json'))
    return {str(p.relative_to(ROOT)):sha(p) for p in sorted(paths)}


def huge(d):
    m=d['measurement']
    return min(m['anon_huge_before_kib'],m['anon_huge_after_kib'])*1024>=m['mapped_bytes']


def edges(group,axis):
    chosen={}
    for d in sorted(group,key=lambda r:r['started']):chosen.setdefault(d['parameters'][axis],d)
    rows=[chosen[k] for k in sorted(chosen)];result=[]
    for a,b in zip(rows,rows[1:]):
        pa,pb=a['parameters'],b['parameters'];sa,sb=a['statistics'],b['statistics']
        clean=a['qualification']==b['qualification']=='clean'
        same=a['selected']['cpu']==b['selected']['cpu']
        backing=all(d['parameters']['page']!='huge' or huge(d) for d in (a,b))
        ratio=sb['median']/sa['median'] if sa['median'] else 0
        if ratio>1.15 and sb['q1']>sa['q3']:
            result.append(dict(interval=[pa[axis],pb[axis]],ratio=ratio,clean=clean,same_cpu=same,
                backing_verified=backing,qualified=clean and same and backing,
                sources=[a['record_path'],b['record_path']]))
    return result


def spatial(rows,root):
    file=root/'spatial-cohorts.json'
    if not file.exists():return dict(status='pending',cohorts=[])
    by_attempt={d['attempt']:d for d in rows};results=[]
    for cohort in json.loads(file.read_text())['cohorts']:
        first=next((a for a in cohort['attempts'] if a['same_core_clean']),None)
        d={k:cohort[k] for k in ('bytes','align','seed')};d['supports']=False
        if first and all(a in by_attempt for a in first['records']):
            g=sorted([by_attempt[a] for a in first['records']],key=lambda d:d['parameters']['offset'])
            low,at,high=[r['statistics'] for r in g]
            d.update(sources=[r['record_path'] for r in g],medians=[r['statistics']['median'] for r in g],
                same_cpu=len({r['selected']['cpu'] for r in g})==1,
                full_huge_backing=all(huge(r) for r in g),
                supports=all(r['qualification']=='clean' for r in g) and all(huge(r) for r in g)
                    and len({r['selected']['cpu'] for r in g})==1
                    and min(at['q1'],high['q1'])-low['q3']>=2/min(r['parameters']['batch'] for r in g))
        else:d['reason']='No complete clean same-core acquisition cohort'
        results.append(d)
    return dict(status='reproduced' if results and all(c['supports'] for c in results) else 'mixed/inconclusive',
        supported=sum(c['supports'] for c in results),total=len(results),cohorts=results,
        limitation='Visible spatial granularity at these working sets; offsets change active-line count and set coverage as well as spatial reuse. Separate per-level physical line sizes remain unestablished')


def capacity(rows,plan,root=None):
    groups=collections.defaultdict(list)
    for r in rows:
        if r['family']=='capacity_repeat':groups[r['parameters']['page'],r['parameters']['seed']].append(r)
    curves=[dict(page=page,seed=seed,edges=edges(g,'bytes'),sources=[r['record_path'] for r in g]) for (page,seed),g in sorted(groups.items())]
    matched=[]
    if root and (root/'capacity-matched.json').exists():
        by_attempt={r['attempt']:r for r in rows}
        for cohort in json.loads((root/'capacity-matched.json').read_text())['cohorts']:
            g=[by_attempt[ref] for ref in cohort['accepted_records'] if ref in by_attempt]
            found=edges(g,'bytes') if len(g)==len(cohort['counts']) else []
            matched.append(dict(page=cohort['page'],seed=cohort['seed'],series=cohort['series'],interval=cohort['interval'],
                accepted=bool(g) and len(g)==len(cohort['counts']),edges=found,sources=[r['record_path'] for r in g]))
            for curve in curves:
                if curve['page']==cohort['page'] and curve['seed']==cohort['seed']:
                    curve['edges'].extend(found);curve['sources'].extend(r['record_path'] for r in g)
    # Report ALL replicated intervals inside the original envelope. An edge is
    # not automatically the LLC boundary, and multiple candidates are retained.
    common=[]
    if len(curves)==4:
        candidates=[[e for e in c['edges'] if e['qualified']] for c in curves]
        for combination in itertools.product(*candidates):
            lo=max(e['interval'][0] for e in combination);hi=min(e['interval'][1] for e in combination)
            prior=plan['capacity_interval']
            if lo<hi and prior[0]<=lo<hi<=prior[1]:
                common.append(dict(interval=[lo,hi],sources=sorted({s for e in combination for s in e['sources']})))
    unique={}
    for entry in common:unique.setdefault(tuple(entry['interval']),set()).update(entry['sources'])
    common=[dict(interval=list(interval),sources=sorted(sources)) for interval,sources in sorted(unique.items())]
    return dict(curves=curves,matched_cohorts=matched,replicated_intervals=common,prior_interval=plan['capacity_interval'],
        interpretation='Replicated timing departure intervals, conditional on physical-level assignment; not specification confidence intervals')


def conflict(rows,plan):
    groups=collections.defaultdict(list)
    for r in rows:
        p=r['parameters']
        if r['family']=='batched_conflict' and p['samples']>=1000000 and r.get('comparison_accepted',True):
            groups[p['conflict_stride'],p['scrub_count'],p['variant'],p['seed'],p['series']].append(r)
    curves=[dict(stride=s,scrub=k,variant=v,seed=seed,series=label,edges=edges(g,'candidate_count'),
        sources=[r['record_path'] for r in g]) for (s,k,v,seed,label),g in sorted(groups.items())]
    repeated=[]
    for stride in plan['conflict_strides']:
        for scrub in (0,plan['l1_ways']+2):
            for series in ('heldout','repair-heldout'):
                g=[c for c in curves if c['stride']==stride and c['scrub']==scrub and c['series']==series]
                expected=2 if scrub==0 else 4
                if len(g)!=expected:continue
                sets=[{tuple(e['interval']) for e in c['edges'] if e['qualified'] and e['interval'][1]-e['interval'][0]==1} for c in g]
                for interval in sorted(set.intersection(*sets)):
                    repeated.append(dict(stride=stride,scrub=scrub,interval=list(interval),effective_count=interval[0],confirmation_series=series,
                        sources=sorted({s for c in g for e in c['edges'] if e['interval']==list(interval) for s in e['sources']})))
    geometry=[]
    for n in sorted({r['effective_count'] for r in repeated if r['scrub']}):
        support=[r for r in repeated if r['scrub'] and r['effective_count']==n]
        periods=sorted({r['stride'] for r in support})
        product=n*min(periods)
        geometry.append(dict(effective_count=n,agreeing_strides=periods,smallest_tested_product_bytes=product,
            compatible_with_prior_l2=plan['l2_interval'][0]<=product<=plan['l2_interval'][1],
            at_least_two_strides=len(periods)>=2))
    candidates=[g['effective_count'] for g in geometry if g['compatible_with_prior_l2'] and g['at_least_two_strides']]
    return dict(curves=curves,repeated_thresholds=repeated,geometry_checks=geometry,
        conditional_l2_ways=candidates[0] if len(candidates)==1 else None,
        conditional_candidates=candidates,physical_l2_ways=None,
        interpretation='Effective ring thresholds only. Fixed scrub contributes to the timed average; neither complete candidate L1 eviction nor unique lower-index congruence is independently proven. Geometry compatibility alone does not establish physical ways.')


def verify_host(host,final=False):
    root=ROOT/'machines'/host/'uncertainty-v1'
    plan=json.loads((ROOT/'config/uncertainty-plan.json').read_text())['hosts'][host]
    records=[];issues=[];unsuccessful=[];manifests=set()
    for path in sorted(root.glob('*/*/attempt-*/run.json')):
        original=json.loads(path.read_text())
        if not original.get('raw'):
            unsuccessful.append(dict(record=str(path.relative_to(ROOT)),status=original.get('status'),reason=original.get('error',original.get('reason','No completed raw distribution; see controller log'))))
            continue
        d,bad=verify(path,root,smoke=original['parameters']['samples']<1000000)
        if json.loads((path.parent/'stdout.log').read_text())!=d['measurement']:
            bad.append('Benchmark stdout/measurement metadata mismatch')
        if bad:issues.append(dict(record=d['record_path'],problems=bad))
        env=root/d['environment_record'];manifest=root/d['provenance_manifest'];manifests.add(manifest)
        if not env.exists():issues.append(dict(record=d['record_path'],problems=['Missing environment']))
        else:
            environment=json.loads(env.read_text())
            if environment['config']['_source_digest']!=d['source_sha256']:issues.append(dict(record=d['record_path'],problems=['Environment source identity mismatch']))
        records.append(d)
    for manifest in manifests:
        for name,digest in json.loads(manifest.read_text())['files'].items():
            if sha(manifest.parent/name)!=digest:issues.append(dict(record=str(manifest.relative_to(ROOT)),problems=['Producing source mismatch: '+name]))
    repair_file=root/'conflict-repair.json'
    repair=json.loads(repair_file.read_text()) if repair_file.exists() else None
    if repair:
        accepted={ref for g in repair['repairs']+repair['confirmations'] for ref in g['accepted_records']}
        for d in records:
            if d['parameters'].get('series') in ('discovery-repair','repair-heldout'):
                d['comparison_accepted']=d['attempt'] in accepted
    matched_file=root/'capacity-matched.json'
    matched=json.loads(matched_file.read_text()) if matched_file.exists() else None
    if matched:
        accepted={ref for g in matched['cohorts'] for ref in g['accepted_records']}
        for d in records:
            if d['family']=='capacity_matched':d['comparison_accepted']=d['attempt'] in accepted
    by_key=collections.defaultdict(list)
    for d in records:
        if d['parameters']['samples']>=1000000:by_key[d['family'],Path(d['attempt']).parts[1]].append(d)
    selected=[]
    for group in by_key.values():
        group.sort(key=lambda d:d['started']);good=[d for d in group if d['qualification']=='clean']
        valid=[d for d in group if d['qualification']!='invalid']
        if good or valid:selected.append((good or valid)[0])
    by_attempt={d['attempt']:d for d in records};missing=[];stages={}
    required_stages=['smoke','controls','conflict','capacity','spatial']+(['repair_smoke','repair'] if plan['conflict_required'] else [])
    if plan['capacity_interval']:required_stages.append('capacity_repair')
    for stage in required_stages:
        path=root/(stage+'-finished.json')
        if not path.exists():missing.append(stage);continue
        marker=json.loads(path.read_text());stages[stage]=marker
        if marker['failed']:issues.append(dict(stage=stage,problems=['Expected configurations failed: '+str(marker['failed'])]))
        for ref in marker['records']:
            if ref not in by_attempt:issues.append(dict(stage=stage,problems=['Missing stage-selected distribution: '+str(ref)]))
    gate=json.loads((root/'timer-gate.json').read_text()) if (root/'timer-gate.json').exists() else {}
    if not gate.get('passed'):issues.append(dict(problems=['Timer gate missing/failed']))
    elif all(ref in by_attempt for ref in gate['sources']):
        timer,hot=[by_attempt[ref] for ref in gate['sources']]
        ratio=timer['statistics']['median']/(hot['statistics']['median']*hot['parameters']['batch'])
        if abs(ratio-gate['fraction'])>1e-12 or ratio>.05 or timer['qualification']!=hot['qualification'] or hot['qualification']!='clean':
            issues.append(dict(problems=['Independent timer overhead/quality gate failed']))
    else:issues.append(dict(problems=['Missing timer gate source records']))
    # Coverage is independently derived from prospective plan, not just markers.
    if final:
        smoke=[r for r in records if r['parameters']['samples']==2048]
        if len({(r['family'],Path(r['attempt']).parts[1]) for r in smoke})!=(6 if plan['conflict_required'] else 4):issues.append(dict(problems=['Smoke coverage']))
        spatial_keys={(r['parameters']['bytes'],r['parameters']['align'],r['parameters']['seed'],r['parameters']['offset']) for r in selected if r['family']=='spatial_residency'}
        seed=json.loads((ROOT/'config/phase1.json').read_text())['seed']
        expected={(w,a,s,o) for w in plan['spatial_allocations'] for a in (0,24) for s in (seed+1401,seed+1501) for o in (56-a,64-a,72-a)}
        if not expected<=spatial_keys:issues.append(dict(problems=['Spatial prospective coverage missing']))
        if plan['conflict_required']:
            expected={(s,k,n) for s in plan['conflict_strides'] for k in (0,plan['l1_ways']+2) for n in plan['conflict_counts']}
            actual={(r['parameters']['conflict_stride'],r['parameters']['scrub_count'],r['parameters']['candidate_count']) for r in selected if r['family']=='batched_conflict' and r['parameters']['series']=='discovery'}
            if not expected<=actual:issues.append(dict(problems=['Conflict prospective coverage missing']))
            file=root/'conflict-refinement-plan.json'
            if file.exists():
                for discovery in json.loads(file.read_text())['discoveries']:
                    counts={n for lo,hi in discovery['edges'] for n in range(max(2,lo-1),hi+2)}
                    for v in ((1,2) if discovery['scrub'] else (1,)):
                        for s in (seed+1001,seed+1101):
                            actual={r['parameters']['candidate_count'] for r in selected if r['family']=='batched_conflict' and r['parameters']['series']=='heldout' and r['parameters']['conflict_stride']==discovery['stride'] and r['parameters']['scrub_count']==discovery['scrub'] and r['parameters']['variant']==v and r['parameters']['seed']==s}
                            if not counts<=actual:issues.append(dict(problems=['Conflict adaptive coverage missing']))
            else:issues.append(dict(problems=['Missing conflict refinement plan']))
            if not repair:issues.append(dict(problems=['Missing conflict quality-repair record']))
            else:
                from uncertainty_worker import blocked_pairs
                original=json.loads((root/'conflict-refinement-plan.json').read_text())
                expected_pairs={(g['stride'],g['scrub'],tuple(pair)) for g in original['discoveries']
                    for pair in blocked_pairs([by_attempt[ref] for ref in g['records']])}
                actual_pairs={(g['stride'],g['scrub'],tuple(g['interval'])) for g in repair['repairs']}
                if expected_pairs!=actual_pairs:issues.append(dict(problems=['Quality-repair pair coverage mismatch']))
                expected_confirmations={(g['stride'],g['scrub'],tuple(edge),v,s) for g in repair['repairs'] for edge in g['edges']
                    for v in ((1,2) if g['scrub'] else (1,)) for s in (seed+1801,seed+1901)}
                actual_confirmations={(g['stride'],g['scrub'],tuple(g['interval']),g['variant'],g['seed']) for g in repair['confirmations']}
                if expected_confirmations!=actual_confirmations:issues.append(dict(problems=['Repair held-out coverage mismatch']))
                for group in repair['repairs']+repair['confirmations']:
                    first=[]
                    for attempt in group['attempts']:
                        rs=[by_attempt[ref] for ref in attempt['records'] if ref in by_attempt]
                        expected_counts=group.get('counts',group['interval'])
                        if len(rs)!=len(expected_counts) or {r['parameters']['candidate_count'] for r in rs}!=set(expected_counts):
                            issues.append(dict(problems=['Incomplete quality-repair cohort']))
                        if not first and rs and all(r['qualification']=='clean' for r in rs) and len({r['selected']['cpu'] for r in rs})==1:
                            first=attempt['records']
                    if first!=group['accepted_records']:issues.append(dict(problems=['Repair did not select first clean same-core cohort']))
        if plan['capacity_interval']:
            lo,hi=plan['capacity_interval'];grid={lo//2,hi*2}|{lo+(hi-lo)*i//8 for i in range(9)}
            for page in ('base','huge'):
                for s in (seed+1201,seed+1301):
                    actual={r['parameters']['bytes'] for r in selected if r['family']=='capacity_repeat' and r['parameters']['page']==page and r['parameters']['seed']==s}
                    file=root/('capacity-plan-'+page+'-'+str(s)+'.json')
                    if not file.exists():issues.append(dict(problems=['Missing capacity refinement plan']));continue
                    edges_plan=json.loads(file.read_text())['edges'];expected=grid|{((a+(b-a)*i//4)//64)*64 for a,b in edges_plan for i in (1,2,3)}
                    if not expected<=actual:issues.append(dict(problems=['Capacity prospective/adaptive coverage missing']))
            if not matched:issues.append(dict(problems=['Missing matched capacity controls']))
            else:
                from uncertainty_worker import clean_cross_core_pairs
                groups=collections.defaultdict(list)
                for r in selected:
                    if r['family']=='capacity_repeat':groups[r['parameters']['page'],r['parameters']['seed']].append(r)
                expected={(page,s,tuple(pair)) for (page,s),g in groups.items() for pair in clean_cross_core_pairs(g)}
                actual={(g['page'],g['seed'],tuple(g['interval'])) for g in matched['cohorts'] if g['series']=='matched-pair'}
                if expected!=actual:issues.append(dict(problems=['Matched capacity pair coverage mismatch']))
                for group in matched['cohorts']:
                    first=[]
                    for attempt in group['attempts']:
                        rs=[by_attempt[ref] for ref in attempt['records'] if ref in by_attempt]
                        if len(rs)!=len(group['counts']) or {r['parameters']['bytes'] for r in rs}!=set(group['counts']):issues.append(dict(problems=['Incomplete matched capacity cohort']))
                        if not first and rs and all(r['qualification']=='clean' for r in rs) and len({r['selected']['cpu'] for r in rs})==1:first=attempt['records']
                    if first!=group['accepted_records']:issues.append(dict(problems=['Matched capacity did not select first clean same-core cohort']))
                    if group['series']=='matched-pair' and first:
                        rs=[by_attempt[ref] for ref in first]
                        if any(e['ratio']>1.15 for e in edges(rs,'bytes')):
                            if not any(g['series']=='matched-refinement' and g['page']==group['page'] and g['seed']==group['seed'] and g['interval']==group['interval'] for g in matched['cohorts']):issues.append(dict(problems=['Missing matched capacity refinement']))
    result=dict(time=now(),host=host,complete=not issues and not missing,issues=issues,missing_stages=missing,
        attempts=len(records),full_attempts=sum(d['parameters']['samples']>=1000000 for d in records),
        smoke_attempts=sum(d['parameters']['samples']<1000000 for d in records),selected_points=len(selected),
        noisy_selected=sum(d['qualification']=='noisy' for d in selected),flagged_attempts=sum(bool(d.get('flags')) for d in records),
        unsuccessful=unsuccessful,stages=stages,timer_gate=gate,spatial=spatial(records,root),
        capacity=capacity(selected,plan,root),conflict=conflict(selected,plan))
    write_json(OUT/(host+'-records.json'),records);write_json(OUT/(host+'-selected.json'),selected)
    write_json(OUT/(host+'-inference.json'),result)
    print(json.dumps({k:result[k] for k in ('host','complete','attempts','selected_points','noisy_selected','issues','missing_stages')}),flush=True)
    return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--final',action='store_true');ap.add_argument('--hosts',nargs='+');ap.add_argument('--jobs',type=int,default=2);args=ap.parse_args()
    if args.final:
        # Also serves an already queued final invocation: new repairs must be
        # collected before any final statistics or artifacts are published.
        required=[(h,'repair') for h in ('crux','thunderbird')]+[(h,'capacity_repair') for h in ('sunbird','charnwood','crux','upgrade')]
        while any(not (ROOT/'machines'/h/'uncertainty-v1'/(stage+'-finished.json')).exists() for h,stage in required):
            time.sleep(5)
    digest=sha(Path(__file__));plan_digest=sha(ROOT/'config/uncertainty-plan.json')
    policy_digest=sha(ROOT/'config/uncertainty-analysis-policy.json')
    repair_digest=sha(ROOT/'config/uncertainty-repair-policy.json')
    matched_digest=sha(ROOT/'config/uncertainty-capacity-repair-policy.json')
    allowed=json.loads((ROOT/'config/phase1.json').read_text())['hosts'];hosts=args.hosts or allowed
    if set(hosts)-set(allowed):ap.error('Invalid host')
    inputs=snapshot_inputs(hosts) if args.final else {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:results=list(pool.map(lambda h:verify_host(h,args.final),hosts))
    if digest!=sha(Path(__file__)) or plan_digest!=sha(ROOT/'config/uncertainty-plan.json') or policy_digest!=sha(ROOT/'config/uncertainty-analysis-policy.json') or repair_digest!=sha(ROOT/'config/uncertainty-repair-policy.json') or matched_digest!=sha(ROOT/'config/uncertainty-capacity-repair-policy.json'):raise SystemExit('Analysis source/plan/policy changed during execution')
    if args.final and inputs!=snapshot_inputs(hosts):raise SystemExit('Acquisition inputs changed during final verification')
    summary=dict(time=now(),complete=args.final and set(hosts)==set(allowed) and all(r['complete'] for r in results),
        final_requested=args.final,hosts=results,analysis_sha256=digest,plan_sha256=plan_digest,policy_sha256=policy_digest,repair_policy_sha256=repair_digest,capacity_repair_policy_sha256=matched_digest,
        input_snapshot=inputs,selected_points=sum(r['selected_points'] for r in results),full_attempts=sum(r['full_attempts'] for r in results),
        smoke_attempts=sum(r['smoke_attempts'] for r in results),noisy_selected=sum(r['noisy_selected'] for r in results),
        flagged_attempts=sum(r['flagged_attempts'] for r in results))
    write_json(OUT/('verification.json' if args.final else 'diagnostic-verification.json'),summary)
    with open(OUT/'statistics.csv','w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['host','family','qualification','cpu','unit','parameters','record','raw_sha256','n','mean','stddev','median','q1','q3','p05','p95','minimum','maximum','outliers'])
        writer.writeheader()
        for host in hosts:
            for d in json.loads((OUT/(host+'-selected.json')).read_text()):
                row=dict(host=host,family=d['family'],qualification=d['qualification'],cpu=d['selected']['cpu'],unit=d['statistic_unit'],
                    parameters=json.dumps(d['parameters'],sort_keys=True),record=d['record_path'],raw_sha256=d['raw_sha256'])
                row.update({k:d['statistics'][k] for k in writer.fieldnames if k in d['statistics']});writer.writerow(row)
    affinity=collections.defaultdict(list)
    for host in hosts:
        for r in json.loads((OUT/(host+'-records.json')).read_text()):
            s=r['selected'];affinity[host,s['cpu'],s['core'],s['socket'],s['node']].append(r)
    with open(OUT/'affinity-summary.csv','w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['host','cpu','physical_core','socket','node','raw_attempts','flagged_attempts','maximum_initial_busy_fraction','idle_evidence'])
        for key,group in sorted(affinity.items()):
            writer.writerow(list(key)+[len(group),sum(bool(r.get('flags')) for r in group),
                max(r['selected']['peak_busy_fraction'] for r in group),
                json.dumps([str(Path(r['record_path']).with_name('idle.json')) for r in group])])
    if args.final and not summary['complete']:raise SystemExit('Final verification incomplete; see retained explanations')

if __name__=='__main__':main()
