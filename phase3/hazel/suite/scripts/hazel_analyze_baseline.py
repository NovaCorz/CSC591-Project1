#!/usr/bin/env python3
"""Compute-node raw verification and blind baseline inference for one Hazel target."""
import argparse
import json
import os
from pathlib import Path
import sys

import analyze
from common import now, sha, write_json

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('constraint')
    args = parser.parse_args()
    if not os.environ.get('SLURM_JOB_ID'):
        raise SystemExit('Refusing analysis on a login node; Slurm job required')
    allowed = json.loads((ROOT / 'config/phase1.json').read_text())['hosts']
    if args.constraint not in allowed: raise SystemExit('Unknown constraint')
    run = ROOT / 'machines' / args.constraint / 'full'
    if not (run / 'collection-finished.json').exists():
        raise SystemExit('Baseline collection is incomplete')
    rows, attempts, issues = analyze.rows_for(args.constraint, verify=True)
    calibration = json.loads((run / 'batch-calibration.json').read_text())
    chosen = calibration['chosen_batch']
    for row in rows:
        alternate = row['family'] in ('capacity', 'line_size', 'associativity') and row['parameters']['batch'] != chosen
        row['analysis_role'] = 'alternate batch control' if alternate else 'primary suite'
    coverage = analyze.coverage_issues(rows, run, json.loads((ROOT / 'config/phase1.json').read_text()))
    spatial = analyze.spatial_inference(rows)
    conflict = analyze.conflict_inference(rows)
    l1 = analyze.l1_candidate(rows, spatial, conflict)
    output = ROOT.parent / 'analysis' / args.constraint
    output.mkdir(parents=True, exist_ok=True)
    record = {
        'time': now(), 'constraint': args.constraint, 'job_id': os.environ['SLURM_JOB_ID'],
        'source_commit': '1f687d7f6eec0cf79e74afc57118db013aa036c3',
        'analysis_sha256': sha(Path(__file__)), 'phase1_analysis_sha256': sha(Path(analyze.__file__)),
        'verified_points': len(rows), 'attempts': len(attempts),
        'integrity_or_quality_issues': issues, 'coverage_issues': coverage,
        'chosen_batch': chosen, 'capacity_candidates': analyze.boundaries(rows),
        'spatial': spatial, 'conflict': conflict, 'l1_candidate': l1,
        'complete': not issues and not coverage,
        'boundary': 'Timing data only; no PMU, cache reporting, published cache organization, or prediction fitting.',
    }
    write_json(output / 'baseline-inference.json', record)
    write_json(output / 'baseline-verified-records.json', rows)
    geometry = l1.get('geometry') or {}
    required = {
        'spatial_candidate': l1.get('line_bytes'),
        'l1_ways_candidate': l1.get('ways'),
        'l1_tested_period': geometry.get('tested_index_period_bytes'),
        'l1_capacity_interval': l1.get('capacity_interval_bytes'),
    }
    missing = [name for name, value in required.items() if value in (None, [], '')]
    plan = {
        'phase': 'Hazel timing only', 'constraint': args.constraint,
        'batch': chosen, 'spatial_footprints': [524288, 2097152],
        'cross_footprints': [262144, 8388608, 67108864],
        **required, 'baseline_inference_sha256': sha(output / 'baseline-inference.json'),
        'ready': record['complete'] and not missing, 'missing_inputs': missing,
        'derivation': 'Same follow-up constants as Phase I; target-specific line, ways, index period, capacity interval, and batch come only from verified Hazel baseline timing inference.',
    }
    write_json(output / 'followup-plan.json', plan)
    print(json.dumps({'constraint': args.constraint, 'complete': record['complete'],
                      'verified_points': len(rows), 'issues': len(issues),
                      'coverage_issues': len(coverage), 'plan_ready': plan['ready'],
                      'missing_inputs': missing}))
    if not record['complete']:
        raise SystemExit(2)


if __name__ == '__main__': main()
