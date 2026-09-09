#!/usr/bin/env python3
"""Recompute all statistics from raw samples, plot evidence, and gate final Phase I.
No source of cache answers is accessed. All inferences are conservative candidates.
"""
import argparse
import csv
import json
import math
import os
from pathlib import Path
import sys
import time
from common import now, read_raw, sha, stats, statistics_agree, utilization, write_json

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = ('capacity', 'line_size', 'associativity', 'inclusion_policy', 'latency', 'software_metric', 'timer', 'loop')
# Course-provided identification only (specification Table 1), not cache answers.
COURSE_MODELS=dict(sunbird='2 × Xeon E5-2680 v3',thunderbird='Ampere Q80-30',skylark='2 × AMD EPYC 7532',artemisia='2 × Xeon Gold 5420+',charnwood='Core i7-6700',crux='Core i7-9700',ookay='Core i7-7700',upgrade='Core i7-8700')


def ns_scale(measurement):
    if measurement['unit']=='monotonic_raw_ns':return 1.0,'CLOCK_MONOTONIC_RAW nanoseconds'
    if measurement['unit']=='CNTVCT_ticks':
        frequency=measurement.get('counter_frequency',0);method='recorded CNTFRQ_EL0 frequency'
    else:
        frequency=measurement.get('empirical_ticks_per_second',0);method='per-run timer/CLOCK_MONOTONIC_RAW calibration; approximate'
    return (1e9/frequency if frequency>0 else None),method


def rows_for(host, verify=True, phase="full"):
    root = ROOT / 'machines' / host / phase
    selected, attempts, problems = [], [], []
    by_point={}
    for path in sorted(root.glob('*/*/attempt-*/run.json')):
        d = json.loads(path.read_text())
        d['record_path'] = str(path.relative_to(ROOT))
        attempts.append(d)
        by_point.setdefault(path.parent.parent,[]).append(d)
    # Preferred evidence is the runner's quality-passing result. If none exists,
    # a deterministic first complete noisy attempt remains usable as *noisy data*.
    # Selection never ranks latency values, never edits raw samples, and preserves
    # every alternate attempt. Noisy points cannot establish confident boundaries.
    fatal={'affinity mismatch','major page faults during measurement','timer resolution: more than 1 percent zero intervals'}
    for base in sorted(by_point):
        done=base/'complete.json'
        if done.exists():
            candidate=json.loads(done.read_text())
            candidate['record_path']=str(done.relative_to(ROOT))
            candidate['qualification']='verified_clean'
        else:
            candidates=[d for d in by_point[base] if d.get('status')=='noisy' and d.get('raw') and not fatal.intersection(d.get('flags',[]))]
            if not candidates:
                problems.append(dict(path=str(base.relative_to(ROOT)),error='configuration has no complete, correctly pinned, trustworthy-timer raw distribution'))
                continue
            candidate=dict(sorted(candidates,key=lambda d:d['started'])[0])
            candidate['qualification']='verified_noisy'
            candidate['qualification_reason']='First chronological complete noisy attempt after no quality-passing result; all flags retained; excluded from confident inference'
        d=candidate
        raw=root/d['raw']
        try:
            if sha(raw)!=d['raw_sha256']:raise ValueError('raw SHA256 mismatch')
            if d['exact_raw_count']<1000000:raise ValueError('fewer than 1,000,000 timed samples')
            idle_path=root/d['attempt']/'idle.json'
            idle=json.loads(idle_path.read_text())
            if idle['selected']!=d['selected']:raise ValueError('selected-core record differs from idle evidence')
            if len(idle['evidence'])<2 or not 0<=idle['threshold']<=.05:
                raise ValueError('idle evidence does not meet the two-window 5-percent policy')
            if d['selected']['cpu'] not in d['selected']['siblings']:
                raise ValueError('selected CPU absent from its recorded sibling group')
            from datetime import datetime
            for window in idle['evidence']:
                if (datetime.fromisoformat(window['end'])-datetime.fromisoformat(window['start'])).total_seconds()<.99:
                    raise ValueError('idle observation window shorter than one second')
                measured=utilization(window['before'],window['after'])
                if any(measured.get(str(cpu),1)>idle['threshold'] for cpu in d['selected']['siblings']):
                    raise ValueError('raw activity evidence does not establish idle core and SMT siblings')
            if d['measurement']['unit'] not in ('TSC_ticks','CNTVCT_ticks','monotonic_raw_ns'):
                raise ValueError('unrecognized or misleading timer unit')
            if d['measurement']['cpu']!=d['measurement']['final_cpu'] or d['measurement']['cpu']!=d['selected']['cpu']:
                raise ValueError('affinity mismatch')
            if d['measurement']['major_faults']:
                raise ValueError('major page faults during measurement')
            expected_source=ROOT/'src'/('page_control.c' if phase=='page_control' else 'cache_bench.c')
            if d['source_sha256']!=sha(expected_source):raise ValueError('producing benchmark source differs from analyzed source')
            if verify:
                values=read_raw(raw,d['measurement']['little_endian'])
                divisor=1 if d['parameters']['mode'] in ('overhead','reload') else d['parameters']['batch']
                actual=stats(values,divisor)
                if actual['n']!=d['exact_raw_count'] or actual['n']!=d['parameters']['samples'] or actual['n']!=d['measurement']['samples']:
                    raise ValueError('raw count disagrees with invocation or measurement metadata')
                if not statistics_agree(actual,d['statistics']):raise ValueError('recomputed distribution differs beyond floating-point tolerance')
                d['stddev_rounding_difference']=actual['stddev']-d['statistics']['stddev']
                d['statistics']=actual
            d['raw_path']=str(raw.relative_to(ROOT));selected.append(d)
        except Exception as e:problems.append(dict(path=str(base),error=str(e)))
    return selected, attempts, problems


