#!/usr/bin/env python3
"""Export final machine-readable tables from verified Phase-I inference JSON."""
import argparse
import csv
import json
from pathlib import Path


def tables(workspace):
    hosts = json.loads((workspace / 'config/phase1.json').read_text())['hosts']
    verification = json.loads((workspace / 'data_processed/uncertainty/verification.json').read_text())
    if not verification['complete']:
        raise ValueError('Final verification is incomplete')
    cache_rows, behavior = [], []
    for host in hosts:
        d = json.loads((workspace / 'data_processed/uncertainty' / (host + '-inference.json')).read_text())
        old = json.loads((workspace / 'data_processed/followup' / (host + '-inference.json')).read_text())
        for c in old['cross_core']['comparisons']:
            behavior.append(dict(host=host, bytes=c['bytes'], seed=c['seed'], clean=c['clean'], same_pair=c['same_pair'],
                control_pair=c['control_pair'], pressure_pair=c['pressure_pair'],
                control_median=c['control']['median'], control_q1=c['control']['q1'], control_q3=c['control']['q3'],
                pressure_median=c['pressure']['median'], pressure_q1=c['pressure']['q1'], pressure_q3=c['pressure']['q3'],
                native_unit=old['revised_cache_table'][0]['unit'].replace('/access', '/target_reload'), sources=c['sources']))
        for i, r in enumerate(old['revised_cache_table']):
            extra = d['conflict'].get('conditional_l2_ways') if i == 1 else None
            geometry = next((g for g in d['conflict']['geometry_checks'] if g['effective_count'] == extra
                and g['compatible_with_prior_l2'] and g['at_least_two_strides']), None)
            cache_rows.append(dict(host=host, level=r['role'], prior_capacity_interval_bytes=r['capacity_interval_bytes'],
                additional_capacity_departures=d['capacity']['replicated_intervals'] if i == 2 else [],
                line_candidate_bytes=r.get('line_candidate_bytes'), prior_ways_candidate=r.get('ways_candidate'),
                additional_conditional_ways=extra,
                additional_conditional_sets_if_64B_line=min(geometry['agreeing_strides']) // 64 if geometry else None,
                derived_sets=r.get('derived_sets'), hit_latency_median=r.get('hit_median_native_ticks_per_access'),
                hit_and_next_level_distributions='data_processed/followup/latency-classes.csv',
                miss_penalty='Descriptive same-core class differences in latency-classes.csv; isolated hardware penalty uncertain',
                unit=r['unit'], sharing_scope=r['sharing_scope'], inclusion_exclusion=r['inclusion_exclusion'],
                limitation=r['caveat'], additional_evidence='data_processed/uncertainty/' + host + '-inference.json'))
    return {'inferred-cache-table.csv': cache_rows, 'historical-behavior.csv': behavior}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    output = tables(args.workspace.resolve())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, records in output.items():
        with (args.output_dir / name).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(records[0]))
            writer.writeheader()
            for record in records:
                writer.writerow({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in record.items()})
        print(str(args.output_dir / name))


if __name__ == '__main__':
    main()
