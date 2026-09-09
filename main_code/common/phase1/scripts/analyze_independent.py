#!/usr/bin/env python3
"""Verify all raw diagnostic intervals, selection and idle evidence; summarize pairs."""
import argparse
import csv
import json
import math
from pathlib import Path
import statistics
from common import now,read_raw,sha,stats,statistics_agree,utilization,write_json
from independent_worker import audit_loops

ROOT=Path(__file__).resolve().parents[1]


def verify_record(out,path):
    d=json.loads(path.read_text())
    d['record']=str(path.relative_to(ROOT));d['record_sha256']=sha(path)
    if 'raw' not in d:
        assert d['status']=='failed',('incomplete attempt',path)
        return d
    p=d['parameters'];m=d['measurement'];raw=out/d['raw']
    assert sha(raw)==d['raw_sha256']
    values=read_raw(raw,m['little_endian']);divisor=1 if p['mode']=='overhead' else p['batch']
    assert len(values)==p['samples']==m['samples']==d['exact_raw_count']
    assert statistics_agree(stats(values,divisor),d['statistics']),path
    block=max(1,len(values)//10)
    medians=[stats(values[i:i+block],divisor)['median'] for i in range(0,len(values),block)]
    assert medians==d['block_medians']
    assert m['functional_checks_passed'] and m['streams']==p['streams']
    for key in ['bytes','stride','batch','seed']:assert m[key]==p[key]
    assert p['bytes']==1024 and p['stride']==8 and p['batch']%128==0
    if 'repair_generation' in p:
        repair=out/'repair'/p['repair_generation']
        assert sha(repair/'independent_repair.py')==p['repair_driver_sha256']
        checks=[json.loads(f.read_text()) for f in repair.glob('quiet-check-*.json')]
        quiet=next(c for c in checks if c['selected'] is not None)
        assert len(quiet['evidence'])==20
        for w in quiet['evidence']:
            assert utilization(w['before'],w['after'])==w['busy_fraction']
            assert all(w['busy_fraction'][str(s)]<=quiet['threshold'] for s in quiet['selected']['siblings'])
    idle=json.loads((path.parent/'idle.json').read_text());cpu=d['selected']['cpu']
    assert idle['selected']==d['selected'] and len(idle['evidence'])==2
    for window in idle['evidence']:
        actual=utilization(window['before'],window['after'])
        assert actual==window['busy_fraction']
        assert all(actual[str(s)]<=idle['threshold'] for s in d['selected']['siblings'])
    env=json.loads((out/d['environment_record']).read_text())
    assert cpu in env['available_affinity']
    build=out/Path(d['provenance_manifest']).parent
    manifest=json.loads((build/'manifest.json').read_text())
    assert manifest['source_digest']==d['source_sha256']
    for name,h in manifest['files'].items():assert sha(build/'source'/name)==h
    binary=json.loads((build/'verification.json').read_text())
    assert sha(build/'independent_load')==binary['binary_sha256']
    flags=[]
    if m['cpu']!=cpu or m['final_cpu']!=cpu:flags.append('affinity mismatch')
    if m['major_faults']:flags.append('major page faults during measurement')
    if m['involuntary_switches']>max(5,m['elapsed_ns']/1e9*5):flags.append('frequent involuntary context switches')
    trace=json.loads((path.parent/'activity.json').read_text())
    siblings=set(d['selected']['siblings'])-{cpu}
    if any(w['busy_fraction'].get(str(s),1)>env['config']['idle_fraction'] for w in trace for s in siblings):flags.append('SMT sibling became busy')
    if max(medians)>1.2*max(min(medians),1e-9) and (max(medians)-min(medians))*divisor>2:flags.append('block median drift exceeds 20 percent')
    if p['mode']=='chase' and d['statistics']['zero_samples']>.01*len(values):flags.append('timer resolution: more than 1 percent zero intervals')
    assert flags==d['flags'] and d['status']==('noisy' if flags else 'passed')
    d['idle_record']=str((path.parent/'idle.json').relative_to(ROOT))
    d['idle_sha256']=sha(path.parent/'idle.json')
    return d


def pair_summary(records):
    by={r['parameters']['streams']:r for r in records}
    assert set(by)=={1,4}
    a,b=by[1],by[4]
    assert a['selected']['cpu']==b['selected']['cpu']
    assert a['measurement']['ring_hash']==b['measurement']['ring_hash']
    assert all(r['status']=='passed' for r in records)
    for key in ['batch','seed','bytes','stride','samples']:
        assert a['parameters'][key]==b['parameters'][key]
    assert a['measurement']['unit']==b['measurement']['unit']
    return dict(cpu=a['selected']['cpu'],dependent=a['statistics']['median'],independent=b['statistics']['median'],
        ratio=a['statistics']['median']/b['statistics']['median'],records=[a['record'],b['record']])


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--hosts',nargs='+');args=ap.parse_args()
    hosts=json.loads((ROOT/'config/phase1.json').read_text())['hosts'];plan=json.loads((ROOT/'config/independent-load.json').read_text())
    if args.hosts:
        if set(args.hosts)-set(hosts):ap.error('Only assigned lab hosts allowed')
        hosts=args.hosts
    dest=ROOT/'data_processed/independent-load';dest.mkdir(parents=True,exist_ok=True)
    all_records=[];summaries=[];inputs={};audits={}
    for host in hosts:
        out=ROOT/'machines'/host/plan['round']
        assert (out/'full-finished.json').exists(),host+' not complete'
        records={}
        for path in sorted(out.glob('*/*/attempt-*/run.json')):
            d=verify_record(out,path);records[d['attempt'] if 'attempt' in d else str(path.parent.relative_to(out))]=d
            all_records.append(dict(host=host,**d));inputs[d['record']]=d['record_sha256']
            if 'raw' in d:inputs[str((out/d['raw']).relative_to(ROOT))]=d['raw_sha256']
        for build in (out/'build').iterdir():
            env=next(json.loads(p.read_text()) for p in out.glob('environment-*.json'))
            loops=audit_loops((build/'independent_load.dis').read_text(),env['isa'])
            for name,entry in loops.items():
                lines=entry['disassembly'].splitlines();pattern='ldr' if env['isa']=='aarch64' else 'mov'
                # Audit exact inner loop from first self-dereferencing load through backward branch.
                import re
                first=next(i for i,s in enumerate(lines) if re.search(r'ldr\s+(x\d+),\s*\[\1\]' if env['isa']=='aarch64' else r'mov\s+\(%(\w+)\),%\1',s))
                last=next(i for i in range(first,len(lines)) if re.search(r'b\.ne' if env['isa']=='aarch64' else 'jne',lines[i]))
                body='\n'.join(lines[first:last+1]);assert not re.search(r'\bsp\b|%[re](?:sp|bp)',body)
                assert last-first+1==6
                entry['inner_loop']=body;entry['stack_free_inner_loop']=True
            audits[host]=loops
        cohorts=json.loads((out/'cohorts.json').read_text());pairs=[]
        assert len(cohorts['cohorts'])==len(plan['seeds'])*len(plan['orders'])
        assert {(c['seed'],c['order_index']) for c in cohorts['cohorts']}=={(s,i) for s in plan['seeds'] for i in range(len(plan['orders']))}
        for c in cohorts['cohorts']:
            first_clean=[]
            for attempt in c['attempts']:
                group=[records[r] for r in attempt['records']]
                clean=all(d['status']=='passed' for d in group) and len({d.get('selected',{}).get('cpu') for d in group})==1
                if clean:clean=len({d['measurement']['ring_hash'] for d in group})==1
                assert clean==attempt['same_core_clean']
                assert [d['parameters']['streams'] for d in group]==c['order']
                assert all(d['parameters']['seed']==c['seed'] and d['parameters']['order_index']==c['order_index'] and d['parameters']['samples']==plan['samples'] for d in group)
                if clean and not first_clean:first_clean=attempt['records']
            assert c['selected']==first_clean
            if first_clean:pairs.append(dict(seed=c['seed'],order=c['order'],**pair_summary([records[r] for r in first_clean])))
        gate=json.loads((out/'timer-gate.json').read_text());assert gate['passed']
        latest=gate['calibrations'][-1]
        calibration=next(g for g in latest['attempts'] if g['same_core_clean'])
        g=[records[r] for r in calibration['records']]
        assert all(d['status']=='passed' for d in g) and len({d['selected']['cpu'] for d in g})==1
        fraction=g[0]['statistics']['median']/(cohorts['batch']*min(d['statistics']['median'] for d in g[2:]))
        assert fraction==calibration['fraction'] and fraction<=plan['timer_fraction_limit']
        full=[d for d in records.values() if d['parameters']['samples']==plan['samples']]
        result=dict(host=host,unit=g[2]['measurement']['unit']+'/load',batch=cohorts['batch'],qualified_pairs=len(pairs),planned_pairs=6,
            pairs=pairs,cpus=sorted({p['cpu'] for p in pairs}),full_attempts=len(full),smoke_attempts=len(records)-len(full),
            noisy_full=sum(d['status']=='noisy' for d in full),failed_full=sum(d['status']=='failed' for d in full),
            timer_fraction=fraction,calibration_cpu=g[0]['selected']['cpu'],calibration_records=calibration['records'],
            dependent_median=statistics.median(p['dependent'] for p in pairs) if pairs else None,
            independent_median=statistics.median(p['independent'] for p in pairs) if pairs else None,
            ratio_median=statistics.median(p['ratio'] for p in pairs) if pairs else None,
            ratio_min=min((p['ratio'] for p in pairs),default=None),ratio_max=max((p['ratio'] for p in pairs),default=None),
            conclusion='Four independent chains have lower median ticks/load in every qualified pair; evidence of load overlap, not physical hit latency.' if pairs and all(p['ratio']>1 for p in pairs) else 'No uniform independent-load advantage established; inspect pair evidence.',
            limitations='One hot 1 KiB footprint; four chains share the same address set. Native ticks, not core cycles. Batch boundaries reset pointers; wrapper costs retained. Six seed/order pairs are not six independent machines or million independent repetitions.')
        summaries.append(result);write_json(dest/(host+'-summary.json'),result)
        print(json.dumps(result),flush=True)
    write_json(dest/'summary.json',summaries);write_json(dest/'verified-records.json',all_records);write_json(dest/'native-loop-audit.json',audits)
    fields=['host','unit','batch','qualified_pairs','planned_pairs','dependent_median','independent_median','ratio_median','ratio_min','ratio_max','cpus','full_attempts','noisy_full','failed_full','smoke_attempts','timer_fraction']
    with (dest/'summary.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for s in summaries:w.writerow({k:s[k] for k in fields})
    fields=['host','family','record','status','mode','streams','seed','batch','cpu','unit','n','mean','stddev','median','q1','q3','p05','p95','outliers','flags','raw_sha256']
    with (dest/'statistics.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for d in all_records:
            if 'statistics' not in d:continue
            row=dict(host=d['host'],family=d['family'],record=d['record'],status=d['status'],cpu=d['selected']['cpu'],
                unit=d['measurement']['unit']+('/interval' if d['parameters']['mode']=='overhead' else '/load'),
                flags='; '.join(d['flags']),raw_sha256=d['raw_sha256'])
            row.update({k:d['parameters'][k] for k in ['mode','streams','seed','batch']});row.update(d['statistics'])
            w.writerow({k:row[k] for k in fields})
    write_json(dest/'verification.json',dict(time=now(),passed=True,all_hosts=len(hosts)==8,hosts=hosts,
        qualified_pairs=sum(s['qualified_pairs'] for s in summaries),planned_pairs=6*len(hosts),
        all_pairs_qualified=all(s['qualified_pairs']==6 for s in summaries),
        full_attempts=sum(s['full_attempts'] for s in summaries),smoke_attempts=sum(s['smoke_attempts'] for s in summaries),
        noisy_full=sum(s['noisy_full'] for s in summaries),failed_full=sum(s['failed_full'] for s in summaries),
        raw_intervals_verified=sum(d.get('exact_raw_count',0) for d in all_records),
        checks=['All raw counts/hashes/full statistics/block medians','Recomputed noise flags','Two idle windows and SMT siblings',
                'Source snapshot and binary hashes','Native load dependencies and stack-free inner loops','First-clean same-core selection',
                'All six seed/order cohorts','Timer overhead <=5%','Runtime pointer identities'],inputs=inputs))


if __name__=='__main__':main()