def coverage_issues(rows, root, cfg):
    """Fail closed on a missing planned configuration, even if a finish marker exists."""
    issues=[]
    calibration=root/'batch-calibration.json'
    if not calibration.exists():issues.append('missing batch calibration')
    else:
        cal=json.loads(calibration.read_text())
        if not cal['passed'] or cal['trials'][-1]['overhead_fraction']>.05:
            issues.append('primary batch timer overhead exceeds 5 percent')
        # A recalibrated resume can leave valid earlier-batch controls. Preserve
        # them, but require the complete planned suite at the final chosen batch.
        rows=[r for r in rows if r['family'] not in ('capacity','line_size','associativity') or r['parameters']['batch']==cal['chosen_batch']]
    capacity={(r['parameters']['bytes'],r['parameters']['order']) for r in rows if r['family']=='capacity'}
    n=cfg['min_bytes']
    while n <= cfg['max_bytes']:
        for order in ('random','regular'):
            if (n,order) not in capacity: issues.append('missing coarse capacity '+str((n,order)))
        n*=2
    candidates=root/'candidate-boundaries.json'
    if candidates.exists():
        for lo,hi in json.loads(candidates.read_text())['intervals']:
            for i in range(1,8):
                size=(lo+(hi-lo)*i//8)//8*8
                for order in ('random','regular'):
                    if (size,order) not in capacity:issues.append('missing refined capacity '+str((size,order)))
    else:issues.append('missing adaptive boundary plan')
    conflicts={(r['parameters']['stride'],r['parameters']['bytes']//r['parameters']['stride']) for r in rows if r['family']=='associativity'}
    for stride in (4096,16384,65536,262144):
        for n in range(2,25):
            if (stride,n) not in conflicts:issues.append('missing conflict '+str((stride,n)))
    offsets=set(list(range(8,137,8))+[184,192,200,248,256,264])
    spatial={}
    for r in rows:
        if r['family']=='line_size':spatial.setdefault(r['parameters']['bytes'],set()).add(r['parameters']['offset'])
    if not spatial:issues.append('missing spatial sweep')
    intervals=json.loads(candidates.read_text())['intervals'] if candidates.exists() else []
    first=min([b for a,b in intervals] or [65536])
    expected_spatial={min(cfg['max_bytes'],first*8),min(cfg['max_bytes'],first*32)}
    if expected_spatial-set(spatial):issues.append('missing spatial footprints '+str(sorted(expected_spatial-set(spatial))))
    reloads={(r['parameters']['bytes'],r['parameters']['batch']) for r in rows if r['family']=='inclusion_policy'}
    for size in set([1024,cfg['max_bytes']]+[b for a,b in intervals]):
        for pressure in (32,512,2048):
            if (size,pressure) not in reloads:issues.append('missing reload condition '+str((size,pressure)))
    for size,found in spatial.items():
        if offsets-found:issues.append('missing spatial offsets at '+str(size)+': '+str(sorted(offsets-found)))
    metric={r['parameters']['bytes'] for r in rows if r['family']=='software_metric'}
    if {1024,1048576,cfg['max_bytes']}-metric:issues.append('missing software-metric calibration/workload')
    return issues


def boundaries(rows):
    data = sorted([r for r in rows if r['family']=='capacity' and r['parameters']['order']=='random' and r['qualification']=='verified_clean' and r.get('analysis_role')!='alternate batch control'], key=lambda r:r['parameters']['bytes'])
    # Candidate local edges. Do not round to a known cache geometry.
    proposals=[]
    for i,(a,b) in enumerate(zip(data,data[1:])):
        x,y = a['statistics'],b['statistics']
        ratio=y['median']/max(x['median'],1e-12)
        if ratio > 1.12 and y['q1'] > x['q3']:
            proposals.append(dict(lower_bytes=a['parameters']['bytes'],upper_bytes=b['parameters']['bytes'],
                ratio=ratio,below=x,above=y,below_record=a['record_path'],above_record=b['record_path'],
                unit=a['measurement']['unit']+'/access',status='candidate effective transition; mapping to a cache level is uncertain'))
    # Adjacent edges form a broad transition region rather than many invented levels.
    groups=[]
    for p in proposals:
        if groups and p['lower_bytes'] <= groups[-1]['upper_bytes']:
            groups[-1]['upper_bytes']=p['upper_bytes']
            groups[-1]['above']=p['above']
            groups[-1]['above_record']=p['above_record']
            groups[-1]['status']='broad candidate transition; no exact capacity claimed'
        else:
            groups.append(dict(p))
    by_record={r['record_path']:r for r in data}
    for group in groups:
        a=by_record[group['below_record']]['selected'];b=by_record[group['above_record']]['selected']
        group['endpoint_cpus']=[a['cpu'],b['cpu']]
        group['same_logical_cpu']=a['cpu']==b['cpu']
        group['same_socket_and_numa']=(a['socket'],a['node'])==(b['socket'],b['node'])
        group['ratio']=group['above']['median']/group['below']['median']
        group['cross_run_caveat']='Sequential runs may differ in frequency, placement and interference; changed cores/domains add a confound. This is exploratory candidate detection, not a change-point confidence interval.'
    return groups


def spatial_inference(rows):
    groups={}
    for r in rows:
        if r['family']=='line_size' and r['qualification']=='verified_clean' and r.get('analysis_role')!='alternate batch control': groups.setdefault(r['parameters']['bytes'],[]).append(r)
    candidates=[]
    for w,series in groups.items():
        series.sort(key=lambda r:r['parameters']['offset'])
        for a,b in zip(series,series[1:]):
            if b['statistics']['median'] > 1.12*a['statistics']['median'] and b['statistics']['q1'] > a['statistics']['q3']:
                candidates.append(dict(footprint=w,offset_lower=a['parameters']['offset'],offset_upper=b['parameters']['offset'],
                    sources=[a['record_path'],b['record_path']]))
    return dict(status='candidate spatial granularity only; distinct line sizes per cache level not established',candidates=candidates,
        limitation='Random 512-byte blocks have fixed allocation and node count; physical line occupancy changes with offset. Prefetching and residency can obscure or imitate a boundary.')


def conflict_inference(rows):
    groups={}
    for r in rows:
        if r['family']=='associativity' and r['qualification']=='verified_clean' and r.get('analysis_role')!='alternate batch control': groups.setdefault(r['parameters']['stride'],[]).append(r)
    edges=[];bounds=[]
    for stride,series in sorted(groups.items()):
        series.sort(key=lambda r:r['parameters']['bytes'])
        for a,b in zip(series,series[1:]):
            n=a['parameters']['bytes']//stride
            if b['statistics']['median'] > 1.18*a['statistics']['median'] and b['statistics']['q1'] > a['statistics']['q3']:
                next_n=b['parameters']['bytes']//stride
                if next_n==n+1:edges.append(dict(candidate_resident_addresses=n,stride=stride,sources=[a['record_path'],b['record_path']]))
                else:bounds.append(dict(resident_addresses_lower=n,resident_addresses_upper=next_n-1,stride=stride,sources=[a['record_path'],b['record_path']],reason='Intermediate configurations are missing or noisy; no exact threshold inferred'))
    return dict(status='effective conflict thresholds; no verified per-level associativity',candidates=edges,bounded_candidates=bounds,
        limitation='Only virtual low bits controlled. Physical indexing, page translation, replacement, and slice hashing are unresolved. No way count or derived set count is manufactured.')


def l1_candidate(rows, spatial, conflict):
    clean=sorted([r for r in rows if r['family']=='capacity' and r['parameters']['order']=='random' and r['qualification']=='verified_clean' and r.get('analysis_role')!='alternate batch control'],key=lambda r:r['parameters']['bytes'])
    result=dict(status='unresolved',line_bytes=None,ways=None,capacity_interval_bytes=None,geometry=None,
        caveat='Conditional L1 interpretation of the smallest timing class. All numerical candidates come from measured plateaus and repeated spatial/conflict edges; no specification value is used.')
    if len(clean)<4 or clean[0]['parameters']['bytes']>4096:return result
    initial=clean[:3]
    centers=sorted(r['statistics']['median'] for r in initial)
    if centers[-1]>1.2*centers[0]:
        result['reason']='Small-footprint centers differ by over 20%; cross-run drift prevents a stable L1 baseline';return result
    reference=centers[1]
    last=None;depart=None
    for r in clean:
        if r['statistics']['median']<=reference*1.10:
            last=r
        elif last is not None:
            depart=r;break
    if last and depart:
        result['capacity_interval_bytes']=[last['parameters']['bytes'],depart['parameters']['bytes']]
        result['capacity_sources']=[last['record_path'],depart['record_path']]
        result['capacity_endpoint_cpus']=[last['selected']['cpu'],depart['selected']['cpu']]
        result['capacity_rule']='First departure by >10% from median of first three small-footprint centers; interval, not a rounded cache answer'
        result['hit_class_statistics']=initial[0]['statistics'];result['unit']=initial[0]['measurement']['unit']+'/access'
        result['next_class_statistics']=depart['statistics']
        scale,method=ns_scale(initial[0]['measurement'])
        result['hit_class_median_ns']=initial[0]['statistics']['median']*scale if scale else None
        result['nanosecond_conversion']=method
    spatial_groups={}
    for c in spatial['candidates']:
        if c['offset_upper']-c['offset_lower']==8:
            spatial_groups.setdefault(c['footprint'],set()).add(c['offset_upper'])
    if len(spatial_groups)>=2:
        shared=set.intersection(*spatial_groups.values())
        if len(shared)==1:
            result['line_bytes']=next(iter(shared))
            result['line_rule']='Unique spatial edge shared by at least two fixed-footprint sweeps; 8-byte offset resolution; transfer-granularity candidate'
    support={}
    for c in conflict['candidates']:support.setdefault(c['candidate_resident_addresses'],set()).add(c['stride'])
    repeatable={n:sorted(strides) for n,strides in support.items() if len(strides)>=3}
    if len(repeatable)==1:
        ways,strides=next(iter(repeatable.items()));result['ways']=ways;result['conflict_strides']=strides
        result['ways_rule']='Unique conflict threshold reproduced at three or more strides; conditional virtual-index interpretation'
    if result['line_bytes'] and result['ways'] and result['capacity_interval_bytes']:
        B,A=result['line_bytes'],result['ways'];lo,hi=result['capacity_interval_bytes']
        period=min(result['conflict_strides']);C=A*period
        sets=C/(A*B)
        result['derived_set_interval']=[lo/(A*B),hi/(A*B)]
        if lo<=C<=hi and sets.is_integer():
            result['geometry']=dict(capacity_candidate_bytes=C,line_candidate_bytes=B,ways_candidate=A,derived_sets=int(sets),tested_index_period_bytes=period,
                status='internally consistent candidate; smallest tested agreeing stride may not be fundamental; no rounding applied')
            result['status']='timing-supported, internally consistent L1 candidate with capacity interval'
        else:result['status']='independent candidates do not establish a consistent exact geometry; retain interval and revisit'
    return result


def estimator(rows, host):
    data=sorted([r for r in rows if r['family']=='software_metric'],key=lambda r:r['parameters']['bytes'])
    if len(data)!=3 or any(r['qualification']!='verified_clean' for r in data):
        return dict(status='unavailable: calibration/workload incomplete or noisy')
    hot, target, cold=data
    upper=hot['statistics']['p95']; lower=cold['statistics']['p05']
    if upper >= lower:
        return dict(status='unresolved: hot/cold calibration distributions overlap',hot_p95=upper,cold_p05=lower,
                    sources=[r['record_path'] for r in data])
    threshold=(upper+lower)/2
    raw=read_raw(ROOT/target['raw_path'],target['measurement']['little_endian'])
    hits=sum(v<=threshold for v in raw); n=len(raw); rate=hits/n
    # Wilson interval is a binomial diagnostic; correlated chain samples can violate independence.
    z=1.96; den=1+z*z/n; center=(rate+z*z/(2*n))/den
    radius=z*math.sqrt(rate*(1-rate)/n+z*z/(4*n*n))/den
    blocks=[sum(v<=threshold for v in raw[i:i+10000])/len(raw[i:i+10000]) for i in range(0,n,10000)]
    return dict(status='timing-classified cache-residency proxy; not a validated hardware hit rate',
                classified_hits=hits,total_timed_accesses=n,estimate=rate,threshold_raw_ticks=threshold,
                threshold_sensitivity_rate_range=[sum(v<=upper for v in raw)/n,sum(v<=lower for v in raw)/n],
                threshold_sensitivity_limits_raw_ticks=[upper,lower],
                wilson_95_independent_sample_assumption=[center-radius,center+radius],block_rate_range=[min(blocks),max(blocks)],
                standardized_workload_bytes=1048576,unit=target['measurement']['unit'],sources=[r['record_path'] for r in data],
                calibration_and_workload_cpus=[r['selected']['cpu'] for r in data],same_logical_cpu=len({r['selected']['cpu'] for r in data})==1,
                limitations='Single-load timer overhead/quantization; smallest/largest footprints are empirical proxies, not PMU-confirmed classes. Adjacent samples are correlated. Wilson intervals omit calibration/classification error; threshold-sensitivity and block ranges expose additional uncertainty. Phase-II validation not performed.')


def level_table(info):
    """Requested cache roles, with unresolved assignments explicitly represented."""
    c=info['l1_candidate'];g=c.get('geometry') or {};bounds=c.get('capacity_interval_bytes') or ['','']
    hit=c.get('hit_class_statistics',{}).get('median','');nxt=c.get('next_class_statistics',{}).get('median','')
    common=dict(host=info['host'],sharing_scope=info['sharing_scope'],inclusion_exclusion='uncertain')
    result=[dict(common,level='L1D candidate',size_lower_bytes=bounds[0],size_upper_bytes=bounds[1],
        line_size=c.get('line_bytes') or 'unresolved',associativity=c.get('ways') or 'unresolved',
        derived_sets=g.get('derived_sets','unresolved'),hit_latency_median=hit,next_level_latency_median=nxt,
        incremental_difference=nxt-hit if hit!='' and nxt!='' else '',unit=c.get('unit',''),
        status=c['status']+'; next-class latency is the first measured departure, not a pure L2-hit latency')]
    for level in ('L2 role unassigned','LLC role unassigned'):
        result.append(dict(common,level=level,size_lower_bytes='',size_upper_bytes='',line_size='unresolved',
            associativity='unresolved',derived_sets='unresolved',hit_latency_median='',next_level_latency_median='',
            incremental_difference='',unit='',status='Measured effective transitions are listed separately; cache/translation separation and physical level assignment remain uncertain'))
    return result


def plot_host(host, rows, output, families=FAMILIES):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':12,'axes.grid':False,'axes.spines.top':False,'axes.spines.right':False,
                         'figure.facecolor':'white','axes.facecolor':'white','lines.linewidth':1.7,'svg.fonttype':'none'})
    paths=[]
    for family in families:
        selected=[r for r in rows if r['family']==family]
        if not selected: continue
        fig,ax=plt.subplots(figsize=(8.5,5.2))
        groups={}
        for r in selected:
            p=r['parameters']
            if family=='capacity': key=p['order']+'; N='+str(p['batch']); x=p['bytes']
            elif family=='line_size': key='allocation '+str(p['bytes'])+' B'; x=p['offset']
            elif family=='associativity': key='stride '+str(p['stride'])+' B'; x=p['bytes']//p['stride']
            elif family=='inclusion_policy': key='pressure '+str(p['batch'])+' loads'; x=p['bytes']
            else: key='batch '+str(p['batch']); x=p['bytes']
            groups.setdefault(key,[]).append((x,r))
        for idx,(key,series) in enumerate(sorted(groups.items())):
            series.sort(key=lambda x:x[0]); x=[a for a,b in series]; y=[b['statistics']['median'] for a,b in series]
            ax.plot(x,y,marker=['o','s','^','D','v'][idx%5],color=str(min(.65,idx*.18)),label=key)
            ax.fill_between(x,[b['statistics']['q1'] for a,b in series],[b['statistics']['q3'] for a,b in series],color='0.7',alpha=.25)
            noisy=[(a,b) for a,b in series if b['qualification']=='verified_noisy']
            if noisy: ax.scatter([a for a,b in noisy],[b['statistics']['median'] for a,b in noisy],marker='x',s=80,color='black',label=key+' noisy')
        if family in ('capacity','inclusion_policy','latency','software_metric','page_control'): ax.set_xscale('log',base=2)
        if family in ('capacity','page_control'): ax.set_yscale('log',base=2)
        ax.set_xlabel({'line_size':'Paired-access byte offset','associativity':'Addresses in conflict candidate group'}.get(family,'Allocation / address span (bytes)'))
        suffix='/reload' if family=='inclusion_policy' else '/interval' if family=='timer' else '/access' if family!='loop' else '/loop iteration'
        ax.set_ylabel(selected[0]['measurement']['unit']+suffix+(' (batch averages)' if family in ('capacity','line_size','associativity','latency','page_control') else ''))
        ax.set_title(host+' — '+family.replace('_',' ')); ax.legend(fontsize=9)
        fig.tight_layout()
        base=output/(host+'-'+family)
        fig.savefig(str(base)+'.svg'); fig.savefig(str(base)+'.pdf'); fig.savefig(str(base)+'.png',dpi=160); plt.close(fig)
        # All points get distribution box plots in paginated groups; no hand-picked survivors.
        sorted_rows=sorted(selected,key=lambda r:(r['parameters']['bytes'],r['parameters']['stride'],r['parameters']['offset'],r['parameters']['order']))
        for page,start in enumerate(range(0,len(sorted_rows),18)):
            page_rows=sorted_rows[start:start+18]
            boxes=[]; labels=[]
            for r in page_rows:
                s=r['statistics'];p=r['parameters']
                boxes.append(dict(med=s['median'],q1=s['q1'],q3=s['q3'],whislo=s['p05'],whishi=s['p95'],fliers=[]))
                label=str(p['offset'] if family=='line_size' else p['bytes']//p['stride'] if family=='associativity' else p['bytes'])
                detail=('W='+str(p['bytes']) if family=='line_size' else 's='+str(p['stride']) if family=='associativity' else 'N='+str(p['batch']) if family in ('inclusion_policy','latency') else p['order']+' N='+str(p['batch']) if family=='capacity' else p['order'])
                labels.append(label+'\n'+detail+(' *noisy' if r['qualification']=='verified_noisy' else ''))
            fig,ax=plt.subplots(figsize=(10,5.5)); ax.bxp(boxes,showfliers=False,medianprops=dict(color='black',linewidth=1.4))
            ax.set_xticks(range(1,len(labels)+1),labels,rotation=65,fontsize=8)
            ax.set_ylabel(selected[0]['measurement']['unit']+suffix+(' (batch averages)' if family in ('capacity','line_size','associativity','latency','page_control') else ''))
            ax.set_title(host+' '+family+'; boxes Q1–Q3, whiskers P5–P95')
            fig.tight_layout(); fig.savefig(str(base)+'-boxes-'+str(page)+'.svg'); fig.savefig(str(base)+'-boxes-'+str(page)+'.pdf'); plt.close(fig)
            write_json(str(base)+'-boxes-'+str(page)+'-provenance.json',dict(labels=labels,sources=[dict(record=r['record_path'],raw=r['raw_path'],sha256=r['raw_sha256'],qualification=r['qualification']) for r in page_rows],script_sha256=sha(__file__)))
        write_json(str(base)+'-provenance.json',dict(command='python3 scripts/analyze.py',script_sha256=sha(__file__),
            sources=[dict(record=r['record_path'],raw=r['raw_path'],sha256=r['raw_sha256']) for r in selected],
            plotting='median curves; IQR shading; box plots include all verified points, with noisy points marked and excluded from confident inference. All outliers retained in raw data and tabulated. No background grid.',
            contributor='Codex automation; student producer/checker attribution pending'))
        paths.append(str(base.relative_to(ROOT))+'.svg')
    return paths


def page_control_summary(host, primary_rows, make_plot=True):
    controls,attempts,issues=rows_for(host,phase='page_control')
    csv_rows(ROOT/'data_processed'/(host+'-page-control-statistics.csv'),[(host,r) for r in controls])
    if make_plot and controls:plot_host(host,controls,ROOT/'plots',families=('page_control',))
    pairs=[]
    calibration=ROOT/'machines'/host/'full/batch-calibration.json'
    chosen_batch=json.loads(calibration.read_text())['chosen_batch'] if calibration.exists() else None
    for r in controls:
        p=r['parameters'];m=r.get('page_control',{})
        if chosen_batch is not None and p['batch']!=chosen_batch:continue
        candidates=[a for a in primary_rows if a['family']=='capacity' and a['parameters']['order']=='random' and a['parameters']['bytes']==p['bytes'] and a['parameters']['batch']==p['batch']]
        baseline=candidates[0] if candidates else None
        huge_before=m.get('anon_huge_before_kib',0)*1024
        huge_after=m.get('anon_huge_after_kib',0)*1024
        confirmed=m.get('advice_rc')==0 and min(huge_before,huge_after)>=p['bytes']
        pairs.append(dict(bytes=p['bytes'],huge_backing_before_bytes=huge_before,huge_backing_after_bytes=huge_after,
            huge_backing_confirmed=confirmed,page_metadata=m,control_statistics=r['statistics'],
            baseline_statistics=baseline['statistics'] if baseline else None,
            same_logical_cpu=baseline is not None and baseline['selected']['cpu']==r['selected']['cpu'],
            control_cpu=r['selected']['cpu'],baseline_cpu=baseline['selected']['cpu'] if baseline else None,
            control_record=r['record_path'],baseline_record=baseline['record_path'] if baseline else None,
            control_raw=r['raw_path'],control_sha256=r['raw_sha256'],qualification=r['qualification'],
            flags=r.get('flags',[]),baseline_qualification=baseline['qualification'] if baseline else None,
            unit=r['measurement']['unit']+'/access'))
    pairs.sort(key=lambda p:p['bytes'])
    cfg=json.loads((ROOT/'config/phase1.json').read_text())
    expected=[];w=cfg['min_bytes']
    while w<=cfg['max_bytes']:expected.append(w);w*=4
    root=ROOT/'machines'/host/'page_control'
    missing=sorted(set(expected)-{p['bytes'] for p in pairs})
    info=dict(pairs=pairs,issues=issues,attempts=len(attempts),alternate_batch_control_points=sum(r['parameters']['batch']!=chosen_batch for r in controls) if chosen_batch is not None else 0,
        missing_working_sets=missing,complete=(root/'collection-finished.json').exists() and not missing and not issues,
        interpretation='Changed latency with confirmed huge backing is consistent with translation effects, but allocation/physical indexing and changed cores may also contribute. No cache geometry is read from page metadata.',
        unavailable=(root/'control-unavailable.json').exists() and not controls)
    if make_plot and pairs:
        import matplotlib.pyplot as plt
        fig,ax=plt.subplots(figsize=(8.5,5.2))
        b=[p for p in pairs if p['baseline_statistics']]
        ax.plot([p['bytes'] for p in b],[p['baseline_statistics']['median'] for p in b],'ko-',label='Base-page random chase')
        ax.plot([p['bytes'] for p in pairs],[p['control_statistics']['median'] for p in pairs],color='0.45',marker='s',label='THP-request random chase')
        unconfirmed=[p for p in pairs if not p['huge_backing_confirmed']]
        if unconfirmed:ax.scatter([p['bytes'] for p in unconfirmed],[p['control_statistics']['median'] for p in unconfirmed],marker='D',s=70,facecolors='none',edgecolors='black',label='Huge backing unconfirmed')
        noisy=[p for p in pairs if p['qualification']=='verified_noisy']
        if noisy:ax.scatter([p['bytes'] for p in noisy],[p['control_statistics']['median'] for p in noisy],marker='x',s=90,color='black',label='Noisy THP-request data')
        noisy=[p for p in b if p['baseline_qualification']=='verified_noisy']
        if noisy:ax.scatter([p['bytes'] for p in noisy],[p['baseline_statistics']['median'] for p in noisy],marker='+',s=100,color='black',label='Noisy base-page data')
        ax.set_xscale('log',base=2);ax.set_yscale('log',base=2);ax.grid(False)
        ax.set_xlabel('Logical working set (bytes)');ax.set_ylabel(pairs[0]['unit']+' (batch averages)')
        ax.set_title(host+' — page-size control');ax.legend(fontsize=10);fig.tight_layout()
        base=ROOT/'plots'/(host+'-page-control')
        for ext in ('svg','pdf','png'):fig.savefig(str(base)+'.'+ext,dpi=160)
        plt.close(fig)
        write_json(str(base)+'-provenance.json',dict(pairs=pairs,script_sha256=sha(__file__),contributor='Codex automation; student attribution pending'))
    write_json(ROOT/'data_processed'/(host+'-page-control.json'),info)
    return info


def csv_rows(path, rows):
    fields=['host','family','analysis_role','bytes','stride','offset','batch','order','seed','n','mean','stddev','median','q1','q3','p05','p95','minimum','maximum','zero_samples','outliers','unit','statistic_unit','median_ns_estimated','p05_ns_estimated','p95_ns_estimated','nanosecond_conversion','selected_cpu','core','socket','node','qualification','flags','raw','record']
    with open(path,'w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for host,r in rows:
            p=r['parameters'];s=r['statistics'];c=r['selected']
            scale,method=ns_scale(r['measurement'])
            d=dict(host=host,family=r['family'],**{k:p[k] for k in ('bytes','stride','offset','batch','order','seed')},
                **{k:s[k] for k in ('n','mean','stddev','median','q1','q3','p05','p95','minimum','maximum','zero_samples','outliers')},
                unit=r['measurement']['unit'],selected_cpu=c['cpu'],core=c['core'],socket=c['socket'],node=c['node'],qualification=r['qualification'],flags='; '.join(r.get('flags',[])),raw=r['raw_path'],record=r['record_path'])
            d.update(median_ns_estimated=s['median']*scale if scale else '',p05_ns_estimated=s['p05']*scale if scale else '',p95_ns_estimated=s['p95']*scale if scale else '',nanosecond_conversion=method)
            d['statistic_unit']=d['unit']+{'overhead':'/interval','reload':'/reload','loop':'/loop iteration'}.get(p['mode'],'/access (batch average)' if p['batch']>1 else '/access')
            d['analysis_role']=r.get('analysis_role','page-backing control' if r['family']=='page_control' else 'primary suite')
            writer.writerow(d)


def comparison_plot(allrows):
    import matplotlib.pyplot as plt
    hosts=json.loads((ROOT/'config/phase1.json').read_text())['hosts']
    fig,axes=plt.subplots(2,4,figsize=(14,7),sharex=True,sharey=True)
    sources=[]
    for host,ax in zip(hosts,axes.flat):
        rows=sorted([r for h,r in allrows if h==host and r['family']=='capacity' and r['parameters']['order']=='random' and r.get('analysis_role')!='alternate batch control'],key=lambda r:r['parameters']['bytes'])
        points=[(r,ns_scale(r['measurement'])[0]) for r in rows]
        points=[(r,s) for r,s in points if s is not None]
        ax.plot([r['parameters']['bytes'] for r,s in points],[r['statistics']['median']*s for r,s in points],'k.-')
        ax.fill_between([r['parameters']['bytes'] for r,s in points],[r['statistics']['q1']*s for r,s in points],[r['statistics']['q3']*s for r,s in points],color='.75')
        noisy=[(r,s) for r,s in points if r['qualification']=='verified_noisy']
        if noisy:ax.scatter([r['parameters']['bytes'] for r,s in noisy],[r['statistics']['median']*s for r,s in noisy],marker='x',color='black')
        ax.set_xscale('log',base=2);ax.set_yscale('log',base=2);ax.grid(False);ax.set_title(host)
        sources.extend(dict(host=host,record=r['record_path'],raw=r['raw_path'],sha256=r['raw_sha256'],ns_per_tick=s) for r,s in points)
    fig.supxlabel('Working set (bytes)');fig.supylabel('Estimated ns/access (batch averages)')
    fig.suptitle('Random dependent-load capacity sweeps; IQR shading; × denotes noisy data')
    fig.tight_layout(rect=(.015,.015,1,.95));base=ROOT/'plots/all-hosts-capacity-ns'
    for ext in ('svg','pdf','png'):fig.savefig(str(base)+'.'+ext,dpi=160)
    plt.close(fig)
    write_json(str(base)+'-provenance.json',dict(sources=sources,script_sha256=sha(__file__),
        conversion='Arm recorded generic-counter frequency; x86 per-run wall-clock calibration. No nominal core GHz or PMU cycles used. Cross-run/core and calibration uncertainty remain.'))


def boundary_distribution_plot(host,rows,candidate):
    import matplotlib.pyplot as plt
    data=sorted([r for r in rows if r['family']=='capacity' and r['parameters']['order']=='random' and r.get('analysis_role')!='alternate batch control'],key=lambda r:r['parameters']['bytes'])
    if not data:return None
    bounds=candidate.get('capacity_interval_bytes')
    index=next((i for i,r in enumerate(data) if bounds and r['parameters']['bytes']==bounds[1]),0)
    start=max(0,index-3);selected=data[start:start+7]
    boxes=[];labels=[]
    for r in selected:
        s=r['statistics'];boxes.append(dict(med=s['median'],mean=s['mean'],q1=s['q1'],q3=s['q3'],whislo=s['p05'],whishi=s['p95'],fliers=[]))
        labels.append(format(r['parameters']['bytes']/1024,'.5g')+' KiB\noutliers='+str(s['outliers'])+('\n*noisy' if r['qualification']=='verified_noisy' else ''))
    fig,ax=plt.subplots(figsize=(8.5,5.2));ax.bxp(boxes,showfliers=False,showmeans=True,medianprops=dict(color='black',linewidth=1.4),meanprops=dict(marker='D',markerfacecolor='white',markeredgecolor='black',markersize=5))
    ax.set_xticks(range(1,len(labels)+1),labels,rotation=25,fontsize=9)
    ax.set_ylabel(selected[0]['measurement']['unit']+'/access (batch averages)')
    ax.set_title(host+' — local timing distributions\nBoxes Q1–Q3; whiskers P5–P95; diamond = mean',fontsize=12)
    ax.grid(False);fig.tight_layout();base=ROOT/'plots'/(host+'-boundary-distributions')
    for ext in ('svg','pdf','png'):fig.savefig(str(base)+'.'+ext,dpi=160)
    plt.close(fig)
    write_json(str(base)+'-provenance.json',dict(script_sha256=sha(__file__),
        selection='Up to seven successive final-batch random points starting three points before the first exploratory departure; smallest points if no departure is resolved. Noisy points remain visible. Complete box plots cover every verified point separately.',
        sources=[dict(record=r['record_path'],raw=r['raw_path'],sha256=r['raw_sha256'],qualification=r['qualification']) for r in selected]))
    return str(base.relative_to(ROOT))+'.svg'


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--final',action='store_true');ap.add_argument('--no-plots',action='store_true');args=ap.parse_args()
    cfg=json.loads((ROOT/'config/phase1.json').read_text())
    output=ROOT/'data_processed';output.mkdir(exist_ok=True)
    plots=ROOT/'plots';plots.mkdir(exist_ok=True)
    host_info={};allrows=[];blocked=[]
    for host in cfg['hosts']:
        rows,attempts,issues=rows_for(host)
        root=ROOT/'machines'/host/'full'
        calibration=root/'batch-calibration.json'
        chosen_batch=json.loads(calibration.read_text())['chosen_batch'] if calibration.exists() else None
        for r in rows:
            alternate=r['family'] in ('capacity','line_size','associativity') and chosen_batch is not None and r['parameters']['batch']!=chosen_batch
            r['analysis_role']='alternate batch control' if alternate else 'primary suite'
        absent=[f for f in FAMILIES if not any(r['family']==f for r in rows)]
        coverage=coverage_issues(rows,root,cfg)
        complete=(root/'collection-finished.json').exists() and not issues and not absent and not coverage
        environment=json.loads((root/'environment.json').read_text()) if (root/'environment.json').exists() else {}
        info=dict(host=host,cpu_model=environment.get('cpu_model','unavailable'),isa=(environment.get('uname') or ['','','','','unavailable'])[4],observed_cpus=sorted({r['selected']['cpu'] for r in rows}),observed_sockets=sorted({r['selected']['socket'] for r in rows}),observed_numa_nodes=sorted({r['selected']['node'] for r in rows}),verified_points=len(rows),clean_points=sum(r['qualification']=='verified_clean' for r in rows),noisy_points=sum(r['qualification']=='verified_noisy' for r in rows),attempts=len(attempts),unsuccessful_attempts=sum(r['status']!='passed' for r in attempts),
            missing_families=absent,integrity_or_quality_issues=issues,coverage_issues=coverage,collection_complete=complete,
            capacity_candidates=boundaries(rows),line_size=spatial_inference(rows),associativity=conflict_inference(rows),
            inclusion_policy=dict(status='uncertain',reason='Same-core pressure may directly evict upper copies; lower-level-only eviction and upper residency were not independently established. No global inclusion/exclusion classification.'),
            sharing_scope='effective domain visible to the pinned core; exact sharing domain unverified in Phase I',
            software_metric=estimator(rows,host),plots=[])
        info['l1_candidate']=l1_candidate(rows,info['line_size'],info['associativity'])
        info['course_cpu_model']=COURSE_MODELS[host]
        info['chosen_primary_batch']=chosen_batch
        info['alternate_batch_control_points']=sum(r['analysis_role']=='alternate batch control' for r in rows)
        if not info['cpu_model']:info['cpu_model']='not exposed by the permitted model-line query'
        info['cache_table']=level_table(info)
        if not args.no_plots:
            info['plots']=plot_host(host,rows,plots)
            distribution=boundary_distribution_plot(host,rows,info['l1_candidate'])
            if distribution:info['plots'].append(distribution)
        info['page_control']=page_control_summary(host,rows,not args.no_plots)
        info['primary_collection_complete']=complete
        complete=complete and (info['page_control']['complete'] or info['page_control']['unavailable'])
        info['collection_complete']=complete
        if info['page_control']['pairs'] and not args.no_plots: info['plots'].append('plots/'+host+'-page-control.svg')
        if not complete: blocked.append(host)
        host_info[host]=info
        write_json(output/(host+'-inference.json'),info)
        write_json(output/(host+'-qualification.json'),[dict(record=r['record_path'],qualification=r['qualification'],analysis_role=r['analysis_role'],flags=r.get('flags',[]),stddev_rounding_difference=r.get('stddev_rounding_difference',0)) for r in rows])
        allrows.extend((host,r) for r in rows)
        write_json(output/(host+'-attempts.json'),[dict(record=r['record_path'],status=r['status'],error=r.get('error'),flags=r.get('flags')) for r in attempts])
    csv_rows(output/'statistics.csv',allrows)
    if not args.no_plots:comparison_plot(allrows)
    with open(output/'l1-candidates.csv','w',newline='') as f:
        fields=['host','status','capacity_lower_bytes','capacity_upper_bytes','line_candidate_bytes','ways_candidate','geometry_capacity_bytes','derived_sets','hit_class_median','unit']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for host,info in host_info.items():
            c=info['l1_candidate'];bounds=c.get('capacity_interval_bytes') or ['',''];g=c.get('geometry') or {}
            writer.writerow(dict(host=host,status=c['status'],capacity_lower_bytes=bounds[0],capacity_upper_bytes=bounds[1],line_candidate_bytes=c.get('line_bytes'),ways_candidate=c.get('ways'),geometry_capacity_bytes=g.get('capacity_candidate_bytes'),derived_sets=g.get('derived_sets'),hit_class_median=c.get('hit_class_statistics',{}).get('median'),unit=c.get('unit','')))

    fields=['host','level','size_lower_bytes','size_upper_bytes','line_size','associativity','derived_sets','hit_latency_median','next_level_latency_median','incremental_difference','unit','sharing_scope','inclusion_exclusion','status']
    with open(output/'inferred-cache-table.csv','w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for info in host_info.values():writer.writerows(info['cache_table'])
    with open(output/'residency-transitions.csv','w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for host,info in host_info.items():
            candidates=info['capacity_candidates']
            for i,c in enumerate(candidates or [None],1):
                row=dict(host=host,level='candidate residency transition '+str(i) if c else 'unresolved',
                    size_lower_bytes=c['lower_bytes'] if c else '',size_upper_bytes=c['upper_bytes'] if c else '',
                    line_size='unresolved; spatial candidates in host JSON',associativity='unresolved; conflict candidates in host JSON',
                    derived_sets='unresolved: independent C/B/A unavailable',
                    hit_latency_median=c['below']['median'] if c else '',next_level_latency_median=c['above']['median'] if c else '',
                    incremental_difference=c['above']['median']-c['below']['median'] if c else '',unit=c['unit'] if c else '',
                    sharing_scope=info['sharing_scope'],inclusion_exclusion='uncertain',
                    status=c['status'] if c else 'insufficient complete evidence')
                writer.writerow(row)
    status=dict(time=now(),phase='I timing only',complete=not blocked,blocked_hosts=blocked,hosts=host_info,
        invocation=dict(command=[sys.executable]+sys.argv,cwd=os.getcwd(),python=sys.version,script_sha256=sha(__file__),configuration_sha256=sha(ROOT/'config/phase1.json')),
        boundary='No PMU, cache-reporting interface, published cache table, or Hazel cache experiment used.',
        taxonomy='Only course-provided model labels and measured ISA/topology; microarchitecture/year primary-source research pending',
        git_freeze='User will manage Git after Phase I; no further Git actions are automated',
        attribution='Team identities and GitHub/Overleaf URLs pending user input')
    write_json(output/'verification.json',status)
    write_json(output/'analysis-history'/(str(time.time_ns())+'.json'),status)
    if args.final and blocked:
        raise SystemExit('Final Phase-I report refused: required measurements/checks incomplete on '+', '.join(blocked))
    lines=['# Phase-I timing-only status','', 'Status: '+('required data coverage and integrity verified; recorded noise flags remain' if not blocked else 'INCOMPLETE — no Phase-I freeze or final report'),'',
        'Generated '+status['time'], '', '| Host | Verified million-sample points | Unsuccessful attempts | Collection complete |','|---|---:|---:|---|']
    for h,d in host_info.items():lines.append('| '+h+' | '+str(d['verified_points'])+' | '+str(d['unsuccessful_attempts'])+' | '+str(d['collection_complete'])+' |')
    lines+=['','No numeric cache answer is supplied without timing evidence. Candidate capacity intervals and spatial/conflict thresholds are in the per-host inference JSON files. Inclusion policy and exact sharing scope remain uncertain.',
        '', 'Statistics are recomputed from SHA256-verified raw uint64 samples; unsuccessful runs and outliers are retained. Smoke data are excluded from inference. Raw timer ticks are not labelled core cycles.',
        '', 'Phase II and Hazel cache experiments have not been started.', '', 'Sources: `data_processed/statistics.csv`, `data_processed/*-inference.json`, `machines/<host>/full/`, and `access/`.']
    (ROOT/'report/phase1-status.md').write_text('\n'.join(lines)+'\n')
    if not blocked:
        summary=['# Phase-I timing-only inference summary','',
            'Required measurement coverage and raw-data integrity are verified. Each verified point contains at least 1,000,000 timed samples. Noisy points are explicitly retained and excluded from confident boundary inference. These are exploratory timing candidates, not specification-verified cache answers.','',
            '| Host | Verified / noisy points | L1 departure interval (KiB) | Transfer candidate (B) | Conflict ways candidate | Small-class median (estimated ns/access) | Timing-residency proxy |',
            '|---|---:|---|---:|---:|---:|---:|']
        for host,info in host_info.items():
            c=info['l1_candidate'];bounds=c.get('capacity_interval_bytes');metric=info['software_metric']
            interval=' – '.join(format(v/1024,'.6g') for v in bounds) if bounds else 'unresolved'
            latency=format(c['hit_class_median_ns'],'.5g') if c.get('hit_class_median_ns') is not None else 'unresolved'
            rate=format(metric['estimate']*100,'.4f')+'%' if 'estimate' in metric else 'unresolved'
            summary.append('| '+host+' | '+str(info['verified_points'])+' / '+str(info['noisy_points'])+' | '+interval+' | '+str(c.get('line_bytes') or 'unresolved')+' | '+str(c.get('ways') or 'unresolved')+' | '+latency+' | '+rate+' |')
        summary+=['','Capacity intervals are the first >10% departures from each coherent small-footprint baseline. They are not statistical confidence intervals. Line/ways candidates require repeated spatial/conflict evidence. Exact internally consistent geometry, when supported, appears in `../data_processed/l1-candidates.csv`.',
            '', 'Deeper-level capacity/latency transitions remain effective residency candidates because cache, translation, replacement, core changes and sharing are not fully separated. Distinct L2/LLC geometry, exact sharing scope and inclusion/exclusion remain unresolved. The same-core reload test does not isolate lower-only eviction.',
            '', 'The residency proxy is not a validated hardware hit rate. Consult each host JSON for threshold sensitivity, block ranges, conditional Wilson intervals and calibration/core limitations. Estimated nanoseconds use recorded generic-counter frequency on Arm and per-run wall-timer calibration on x86; no nominal-GHz conversion or core-cycle claim is made.',
            '', 'Evidence: `../data_processed/statistics.csv`, `../data_processed/inferred-cache-table.csv`, `../data_processed/residency-transitions.csv`, per-host inference/page-control JSON, and `../plots/`. All raw attempts are retained in `../machines/`.',
            '', 'Stop before Phase II. Git remains under user control. Team identities, contribution evidence, project URLs and cache-blind taxonomy/year research remain pending; see `../docs/human-handoff.md`.']
        (ROOT/'report/phase1-inference-summary.md').write_text('\n'.join(summary)+'\n')
    print(json.dumps(dict(complete=not blocked,blocked_hosts=blocked,verified_points=len(allrows),output=str(output))))

if __name__=='__main__':main()
