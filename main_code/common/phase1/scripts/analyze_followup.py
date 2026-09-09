#!/usr/bin/env python3
"""Independently verify second-round raw samples and infer timing-only candidates."""
import argparse
import collections
import concurrent.futures
import csv
import hashlib
import json
import math
import sys
from pathlib import Path
from common import now, read_raw, sha, statistics_agree, stats, utilization, write_json

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data_processed/followup'


def verify(record_path,root,smoke=False):
    d=json.loads(record_path.read_text());d['record_path']=str(record_path.relative_to(ROOT))
    if not d.get('raw'):return d,['no completed raw distribution: '+d.get('error',d.get('status','unknown'))]
    problems=[];raw=root/d['raw'];m=d['measurement'];p=d['parameters']
    if not raw.exists() or sha(raw)!=d['raw_sha256']:return d,['raw SHA256 mismatch/missing']
    values=read_raw(raw,m['little_endian']);divisor=p.get('timed_loads',p['batch'])
    s=stats(values,divisor)
    if len(values)!=p['samples'] or m['samples']!=len(values) or (not smoke and len(values)<1000000):problems.append('sample count')
    if not statistics_agree(s,d['statistics']):problems.append('raw-recomputed statistics mismatch')
    d['statistics']=s
    d['statistic_unit']=m['unit']+('/interval' if p['mode']=='overhead' else '/target_reload' if p.get('timed_loads')==1 else '/access')
    d['raw_path']=str(raw.relative_to(ROOT))
    idle=json.loads((record_path.parent/'idle.json').read_text());selected=idle['selected']
    if len(idle['evidence'])<2:problems.append('missing idle windows')
    for w in idle['evidence']:
        a={int(k):v for k,v in w['before'].items()};b={int(k):v for k,v in w['after'].items()}
        busy=utilization(a,b)
        for choice in [selected]+([idle['helper']] if p.get('paired_core') else []):
            if any(busy.get(cpu,1)>idle['threshold']+1e-12 for cpu in choice['siblings']):problems.append('idle evidence does not qualify selected core')
    if m['cpu']!=selected['cpu'] or m['final_cpu']!=selected['cpu']:problems.append('measuring affinity mismatch')
    if p.get('paired_core'):
        helper=idle['helper']
        if m['helper_cpu']!=helper['cpu'] or helper['core']==selected['core'] or helper['socket']!=selected['socket']:problems.append('helper affinity/topology mismatch')
    manifest=root/d['provenance_manifest']
    provenance=json.loads(manifest.read_text())
    for source in ('src/cache_bench.c','src/followup_bench.c','scripts/worker.py','scripts/followup_worker.py','config/followup-plan.json'):
        if sha(manifest.parent/source)!=provenance['files'][source]:problems.append('producing source hash mismatch')
    digest=hashlib.sha256((provenance['files']['src/cache_bench.c']+provenance['files']['src/followup_bench.c']).encode()).hexdigest()
    if digest!=d['source_sha256']:problems.append('benchmark source identity mismatch')
    if p.get('address_list_sha256'):
        path=root/'address-sets'/Path(p['address_list']).name
        if not path.exists() or sha(path)!=p['address_list_sha256']:problems.append('address-set provenance mismatch')
    if m['major_faults']:problems.append('major faults')
    d['qualification']='invalid' if problems else 'noisy' if d.get('flags') else 'clean'
    # Raw block statistics expose quantization and drift without treating the
    # million correlated intervals as independent experimental replications.
    block=max(1,len(values)//10)
    d['block_means']=[sum(values[i:i+block])/len(values[i:i+block])/divisor for i in range(0,len(values),block)]
    if d['family'] in ('cross_core_reload','same_core_reload','target_hot'):
        d['tail_histogram']=sorted(collections.Counter(values).items())
    return d,sorted(set(problems))


def spatial_inference(rows):
    grouped=collections.defaultdict(list)
    for d in rows:
        if d['family']=='spatial_alignment' and d['qualification']=='clean':
            p=d['parameters'];grouped[p['bytes'],p['align']].append(d)
    signatures=[]
    for (footprint,align),group in sorted(grouped.items()):
        group.sort(key=lambda d:d['parameters']['offset']);edges=[]
        for a,b in zip(group,group[1:]):
            pa,pb=a['parameters'],b['parameters'];sa,sb=a['statistics'],b['statistics']
            if pb['offset']-pa['offset']!=8:continue
            quantum=2/min(pa.get('batch',1),pb.get('batch',1))
            if sb['median']>sa['median'] and sb['q1']-sa['q3']>=quantum:
                edges.append(dict(offset_interval=[pa['offset'],pb['offset']],absolute_boundary_candidate=pb['offset']+align,
                    same_cpu=a['selected']['cpu']==b['selected']['cpu'],relative_median_increase=sb['median']/sa['median']-1,
                    passes_original_10_percent_cutoff=sb['median']>1.10*sa['median'],
                    minimum_iqr_gap_ticks_per_access=quantum,sources=[a['record_path'],b['record_path']]))
        signatures.append(dict(footprint=footprint,align=align,edges=edges))
    support=collections.defaultdict(list)
    for g in signatures:
        for edge in g['edges']:support[edge['absolute_boundary_candidate']].append(dict(footprint=g['footprint'],align=g['align'],**edge))
    candidates=[]
    for boundary,evidence in sorted(support.items()):
        fps={e['footprint'] for e in evidence};aligns={e['align'] for e in evidence}
        pairs={(e['footprint'],e['align']) for e in evidence}
        if len(fps)>=2 and len(aligns)>=2 and all((w,a) in pairs for w in fps for a in aligns):
            candidates.append(dict(bytes=boundary,evidence=evidence))
    # The specification asks for the SMALLEST reproducible granularity; a second
    # larger transition does not disqualify the first shifted boundary.
    return dict(candidate_bytes=candidates[0]['bytes'] if candidates else None,candidates=candidates,signatures=signatures,
        resolution_bytes=8,rule='Smallest IQR-separated edge with gap >=2 native interval ticks after batch scaling, reproduced across >=2 alignments and >=2 footprints; separately checked same-core confirmations. Original 10% effect cutoff retained as sensitivity, not a specification requirement.',
        limitation='Candidate transfer granularity visible in this workload; separate line sizes of every cache level are not established')


def confirmation(rows,root):
    file=root/'spatial-cohorts.json'
    if not file.exists():return dict(status='pending',cohorts=[])
    by_attempt={d['attempt']:d for d in rows if d['family']=='spatial_confirmation'}
    output=[]
    for c in json.loads(file.read_text())['cohorts']:
        accepted=next((a for a in c['attempts'] if a['same_core'] and a['all_clean']),None)
        result=dict(bytes=c['bytes'],align=c['align'],seed=c['seed'],acquisition_accepted=bool(accepted))
        if accepted and all(a in by_attempt for a in accepted['records']):
            g=sorted([by_attempt[a] for a in accepted['records']],key=lambda d:d['parameters']['offset'])
            low,at,high=[d['statistics'] for d in g]
            clean=all(d['qualification']=='clean' for d in g)
            quantum=2/min(d['parameters']['batch'] for d in g)
            result.update(boundary=g[1]['parameters']['offset']+c['align'],same_cpu=len({d['selected']['cpu'] for d in g})==1,
                medians=[d['statistics']['median'] for d in g],sources=[d['record_path'] for d in g],
                passes_original_10_percent_cutoff=at['median']>1.10*low['median'] and high['median']>1.10*low['median'],
                supports=clean and min(at['median'],high['median'])>low['median'] and min(at['q1'],high['q1'])-low['q3']>=quantum)
        output.append(result)
    yes=[c for c in output if c.get('supports') and c.get('same_cpu')]
    footprints={c['bytes'] for c in output};seeds={c['seed'] for c in output};alignments={c['align'] for c in output}
    keys={(c['bytes'],c['align'],c['seed']) for c in yes}
    replicated_alignments=[a for a in sorted(alignments) if all((w,a,s) in keys for w in footprints for s in seeds)]
    accepted=len(footprints)>=2 and len(seeds)>=2 and len(replicated_alignments)>=2
    return dict(status='supported' if accepted else 'ambiguous',supported_cohorts=len(yes),total_cohorts=len(output),
        fully_replicated_alignments=replicated_alignments,cohorts=output)


def matched_refinement_edges(rows):
    """Keep endpoints inside the same prospective refinement cohort."""
    groups=collections.defaultdict(list)
    for d in rows:
        if d['family']=='capacity_refinement' and d['qualification']=='clean':
            p=d['parameters'];groups[p['page'],p['stride'],tuple(p['comparison_interval'])].append(d)
    output=[]
    for (page,stride,interval),group in sorted(groups.items()):
        chosen={}
        for d in sorted(group,key=lambda d:d['started']):chosen.setdefault(d['parameters']['bytes'],d)
        curve=[chosen[w] for w in sorted(chosen)];edges=[];step=(interval[1]-interval[0])//8
        for a,b in zip(curve,curve[1:]):
            sa,sb=a['statistics'],b['statistics'];lo,hi=a['parameters']['bytes'],b['parameters']['bytes']
            if hi-lo==step and sb['median']>1.15*sa['median'] and sb['q1']>sa['q3']:
                edges.append(dict(lower_bytes=lo,upper_bytes=hi,ratio=sb['median']/sa['median'],below=sa,above=sb,
                    same_cpu=a['selected']['cpu']==b['selected']['cpu'],
                    huge_confirmed=all(min(d['measurement']['anon_huge_before_kib'],d['measurement']['anon_huge_after_kib'])*1024>=d['measurement']['mapped_bytes'] for d in (a,b)),
                    sources=[a['record_path'],b['record_path']]))
        output.append(dict(page=page,stride=stride,comparison_interval=list(interval),edges=edges))
    return output


def common_class_boundaries(models):
    """Match overlapping boundaries, allowing extra density-specific classes."""
    if len(models)!=2:return []
    output=[]
    for a in models[0]['boundaries_bytes'][1:]:
        for b in models[1]['boundaries_bytes'][1:]:
            lo,hi=max(a[0],b[0]),min(a[1],b[1])
            if lo<hi:output.append(dict(interval=[lo,hi],brackets=[a,b]))
    return sorted(output,key=lambda d:d['interval'])


def capacity_inference(rows):
    groups=collections.defaultdict(list)
    for d in rows:
        if d['family'] in ('capacity_control','capacity_refinement') and d['qualification']=='clean':
            p=d['parameters'];groups[p['page'],p['stride']].append(d)
    result=[]
    for (page,stride),group in sorted(groups.items()):
        # Keep first chronological clean instance at an identical footprint; do
        # not minimize latency or average across cores to manufacture an edge.
        chosen={}
        for d in sorted(group,key=lambda d:d['started']):chosen.setdefault(d['parameters']['bytes'],d)
        curve=[chosen[w] for w in sorted(chosen)];edges=[]
        for a,b in zip(curve,curve[1:]):
            sa,sb=a['statistics'],b['statistics'];lo,hi=a['parameters']['bytes'],b['parameters']['bytes']
            if sb['median']>1.15*sa['median'] and sb['q1']>sa['q3']:
                edges.append(dict(lower_bytes=lo,upper_bytes=hi,ratio=sb['median']/sa['median'],
                    below=sa,above=sb,same_cpu=a['selected']['cpu']==b['selected']['cpu'],
                    huge_confirmed=all(min(d['measurement']['anon_huge_before_kib'],d['measurement']['anon_huge_after_kib'])*1024>=d['measurement']['mapped_bytes'] for d in (a,b)),
                    sources=[a['record_path'],b['record_path']]))
        result.append(dict(page=page,stride=stride,edges=edges,curve=[dict(bytes=d['parameters']['bytes'],median=d['statistics']['median'],
            p05=d['statistics']['p05'],p95=d['statistics']['p95'],cpu=d['selected']['cpu'],huge_kib=d['measurement']['anon_huge_before_kib'],
            source=d['record_path']) for d in curve]))
    models=[]
    for (page,stride),group in sorted(groups.items()):
        if page!='huge':continue
        chosen={}
        for d in sorted(group,key=lambda d:d['started']):
            w=d['parameters']['bytes'];m=d['measurement']
            if d['family']=='capacity_control' and w&(w-1)==0 and min(m['anon_huge_before_kib'],m['anon_huge_after_kib'])*1024>=m['mapped_bytes']:
                chosen.setdefault(w,d)
        curve=[chosen[w] for w in sorted(chosen)]
        if len(curve)>=8:models.append(dict(stride=stride,**plateau_model(curve)))
    consistent=False
    if len(models)==2 and all(m['chosen_classes']==4 for m in models):
        a,b=models
        consistent=all(max(x[0],y[0])<=min(x[1],y[1]) for x,y in zip(a['boundaries_bytes'],b['boundaries_bytes']))
    return dict(curves=result,matched_refinements=matched_refinement_edges(rows),plateau_models=models,
        hierarchy_status='Three cache-like timing classes plus a memory-like class; conditional dense/sparse agreement' if consistent else 'Effective timing classes; physical hierarchy assignment remains tentative',
        three_cache_class_agreement=consistent,
        rule='Adjacent clean medians increase >15% with separated IQRs; first chronological clean instance per footprint',
        limitation='Candidate boundaries require comparison across page policies and spacings, and latency modes, before assigning a physical cache level')


def prefetch_controls(rows):
    comparisons=[]
    for regular in [d for d in rows if d['family']=='capacity_regular']:
        p=regular['parameters']
        candidates=[d for d in rows if d['family']=='capacity_refinement' and d['parameters']['bytes']==p['bytes'] and d['parameters']['page']==p['page'] and d['parameters']['stride']==p['stride']]
        if not candidates:continue
        candidates.sort(key=lambda d:d['started']);randomized=candidates[0]
        comparisons.append(dict(bytes=p['bytes'],stride=p['stride'],page=p['page'],
            same_cpu=regular['selected']['cpu']==randomized['selected']['cpu'],
            clean=regular['qualification']==randomized['qualification']=='clean',
            regular=regular['statistics'],randomized=randomized['statistics'],
            regular_over_randomized_median=regular['statistics']['median']/randomized['statistics']['median'],
            sources=[regular['record_path'],randomized['record_path']]))
    return dict(comparisons=comparisons,
        choice='Randomized dependent traversal is the primary capacity/latency inference; regular traversal is a prefetch sensitivity control. Cross-core or noisy pairs are descriptive only.')


def plateau_model(curve):
    """BIC-selected contiguous log-latency classes; no expected cache sizes."""
    n=len(curve);y=[math.log(d['statistics']['median']) for d in curve]
    def cost(a,b):
        center=sum(y[a:b])/(b-a)
        return sum((v-center)**2 for v in y[a:b])
    models=[]
    for k in range(2,min(5,n//2)+1):
        dp={(0,0):(0,[])}
        for segments in range(1,k+1):
            for end in range(segments*2,n+1):
                candidates=[]
                for start in range((segments-1)*2,end-1):
                    prior=dp.get((segments-1,start))
                    if prior:candidates.append((prior[0]+cost(start,end),prior[1]+[(start,end)]))
                if candidates:dp[segments,end]=min(candidates,key=lambda p:p[0])
        sse,segments=dp[k,n]
        models.append(dict(classes=k,sse=sse,bic=n*math.log(max(sse/n,1e-12))+(2*k-1)*math.log(n),segments=segments))
    chosen=min(models,key=lambda d:d['bic']);segments=[];boundaries=[]
    for index,(a,b) in enumerate(chosen['segments']):
        g=curve[a:b];medians=[d['statistics']['median'] for d in g]
        segments.append(dict(class_index=index+1,working_set_range=[g[0]['parameters']['bytes'],g[-1]['parameters']['bytes']],
            median_timing_range=[min(medians),max(medians)],geometric_center=math.exp(sum(y[a:b])/(b-a)),
            representative=dict(working_set_bytes=g[(len(g)-1)//2]['parameters']['bytes'],
                statistics=g[(len(g)-1)//2]['statistics'],cpu=g[(len(g)-1)//2]['selected']['cpu'],
                unit=g[(len(g)-1)//2]['statistic_unit'],source=g[(len(g)-1)//2]['record_path']),
            sources=[d['record_path'] for d in g]))
        if b<n:boundaries.append([curve[b-1]['parameters']['bytes'],curve[b]['parameters']['bytes']])
    for previous,current in zip(segments,segments[1:]):
        a,b=previous['representative'],current['representative'];same=a['cpu']==b['cpu']
        current['transition_from_previous']=dict(same_cpu=same,
            previous_median=a['statistics']['median'],next_class_median=b['statistics']['median'],
            incremental_median_penalty=b['statistics']['median']-a['statistics']['median'] if same else None,
            sources=[a['source'],b['source']],
            definition='Difference of representative dependent-access medians on the same core; conditional effective residency classes, not an isolated hardware miss penalty')
    return dict(chosen_classes=chosen['classes'],boundaries_bytes=boundaries,segments=segments,alternatives=models,
        representative_rule='Lower middle sampled footprint within each fitted class, chosen by footprint order, never by fastest timing; full raw-recomputed distribution retained',
        limitation='Exploratory BIC segmentation of measured medians; intervals bracket class changes, not statistical confidence or independently established physical capacities')


def conflict_inference(rows,root):
    path=root/'empirical-search.json'
    if not path.exists():return dict(status='pending',searches=[])
    by_attempt={d['attempt']:d for d in rows if d['family']=='empirical_conflict'}
    result=[]
    def center(d):
        s=d['statistics'];return (s['q1']+s['median']+s['q3'])/3
    for search in json.loads(path.read_text())['searches']:
        item={k:v for k,v in search.items() if k not in ('validation','trials')};validation=[]
        for v in search.get('validation',[]):
            d=by_attempt.get(v['record'].get('attempt'))
            if d:validation.append(dict(kind=v['kind'],seed=v['seed'],removed=v.get('removed'),center=center(d),
                qualification=d['qualification'],cpu=d['selected']['cpu'],huge_kib=d['measurement']['anon_huge_before_kib'],source=d['record_path']))
        replicated=[]
        for seed in sorted({v['seed'] for v in validation}):
            full=next((v for v in validation if v['seed']==seed and v['kind']=='full'),None)
            hot=next((v for v in validation if v['seed']==seed and v['kind']=='hot'),None)
            if full and hot:
                deletions=[v for v in validation if v['seed']==seed and v['kind']=='delete']
                midpoint=(full['center']+hot['center'])/2
                all_deletions=len(deletions)==len(search.get('selected_offsets',[])) and all(v['qualification']=='clean' and v['cpu']==full['cpu'] and v['center']<midpoint for v in deletions)
                replicated.append(dict(seed=seed,separated=full['qualification']==hot['qualification']=='clean' and
                    full['center']-hot['center']>=max(.25,.10*hot['center']),same_cpu=full['cpu']==hot['cpu'],
                    every_single_deletion_removes_effect=all_deletions))
        item.update(validation=validation,replications=replicated,
            replicated_effective_eviction_bound=len(search['selected_offsets']) if len(replicated)==2 and all(v['separated'] and v['same_cpu'] for v in replicated) else None)
        item['replicated_minimal_set']=bool(item['replicated_effective_eviction_bound']) and all(v['every_single_deletion_removes_effect'] for v in replicated)
        result.append(item)
    return dict(searches=result,status='measured',limitation='An eviction bound is the number of tested pressure addresses sufficient to slow a target. It is not a physical way count; remapping, replacement and indexing remain controlled only to the extent shown by hold-outs.')


def cross_inference(rows):
    groups=collections.defaultdict(dict)
    for d in rows:
        if d['family']=='cross_core_reload':
            p=d['parameters'];groups[p['bytes'],p['seed']][p['offset']]=d
    comparisons=[]
    for (w,seed),g in sorted(groups.items()):
        if set(g)!={0,1}:continue
        a,b=g[0],g[1]
        histogram=a.get('tail_histogram',[])
        rank=.99*(a['statistics']['n']-1);cumulative=0;threshold=None
        for value,count in histogram:
            cumulative+=count
            if cumulative>rank:threshold=value;break
        tails={}
        if threshold is not None:
            for label,d in [('control',a),('pressure',b)]:
                values=read_raw(ROOT/d['raw_path'],d['measurement']['little_endian'])
                block=max(1,len(values)//10)
                rates=[sum(v>threshold for v in values[i:i+block])/len(values[i:i+block]) for i in range(0,len(values),block)]
                tails[label]=dict(fraction_above_threshold=sum(v>threshold for v in values)/len(values),
                    block_fraction_range=[min(rates),max(rates)],block_fractions=rates)
        comparisons.append(dict(bytes=w,seed=seed,control=a['statistics'],pressure=b['statistics'],
            same_pair=a['selected']['cpu']==b['selected']['cpu'] and a['helper_selected']['cpu']==b['helper_selected']['cpu'],
            clean=a['qualification']==b['qualification']=='clean',sources=[a['record_path'],b['record_path']],
            control_pair=[a['selected']['cpu'],a['helper_selected']['cpu']],pressure_pair=[b['selected']['cpu'],b['helper_selected']['cpu']],
            control_p99_threshold_native_ticks=threshold,tails=tails,
            tail_rule='Fraction strictly above the matched handshake-only control empirical 99th-percentile order statistic; ten chronological block ranges, not independent-sample confidence intervals'))
    return dict(comparisons=comparisons,status='behavioral evidence; global policy remains uncertain',
        limitation='Remote pressure avoids intentional direct eviction on the measuring core. Same-socket cores are not guaranteed to share an LLC domain, and target eviction from a lower shared cache is not independently guaranteed by 1024 pressure loads. Absence of a reload change does not prove exclusion/non-inclusion. Handshake effects are measured separately.')


def revised_cache_table(result):
    """Join independent timing evidence, keeping conditional roles explicit."""
    host=result['host'];base=json.loads((ROOT/'data_processed'/(host+'-inference.json')).read_text())
    old=base['l1_candidate'];interval=old.get('capacity_interval_bytes')
    line=result['spatial']['candidate_bytes'] if result['spatial_confirmation']['status']=='supported' else old.get('line_bytes')
    by_ways=collections.defaultdict(set)
    for candidate in base['associativity']['candidates']:
        by_ways[candidate['candidate_resident_addresses']].add(candidate['stride'])
    joint=[]
    if interval:
        for ways,strides in sorted(by_ways.items()):
            period=min(strides);capacity=ways*period
            if len(strides)>=3 and interval[0]<=capacity<=interval[1]:
                joint.append(dict(ways=ways,tested_period=period,capacity_candidate=capacity,strides=sorted(strides)))
    chosen=joint[0] if len(joint)==1 else None
    table=[dict(host=host,role='L1-like candidate',capacity_interval_bytes=interval,
        capacity_candidate_bytes=chosen['capacity_candidate'] if chosen else None,
        line_candidate_bytes=line,ways_candidate=chosen['ways'] if chosen else old.get('ways'),
        derived_sets=chosen['capacity_candidate']//(line*chosen['ways']) if chosen and line and chosen['capacity_candidate']%(line*chosen['ways'])==0 else None,
        hit_median_native_ticks_per_access=old['hit_class_statistics']['median'],unit=old['unit'],
        evidence='Baseline capacity departure + repeated conflict thresholds; follow-up shifted spatial boundary and independent confirmation',
        caveat='Joint candidate assumes the smallest agreeing tested conflict stride is a fundamental indexing period. Other conflict thresholds remain in the raw evidence; incompatible capacity products do not identify the L1-like class.',
        joint_conflict_candidates=joint,sharing_scope='Exact domain unverified in Phase I',inclusion_exclusion='uncertain')]
    models=result['capacity'].get('plateau_models',[])
    anchored=[m for m in models if interval and m['boundaries_bytes'] and
        max(m['boundaries_bytes'][0][0],interval[0])<min(m['boundaries_bytes'][0][1],interval[1])]
    common=common_class_boundaries(anchored)
    for role,index in [('L2-like candidate',0),('LLC-like candidate',1)]:
        matched=common[index] if len(common)>index else None
        brackets=matched['brackets'] if matched else [];agreement=bool(matched)
        capacity=matched['interval'] if matched else None
        aggregate=False
        if role.startswith('LLC') and common:
            # Multiple deeper classes can reflect mixed LLC residency. Preserve
            # their envelope rather than force the first partial departure into
            # one LLC capacity. If individual boundaries disagree, intersect the
            # two observed deeper envelopes and label the result broad.
            if len(common)>2:
                capacity=[common[1]['interval'][0],common[-1]['interval'][1]];aggregate=True
            elif matched is None:
                deeper=[[b for b in model['boundaries_bytes'] if b[0]>=common[0]['interval'][1]] for model in anchored]
                if len(deeper)==2 and all(deeper):
                    brackets=[[g[0][0],g[-1][1]] for g in deeper]
                    lo,hi=max(b[0] for b in brackets),min(b[1] for b in brackets)
                    if lo<hi:capacity=[lo,hi];aggregate=True
            if aggregate:agreement=False
        coarse_capacity=capacity
        refined=None
        if capacity and agreement:
            spacing=json.loads((ROOT/'config/followup-plan.json').read_text())['hosts'][host]['spatial_candidate']
            edges=[e for cohort in result['capacity']['matched_refinements'] if cohort['page']=='huge' and cohort['stride']==spacing
                for e in cohort['edges'] if capacity[0]<=e['lower_bytes']<e['upper_bytes']<=capacity[1]]
            if edges:
                first=min(edges,key=lambda e:(e['lower_bytes'],e['upper_bytes']))
                # An unusable earlier transition blocks narrowing to a later one.
                if first['same_cpu'] and first['huge_confirmed']:
                    refined=first;capacity=[refined['lower_bytes'],refined['upper_bytes']]
        table.append(dict(host=host,role=role,capacity_interval_bytes=capacity,capacity_candidate_bytes=None,
            line_candidate_bytes=None,ways_candidate=None,derived_sets=None,hit_median_native_ticks_per_access=None,
            unit=old['unit'],evidence='Overlapping BIC class boundaries in fully huge-backed dense and sparse curves, anchored to the independently observed first departure; extra spacing-specific classes retained separately',
            caveat='Conditional physical-role interpretation; broad brackets can include mixed residency/translation/replacement effects. Individual-load hit latency and separate per-level line size are not established by this model.',
            dense_sparse_brackets=brackets,dense_sparse_interval_overlap=agreement,deeper_mixed_class_envelope=aggregate,
            coarse_class_bracket_bytes=coarse_capacity,refined_departure_sources=refined['sources'] if refined else [],
            refinement_rule='Earliest IQR-separated >15% departure within a matched refinement cohort inside the agreed coarse timing-class bracket; narrow only if its endpoints share a core and full huge backing. Never skip an unusable early edge to select a later edge. Not a statistical confidence interval',
            sharing_scope='Exact domain unverified in Phase I',inclusion_exclusion='uncertain'))
    l2_support=collections.defaultdict(set)
    stronger=result.get('l2_confirmation',{});lower=stronger if stronger.get('upper_scrub_calibrated') else result.get('l2_specific',{})
    for stride in lower.get('strides',[]):
        for threshold in stride['fully_replicated_thresholds']:l2_support[threshold].add(stride['stride'])
    candidates=[];l2_row=table[1];band=l2_row['capacity_interval_bytes']
    if band and lower.get('upper_scrub_calibrated'):
        for ways,strides in sorted(l2_support.items()):
            period=min(strides);capacity=period*ways
            if len(strides)>=2 and band[0]<=capacity<=band[1]:
                candidates.append(dict(ways=ways,tested_period=period,capacity_candidate_bytes=capacity,
                    strides=sorted(strides),conditional_sets_if_spatial_granularity_is_l2_line_size=period//line if line and period%line==0 else None))
    l2_row['joint_l2_candidates']=candidates;l2_row['lower_conflict_source']=lower.get('plan_source')
    l2_row['way_inference_status']=('Conditional geometry supported' if len(candidates)==1 else
        'Upper-eviction calibration did not replicate' if not lower.get('upper_scrub_calibrated') else
        'No independent L2-like capacity bracket' if not band else
        'No exact threshold repeated across at least two strides with a capacity-consistent smallest tested period' if not candidates else
        'Multiple capacity-consistent geometries remain')
    if len(candidates)==1:
        c=candidates[0];l2_row.update(ways_candidate=c['ways'],capacity_candidate_bytes=c['capacity_candidate_bytes'],
            evidence=l2_row['evidence']+'; constant-upper-scrub threshold reproduced at >=2 strides, both scrub patterns and both new seeds',
            caveat=l2_row['caveat']+' Way/count geometry also assumes the tested smallest agreeing stride is fundamental and the odd upper scrub avoids target-lower-index conflicts.')
    return table


def l2_inference(rows,root):
    file=root/'l2-search.json'
    if not file.exists():return dict(status='pending',strides=[],calibration=[])
    plan=json.loads(file.read_text());relevant=[d for d in rows if d['family'] in ('l2_conflict','l2_upper_calibration')]
    def score(d):
        values=sorted(d['block_means']);return (values[4]+values[5])/2
    calibration=[dict(scrub_count=d['parameters']['upper_scrub_count'],mode=d['parameters']['mode'],
        statistics=d['statistics'],block_mean_range=[min(d['block_means']),max(d['block_means'])],
        median_of_block_means=score(d),full_huge_backing=min(d['measurement']['anon_huge_before_kib'],d['measurement']['anon_huge_after_kib'])*1024>=d['measurement']['mapped_bytes'],
        cpu=d['selected']['cpu'],qualification=d['qualification'],source=d['record_path']) for d in relevant if d['family']=='l2_upper_calibration']
    by_count={d['scrub_count']:d for d in calibration if d['mode']=='probe'}
    low=by_count.get(1);upper=by_count.get(plan['fixed_scrub_count']);extra=by_count.get(plan['fixed_scrub_count']+2)
    calibrated=bool(low and upper and extra and all(d['qualification']=='clean' and d['full_huge_backing'] for d in (low,upper,extra)) and
        len({d['cpu'] for d in (low,upper,extra)})==1 and upper['block_mean_range'][0]>low['block_mean_range'][1] and
        upper['median_of_block_means']>1.05*low['median_of_block_means'] and
        abs(extra['median_of_block_means']/upper['median_of_block_means']-1)<=.10)
    groups=collections.defaultdict(list)
    for d in relevant:
        p=d['parameters']
        if p['l2_label']=='heldout-refinement':groups[p['l2_candidate_stride'],p['upper_scrub_variant'],p['seed']].append(d)
    strides=[]
    for stride in plan['initial_strides']+plan['additional_strides']:
        replications=[]
        for (s,variant,seed),group in sorted(groups.items()):
            if s!=stride:continue
            clean=sorted([d for d in group if d['qualification']=='clean'],key=lambda d:d['parameters']['l2_candidate_count']);edges=[]
            for a,b in zip(clean,clean[1:]):
                na,nb=a['parameters']['l2_candidate_count'],b['parameters']['l2_candidate_count']
                same=a['selected']['cpu']==b['selected']['cpu']
                backing=all(min(d['measurement']['anon_huge_before_kib'],d['measurement']['anon_huge_after_kib'])*1024>=d['measurement']['mapped_bytes'] for d in (a,b))
                if nb==na+1 and score(b)>1.05*score(a) and min(b['block_means'])>max(a['block_means']):
                    edges.append(dict(threshold=nb,same_cpu=same,full_huge_backing=backing,
                        below=a['statistics'],above=b['statistics'],sources=[a['record_path'],b['record_path']]))
            replications.append(dict(variant=variant,seed=seed,edges=edges,
                sources=[d['record_path'] for d in group]))
        common=set.intersection(*[{e['threshold'] for e in r['edges'] if e['same_cpu'] and e['full_huge_backing']} for r in replications]) if len(replications)==4 else set()
        strides.append(dict(stride=stride,replications=replications,fully_replicated_thresholds=sorted(common)))
    return dict(status='measured',strides=strides,calibration=calibration,upper_scrub_calibrated=calibrated,
        upper_calibration_rule='Same CPU and full huge backing; scrubbed block means above one-address control with >5% center difference; adding two scrub addresses changes center by <=10%; all three runs clean',
        plan_source=str(file.relative_to(ROOT)),
        rule='Adjacent-address increase >5% in median of ten chronological block means, with nonoverlapping block-mean ranges; repeat on the same CPU within comparisons, full huge backing, both odd scrub patterns and both new seeds',
        limitation='Fixed upper pressure is intended to remove the L1 copy while avoiding the next target-index bit. Physical hashing, non-fundamental periods or a different lower indexing rule can defeat that construction. Conditional ways require independent capacity consistency as well.')


def strong_lower_inference(rows,root):
    file=root/'l2-confirmation.json'
    if not file.exists():return dict(status='pending',strides=[],calibrations=[],upper_scrub_calibrated=False)
    plan=json.loads(file.read_text());by_attempt={d['attempt']:d for d in rows}
    def center(d):
        b=sorted(d['block_means']);return (b[4]+b[5])/2
    def backed(d):
        m=d['measurement'];return min(m['anon_huge_before_kib'],m['anon_huge_after_kib'])*1024>=m['mapped_bytes']
    calibrations=[]
    for group in plan['calibrations']:
        accepted=next((a for a in group['attempts'] if a['same_core_clean']),None)
        g=[by_attempt.get(ref) for ref in accepted['records']] if accepted else []
        good=len(g)==3 and all(d and d['qualification']=='clean' and backed(d) for d in g)
        failures=[];checks={}
        if good:
            a,b,c=g
            checks=dict(same_cpu=len({d['selected']['cpu'] for d in g})==1,
                block_ranges_separated=min(b['block_means'])>max(a['block_means']),
                scrub_over_control_ratio=center(b)/center(a),extra_scrub_relative_change=abs(center(c)/center(b)-1))
            if not checks['same_cpu']:failures.append('core changed within calibration')
            if not checks['block_ranges_separated']:failures.append('control and scrub block-mean ranges overlap')
            if checks['scrub_over_control_ratio']<=1.05:failures.append('scrub effect does not exceed the declared 5 percent threshold')
            if checks['extra_scrub_relative_change']>.10:failures.append('four extra scrub addresses change the center by more than 10 percent')
        else:failures.append('missing, noisy, mixed-core or incompletely huge-backed calibration cohort')
        good=good and not failures
        calibrations.append(dict(variant=group['variant'],seed=group['seed'],supports=good,failures=failures,checks=checks,
            centers=[center(d) for d in g if d],sources=[d['record_path'] for d in g if d]))
    strides=[]
    for stride in sorted({r['stride'] for r in plan['refinements']}):
        replications=[]
        for ref in [r for r in plan['refinements'] if r['stride']==stride]:
            g=[by_attempt.get(attempt) for attempt in ref['records']]
            g=sorted([d for d in g if d and d['qualification']=='clean'],key=lambda d:d['parameters']['l2_candidate_count'])
            edges=[]
            for a,b in zip(g,g[1:]):
                na,nb=a['parameters']['l2_candidate_count'],b['parameters']['l2_candidate_count']
                if nb==na+1 and center(b)>1.05*center(a) and min(b['block_means'])>max(a['block_means']):
                    edges.append(dict(threshold=nb,same_cpu=a['selected']['cpu']==b['selected']['cpu'],
                        full_huge_backing=backed(a) and backed(b),sources=[a['record_path'],b['record_path']]))
            replications.append(dict(variant=ref['variant'],seed=ref['seed'],edges=edges))
        common=set.intersection(*[{e['threshold'] for e in r['edges'] if e['same_cpu'] and e['full_huge_backing']} for r in replications]) if len(replications)==4 else set()
        strides.append(dict(stride=stride,replications=replications,fully_replicated_thresholds=sorted(common)))
    return dict(status='measured',selected_scrub_count=plan['selected_scrub_count'],calibrations=calibrations,strides=strides,
        upper_scrub_calibrated=len(calibrations)==4 and all(c['supports'] for c in calibrations),
        plan_source=str(file.relative_to(ROOT)),search_rule=plan['rule'],
        limitation='Timing-calibrated upper scrub and repeated virtual-address conflict relationships support conditional geometry only; physical hashing and fundamental indexing periods remain unverified.')


def host_analysis(host):
    root=ROOT/'machines'/host/'followup-v1';rows=[];issues=[];unsuccessful=[];attempt_count=0
    for family in ('spatial_alignment','spatial_confirmation','capacity_control','capacity_refinement','capacity_regular','empirical_conflict','cross_core_reload','same_core_reload','target_hot','followup_overhead','followup_hot_batch','l2_conflict','l2_upper_calibration','l2_saturation','l2_strong_conflict'):
        for base in sorted((root/family).glob('*')):
            if not base.is_dir():continue
            attempts=[]
            for path in sorted(base.glob('attempt-*/run.json')):
                attempt_count+=1
                try:d,errors=verify(path,root)
                except Exception as e:d=json.loads(path.read_text());errors=[str(e)]
                if errors:unsuccessful.append(dict(record=str(path.relative_to(ROOT)),errors=errors))
                elif d.get('qualification')=='noisy':unsuccessful.append(dict(record=str(path.relative_to(ROOT)),flags=d.get('flags')))
                if not errors:attempts.append(d)
            clean=[d for d in attempts if d['qualification']=='clean']
            selected=(clean or attempts)
            if selected:rows.append(sorted(selected,key=lambda d:d['started'])[0])
            else:issues.append(dict(point=str(base.relative_to(ROOT)),reason='No intact complete distribution'))
    finished={stage:json.loads((root/(stage+'-finished.json')).read_text()) if (root/(stage+'-finished.json')).exists() else None for stage in ('spatial','capacity','confirm','conflict','cross','l2','l2confirm')}
    missing=[s for s,d in finished.items() if d is None]
    build_issues=[]
    try:
        compile_record=json.loads((root/'build/compile.json').read_text())
        if compile_record['returncode'] or '-O0' not in compile_record['command']:build_issues.append('native -O0 build not verified')
        dis=(root/'build/followup_bench.dis').read_text()
        if '<chase>:' not in dis:build_issues.append('dependent loop missing from native disassembly')
        digest=hashlib.sha256((sha(root/'build/cache_bench.c')+sha(root/'build/followup_bench.c')).encode()).hexdigest()
        gate=json.loads((root/'smoke-passed.json').read_text())
        if gate['source_sha256']!=digest or gate['points']<8:build_issues.append('exact-source native smoke gate mismatch')
        timer=json.loads((root/'timer-verification.json').read_text())
        if not timer['passed']:build_issues.append('extension timer overhead calibration failed/noisy')
    except (OSError,KeyError,ValueError) as e:build_issues.append('pending build/smoke/timer verification: '+str(e))
    if not missing:
        issues.extend(dict(reason=x) for x in build_issues)
        plan=json.loads((ROOT/'config/followup-plan.json').read_text())['hosts'][host]
        expected_spatial={(w,a,o) for w in plan['spatial_footprints'] for a in (0,24) for o in range(8,137,8)}
        actual_spatial={(d['parameters']['bytes'],d['parameters']['align'],d['parameters']['offset']) for d in rows if d['family']=='spatial_alignment'}
        expected_coarse={(1024*2**i,page,stride) for i in range(19) for page,stride in [('base',8),('huge',8),('huge',plan['spatial_candidate'])]}
        actual_coarse={(d['parameters']['bytes'],d['parameters']['page'],d['parameters']['stride']) for d in rows if d['family']=='capacity_control'}
        expected_cross={(w,seed,offset) for w in plan['cross_footprints'] for seed in (5922026,5922027) for offset in (0,1)}
        actual_cross={(d['parameters']['bytes'],d['parameters']['seed'],d['parameters']['offset']) for d in rows if d['family']=='cross_core_reload'}
        for family,wanted,actual in [('spatial',expected_spatial,actual_spatial),('capacity',expected_coarse,actual_coarse),('cross',expected_cross,actual_cross)]:
            if wanted-actual:issues.append(dict(reason='missing planned '+family+' configurations',configurations=sorted(wanted-actual)))
        refinement=json.loads((root/'capacity-refinement-plan.json').read_text())['edges']
        expected_refine={(lo+(hi-lo)*i//8,page,lo,hi) for lo,hi in refinement for i in range(9) for page in ('base','huge')}
        actual_refine={(d['parameters']['bytes'],d['parameters']['page'],*d['parameters']['comparison_interval']) for d in rows if d['family']=='capacity_refinement'}
        if expected_refine-actual_refine:issues.append(dict(reason='missing adaptive refinements',configurations=sorted(expected_refine-actual_refine)))
        l2=json.loads((root/'l2-search.json').read_text())
        expected_l2={(s,n) for s in l2['initial_strides']+l2['additional_strides'] for n in l2['coarse_counts']}
        actual_l2={(d['parameters']['l2_candidate_stride'],d['parameters']['l2_candidate_count']) for d in rows if d['family']=='l2_conflict' and d['parameters']['l2_label']=='coarse'}
        if expected_l2-actual_l2:issues.append(dict(reason='missing L2 coarse configurations',configurations=sorted(expected_l2-actual_l2)))
        expected_l2_ref={(r['stride'],r['variant'],r['seed'],n) for r in l2['refinements'] for n in r['counts']}
        actual_l2_ref={(d['parameters']['l2_candidate_stride'],d['parameters']['upper_scrub_variant'],d['parameters']['seed'],d['parameters']['l2_candidate_count']) for d in rows if d['family']=='l2_conflict' and d['parameters']['l2_label']=='heldout-refinement'}
        if expected_l2_ref-actual_l2_ref:issues.append(dict(reason='missing L2 held-out refinements',configurations=sorted(expected_l2_ref-actual_l2_ref)))
        stronger=json.loads((root/'l2-confirmation.json').read_text())
        expected_strong={(r['stride'],r['variant'],r['seed'],n) for r in stronger['refinements'] for n in r['counts']}
        actual_strong={(d['parameters']['l2_candidate_stride'],d['parameters']['upper_scrub_variant'],d['parameters']['seed'],d['parameters']['l2_candidate_count']) for d in rows if d['family']=='l2_strong_conflict'}
        if expected_strong-actual_strong:issues.append(dict(reason='missing stronger-scrub refinements',configurations=sorted(expected_strong-actual_strong)))
    result=dict(host=host,time=now(),verified_points=len(rows),noisy_points=sum(d['qualification']=='noisy' for d in rows),
        attempts=attempt_count,issues=issues,build_issues=build_issues,unsuccessful=unsuccessful,missing_stages=missing,stage_records=finished,
        acquisition_complete=not issues and not missing,spatial=spatial_inference(rows),spatial_confirmation=confirmation(rows,root),
        capacity=capacity_inference(rows),prefetch=prefetch_controls(rows),conflict=conflict_inference(rows,root),cross_core=cross_inference(rows),l2_specific=l2_inference(rows,root),l2_confirmation=strong_lower_inference(rows,root))
    result['revised_cache_table']=revised_cache_table(result)
    OUT.mkdir(parents=True,exist_ok=True);write_json(OUT/(host+'-inference.json'),result)
    write_json(OUT/(host+'-verified-records.json'),rows)
    return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--hosts',nargs='+');ap.add_argument('--final',action='store_true');ap.add_argument('--jobs',type=int,default=2);args=ap.parse_args()
    allowed=json.loads((ROOT/'config/phase1.json').read_text())['hosts'];hosts=args.hosts or allowed
    if set(hosts)-set(allowed):ap.error('Unknown host')
    analysis_digest=sha(Path(__file__));policy_digest=sha(ROOT/'config/followup-inference-policy.json')
    with concurrent.futures.ProcessPoolExecutor(max_workers=max(1,min(args.jobs,len(hosts)))) as pool:
        results=dict(zip(hosts,pool.map(host_analysis,hosts)))
    if analysis_digest!=sha(Path(__file__)) or policy_digest!=sha(ROOT/'config/followup-inference-policy.json'):
        raise SystemExit('Analysis source or inference policy changed during verification; rerun with stable sources')
    state=dict(time=now(),phase='I timing only',hosts=results,command=[sys.executable]+sys.argv,
        analysis_source_sha256=analysis_digest,inference_policy_sha256=policy_digest,
        complete=set(hosts)==set(allowed) and all(d['acquisition_complete'] for d in results.values()))
    write_json(OUT/'verification.json',state)
    allrows=[]
    for host in hosts:
        for d in json.loads((OUT/(host+'-verified-records.json')).read_text()):
            allrows.append(dict(host=host,family=d['family'],qualification=d['qualification'],cpu=d['selected']['cpu'],
                bytes=d['parameters']['bytes'],stride=d['parameters']['stride'],offset=d['parameters']['offset'],align=d['parameters']['align'],
                page=d['parameters']['page'],batch=d['parameters']['batch'],seed=d['parameters']['seed'],
                l2_candidate_stride=d['parameters'].get('l2_candidate_stride'),l2_candidate_count=d['parameters'].get('l2_candidate_count'),
                raw_unit=d['measurement']['unit'],unit=d['statistic_unit'],
                timed_loads=d['parameters'].get('timed_loads',d['parameters']['batch']),
                raw=d['raw_path'],record=d['record_path'],**d['statistics']))
    if allrows:
        with open(OUT/'statistics.csv','w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(allrows[0]));writer.writeheader();writer.writerows(allrows)
    latency=[]
    for host,result in results.items():
        for model in result['capacity']['plateau_models']:
            for segment in model['segments']:
                r=segment['representative'];transition=segment.get('transition_from_previous',{})
                latency.append(dict(host=host,stride=model['stride'],class_index=segment['class_index'],
                    model_class_count=model['chosen_classes'],class_working_set_range=json.dumps(segment['working_set_range']),
                    class_median_range=json.dumps(segment['median_timing_range']),representative_bytes=r['working_set_bytes'],
                    cpu=r['cpu'],unit=r['unit'],source=r['source'],
                    previous_class_same_cpu=transition.get('same_cpu'),
                    incremental_median_penalty=transition.get('incremental_median_penalty'),**r['statistics']))
    if latency:
        with open(OUT/'latency-classes.csv','w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(latency[0]));writer.writeheader();writer.writerows(latency)
    table=[]
    for result in results.values():
        for row in result['revised_cache_table']:
            table.append({k:json.dumps(v) if isinstance(v,(list,dict)) else v for k,v in row.items()})
    if table:
        fields=list(dict.fromkeys(k for row in table for k in row))
        with open(OUT/'revised-cache-table.csv','w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(table)
    print(json.dumps(dict(complete=state['complete'],hosts={h:dict(points=d['verified_points'],noisy=d['noisy_points'],missing=d['missing_stages'],issues=len(d['issues'])) for h,d in results.items()})),flush=True)
    if args.final and not state['complete']:raise SystemExit('Final follow-up report blocked: acquisition or verification incomplete')

if __name__=='__main__':main()
