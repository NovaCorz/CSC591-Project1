#!/usr/bin/env python3
"""CLI for the frozen Phase-I classifier; consumes only benchmark timings/metadata."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'main_code/common/phase1/scripts'))
import analyze
from common import read_raw, stats, sha

def classify(folder,smoke=False):
    folder=Path(folder).resolve()
    config=json.loads((ROOT/'competition/parameters.json').read_text())
    n=2048 if smoke else config['samples_per_point']
    run=json.loads((folder/'run.json').read_text())
    if run['parameters']!=config: raise ValueError('Frozen configuration mismatch')
    records=[];cpus=set();units=set()
    for label,size in [('hot',config['hot_bytes']),('target',config['target_bytes']),('cold',config['cold_bytes'])]:
        meta=folder/(label+'.json');raw=folder/(label+'.u64')
        m=json.loads(meta.read_text())
        if run['commands'][label][-2]!='random': raise ValueError('Random traversal required')
        values=read_raw(raw,m['little_endian'])
        if len(values)!=n:raise ValueError(label+': incorrect sample count')
        if m['cpu']!=m['final_cpu']:raise ValueError(label+': CPU migration')
        if m.get('mode')!='chase' or m.get('offset')!=0 or m.get('samples')!=n or m.get('bytes')!=size or m.get('batch')!=1 or m.get('stride')!=8 or m.get('seed')!=config['seed']:
            raise ValueError(label+': measurement parameters differ from frozen configuration')
        cpus.add(m['cpu']);units.add(m['unit'])
        clean=not m.get('major_faults',0) and not m.get('involuntary_switches',0)
        records.append(dict(family='software_metric',parameters={'bytes':size},qualification='verified_clean' if clean else 'noisy',statistics=stats(values),raw_path=str(raw),measurement=m,selected={'cpu':m['cpu']},record_path=str(meta),raw_sha256=sha(raw)))
    if len(cpus)!=1 or len(units)!=1:raise ValueError('Calibration and target must share one logical CPU and timer unit')
    result=analyze.estimator(records,'competition')
    # Keep the original return values; clarify its historical validation note externally.
    result['acquisition_kind']='smoke, not a competition result' if smoke else 'full'
    result['estimate_percent']=100*result['estimate'] if 'estimate' in result else None
    result['input_hashes']={Path(r['raw_path']).name:r['raw_sha256'] for r in records}
    result['validation_reference']='estimator_validation/results/comparison.csv; its reference-population limitations apply'
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path,help='hot/target/cold .u64 and benchmark stdout .json files')
    p.add_argument('--smoke',action='store_true',help='accept 2048 samples, mark output non-scoring')
    a=p.parse_args()
    print(json.dumps(classify(a.directory,a.smoke),indent=2))
