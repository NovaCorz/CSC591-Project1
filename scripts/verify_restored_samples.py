#!/usr/bin/env python3
"""Recompute a deterministic clean/flagged sample of each host and round.

This is a curation/restore regression check, not a replacement for the archived
full verification. It never collects measurements or changes the raw workspace.
"""
import argparse
import concurrent.futures
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'main_code/common/phase1/scripts'))
from common import sha, read_raw, stats, statistics_agree, utilization
import analyze_followup


def verify_group(workspace, host, round_name):
    root = workspace / 'machines' / host / round_name
    records = []
    for path in root.glob('*/*/attempt-*/run.json'):
        data = json.loads(path.read_text())
        if data.get('raw') and data.get('parameters', {}).get('samples', 0) >= 1000000:
            records.append((data['started'], str(path), data))
    records.sort(key=lambda item: (item[0], item[1]))
    output = dict(host=host, round=round_name, full_raw_attempts=len(records), checks=[])
    for category, flagged in [('clean', False), ('flagged', True)]:
        selected = next((item for item in records if bool(item[2].get('flags')) == flagged), None)
        if selected is None:
            output['checks'].append(dict(category=category, available=False,
                                         reason='No full raw attempt in this category'))
            continue
        _, filename, data = selected
        path = Path(filename)
        problems = []
        if round_name != 'full':
            _, problems = analyze_followup.verify(path, root)
        raw = root / data['raw']
        values = read_raw(raw, data['measurement']['little_endian'])
        parameters = data['parameters']
        divisor = (1 if parameters['mode'] in ('overhead', 'reload') else parameters['batch']) if round_name == 'full' else parameters.get('timed_loads', parameters['batch'])
        actual = stats(values, divisor)
        if sha(raw) != data['raw_sha256']:
            problems.append('Raw hash mismatch')
        if not statistics_agree(actual, data['statistics']):
            problems.append('Recomputed statistics mismatch')
        if not (actual['n'] == data['exact_raw_count'] == parameters['samples'] == data['measurement']['samples']):
            problems.append('Raw sample count mismatch')
        idle = json.loads((path.parent / 'idle.json').read_text())
        selected_core = idle['selected']
        if selected_core != data['selected'] or len(idle['evidence']) < 2 or not 0 <= idle['threshold'] <= .05:
            problems.append('Selected core/idle policy mismatch')
        for window in idle['evidence']:
            if (datetime.fromisoformat(window['end']) - datetime.fromisoformat(window['start'])).total_seconds() < .99:
                problems.append('Idle window too short')
            busy = utilization(window['before'], window['after'])
            if any(busy.get(str(cpu), busy.get(cpu, 1)) > idle['threshold'] + 1e-12 for cpu in selected_core['siblings']):
                problems.append('Recorded core or sibling was busy')
        if data['measurement']['cpu'] != selected_core['cpu'] or data['measurement']['final_cpu'] != selected_core['cpu']:
            problems.append('Affinity mismatch')
        if round_name == 'full' and data['source_sha256'] != sha(workspace / 'src/cache_bench.c'):
            problems.append('Benchmark source mismatch')
        output['checks'].append(dict(category=category, available=True,
            record=str(path.relative_to(workspace)), raw=str(raw.relative_to(workspace)),
            raw_sha256=data['raw_sha256'], samples=actual['n'], statistics=actual,
            flags=data.get('flags', []), selected_core=selected_core,
            idle_evidence=str((path.parent / 'idle.json').relative_to(workspace)),
            idle_windows=len(idle['evidence']), problems=sorted(set(problems)), passed=not problems))
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    if workspace == ROOT or ROOT in workspace.parents:
        parser.error('Use an external restored workspace')
    analyze_followup.ROOT = workspace
    hosts = json.loads((ROOT / 'main_code/common/phase1/config/phase1.json').read_text())['hosts']
    groups = [(h, r) for h in hosts for r in ('full', 'followup-v1', 'uncertainty-v1')]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda group: verify_group(workspace, *group), groups))
    checks = [c for result in results for c in result['checks'] if c['available']]
    result = dict(passed=all(c['passed'] for c in checks) and all(r['full_raw_attempts'] for r in results),
                  policy='First chronological full raw attempt without flags and first with flags, per host/round; unavailable categories explicitly recorded',
                  limitation='Representative restore regression only; complete coverage and all-attempt verification remain in final-verification.json and the external archives',
                  command=[sys.executable] + sys.argv, workspace=str(workspace),
                  groups=len(results), distributions=len(checks), samples=sum(c['samples'] for c in checks), results=results)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('passed', 'groups', 'distributions', 'samples')}))
    raise SystemExit(not result['passed'])


if __name__ == '__main__':
    main()
