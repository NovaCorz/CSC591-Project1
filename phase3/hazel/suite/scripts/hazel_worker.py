#!/usr/bin/env python3
"""Slurm-only adapter for the verified Phase-I baseline acquisition worker.

The cache kernel, sampling, sweep construction, statistics, idle test, noise
rules, and seeds remain in worker.py/common.py. This adapter replaces only the
eight-lab-host launch policy and prevents affinity expansion beyond Slurm's
assigned CPU mask.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import time
import traceback

import worker
from common import now, sha, topology, write_json

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {
    'haswell', 'broadwell', 'skylake', 'cascadelake', 'icelake_6326',
    'icelake_8358', 'sapphirerapids', 'genoa', 'turin'
}


class SegmentDeadline(Exception):
    pass


def cpu_model():
    with open('/proc/cpuinfo') as source:
        for line in source:
            if line.startswith(('model name', 'Hardware', 'Processor')) and ':' in line:
                return line.split(':', 1)[1].strip()
    return 'unavailable'


def slurm_environment():
    names = [
        'SLURM_JOB_ID', 'SLURM_JOB_NAME', 'SLURM_JOB_ACCOUNT',
        'SLURM_JOB_PARTITION', 'SLURM_JOB_QOS', 'SLURM_JOB_CONSTRAINTS',
        'SLURM_JOB_NODELIST', 'SLURM_CPUS_PER_TASK', 'SLURM_CPUS_ON_NODE',
        'SLURM_TASKS_PER_NODE', 'SLURM_JOB_NUM_NODES', 'SLURM_JOB_END_TIME',
        'SLURM_PROCID', 'SLURM_LOCALID', 'SLURM_NODEID', 'SLURM_MEM_PER_NODE',
    ]
    return {name: os.environ.get(name) for name in names}


def provenance(out):
    snapshot = out / 'provenance'
    snapshot.mkdir(exist_ok=True)
    manifest = {}
    for parent in ('src', 'scripts', 'config'):
        for path in sorted((ROOT / parent).glob('*')):
            if path.is_file():
                digest = sha(path)
                target = snapshot / (digest + '-' + path.name)
                if not target.exists():
                    shutil.copy2(path, target)
                manifest[str(path.relative_to(ROOT))] = {
                    'sha256': digest, 'snapshot': target.name
                }
    path = snapshot / ('manifest-' + str(time.time_ns()) + '.json')
    write_json(path, manifest)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=('smoke', 'full'))
    args = parser.parse_args()
    job_id = os.environ.get('SLURM_JOB_ID')
    constraint = os.environ.get('HAZEL_CONSTRAINT')
    if not job_id:
        raise SystemExit('Refusing to run outside a Slurm job')
    if constraint not in ALLOWED:
        raise SystemExit('Missing or invalid HAZEL_CONSTRAINT')

    out = ROOT.parent / 'runs' / constraint / 'baseline' / args.stage
    out.mkdir(parents=True, exist_ok=True)
    rows, topology_record = topology()
    inherited_affinity = sorted(os.sched_getaffinity(0))
    if not inherited_affinity:
        raise RuntimeError('Slurm task supplied an empty CPU affinity mask')
    known_cpus = {row['cpu'] for row in rows}
    if not set(inherited_affinity) <= known_cpus:
        raise RuntimeError('Assigned CPU missing from topology record')

    config = json.loads((ROOT / 'config/phase1.json').read_text())
    config['_source_digest'] = sha(ROOT / 'src/cache_bench.c')
    config['_hazel_constraint'] = constraint
    config['_slurm_job_id'] = job_id
    config['_affinity_policy'] = 'Retain inherited Slurm mask; never expand to unallocated CPUs'
    environment = out / 'environment-history' / ('job-' + job_id + '.json')
    environment.parent.mkdir(exist_ok=True)
    write_json(environment, {
        'time': now(), 'stage': args.stage, 'constraint': constraint,
        'hostname': platform.node(), 'uname': list(platform.uname()),
        'exact_cpu_model': cpu_model(), 'topology': rows,
        'topology_command': topology_record,
        'inherited_and_available_affinity': inherited_affinity,
        'slurm': slurm_environment(), 'argv': sys.argv,
        'cwd': str(Path.cwd()), 'python': sys.version,
        'git_source_commit': '1f687d7f6eec0cf79e74afc57118db013aa036c3',
        'source_sha256': config['_source_digest'], 'config': config,
        'prediction_freeze': None,
        'protocol_deviation': 'User explicitly directed Hazel execution without the section 8.6.1 prediction freeze; measurements cannot retroactively satisfy that ordering requirement.',
        'locality': 'Anonymous mmap and first touch after benchmark CPU binding; MADV_NOHUGEPAGE; no privileged changes',
    })
    config['_environment_record'] = str(environment.relative_to(out))
    manifest = provenance(out)
    config['_provenance_manifest'] = str(manifest.relative_to(out))

    end = int(os.environ.get('SLURM_JOB_END_TIME', '0') or 0)
    margin = 120 if args.stage == 'smoke' else 1500
    original_point = worker.point

    def bounded_point(family, params, context):
        if end and time.time() + margin >= end:
            raise SegmentDeadline('Insufficient Slurm time remains to safely start another point')
        return original_point(family, params, context)

    worker.point = bounded_point
    lock_path = ROOT.parent / 'runs' / constraint / 'baseline' / ('worker-' + args.stage + '.lock')
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            if args.stage == 'full':
                if config['samples'] < 1_000_000:
                    raise RuntimeError('Full Hazel acquisition requires at least 1,000,000 samples per point')
                gate = ROOT.parent / 'runs' / constraint / 'baseline/smoke/smoke-passed.json'
                if not gate.exists():
                    raise RuntimeError('Exact-source compute smoke gate is missing')
                smoke = json.loads(gate.read_text())
                if smoke['source_sha256'] != config['_source_digest']:
                    raise RuntimeError('Smoke source hash does not match full-run source')
            build = out / 'build'
            build.mkdir(exist_ok=True)
            os.chdir(build)
            worker.build(build)
            worker.run_suite(out, config, rows, args.stage == 'smoke')
            write_json(out / ('segment-' + job_id + '.json'), {
                'time': now(), 'job_id': job_id, 'stage': args.stage,
                'status': 'stage_complete'
            })
        except SegmentDeadline as exc:
            write_json(out / ('segment-' + job_id + '.json'), {
                'time': now(), 'job_id': job_id, 'stage': args.stage,
                'status': 'continuation_required', 'reason': str(exc)
            })
            raise SystemExit(75)
        except Exception as exc:
            write_json(out / ('failure-' + job_id + '.json'), {
                'time': now(), 'job_id': job_id, 'stage': args.stage,
                'error': str(exc), 'traceback': traceback.format_exc()
            })
            raise


if __name__ == '__main__':
    main()
