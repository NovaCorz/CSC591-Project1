#!/usr/bin/env python3
"""Slurm adapters for Phase-I page controls and independent-load diagnostic."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import shutil
import sys
import time

from common import now, sha, topology, write_json
from worker import command, parameters, point
import independent_worker

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = set(json.loads((ROOT / 'config/phase1.json').read_text())['hosts'])


def base_environment(constraint, stage, rows, topo):
    with open('/proc/cpuinfo') as source:
        model = next((line.split(':', 1)[1].strip() for line in source
                      if line.startswith('model name') and ':' in line), 'unavailable')
    slurm = {key: value for key, value in os.environ.items() if key.startswith('SLURM_')}
    return {
        'time': now(), 'constraint': constraint, 'stage': stage,
        'hostname': platform.node(), 'exact_cpu_model': model,
        'isa': platform.machine(), 'kernel': platform.release(),
        'python': sys.version, 'inherited_and_available_affinity': sorted(os.sched_getaffinity(0)),
        'available_affinity': sorted(os.sched_getaffinity(0)),
        'topology': rows, 'topology_command': topo, 'slurm': slurm,
        'git_source_commit': '1f687d7f6eec0cf79e74afc57118db013aa036c3',
        'adapter_sha256': sha(Path(__file__)),
        'prediction_freeze': None,
        'protocol_deviation': 'Execution explicitly authorized without the required section 8.6.1 prediction freeze.',
        'affinity_policy': 'Retain inherited Slurm mask; never expand to unallocated CPUs',
    }


def page_control(constraint):
    primary = ROOT.parent / 'runs' / constraint / 'baseline/full'
    if not (primary / 'collection-finished.json').exists():
        raise RuntimeError('Primary baseline collection must finish first')
    out = ROOT.parent / 'runs' / constraint / 'page_control'
    out.mkdir(parents=True, exist_ok=True)
    rows, topo = topology()
    if len(os.sched_getaffinity(0)) < 2:
        raise RuntimeError('Expected two Slurm-assigned physical CPUs for alternate idle-core selection')
    config = json.loads((ROOT / 'config/phase1.json').read_text())
    calibration = json.loads((primary / 'batch-calibration.json').read_text())
    if not calibration['passed']:
        raise RuntimeError('Primary batch calibration did not pass')
    config['batch'] = calibration['chosen_batch']
    build = out / 'build'; build.mkdir(exist_ok=True)
    for name in ('cache_bench.c', 'page_control.c'):
        shutil.copy2(ROOT / 'src' / name, build / name)
    os.chdir(build)
    flags = ['-O0', '-g', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fno-omit-frame-pointer']
    compiler = shutil.which('gcc')
    command([compiler, '--version'], build, 'compiler')
    command([compiler] + flags + ['page_control.c', '-o', 'page_control'], build, 'compile')
    disassembly = command(['objdump', '-d', 'page_control'], build, 'objdump')
    (build / 'page_control.dis').write_text(disassembly)
    config.update(_benchmark_path=str(build / 'page_control'), _source_digest=sha(build / 'page_control.c'),
                  _page_control=True, _hazel_constraint=constraint,
                  _slurm_job_id=os.environ['SLURM_JOB_ID'])
    env = out / 'environment-history' / ('job-' + os.environ['SLURM_JOB_ID'] + '.json')
    env.parent.mkdir(exist_ok=True)
    record = base_environment(constraint, 'page_control', rows, topo)
    record.update(config=config, compiler_flags=flags, wrapper_sha256=config['_source_digest'],
                  included_primary_sha256=sha(build / 'cache_bench.c'),
                  policy='Only this anonymous mapping receives MADV_HUGEPAGE; actual backing recorded from own smaps whitelist')
    write_json(env, record); config['_environment_record'] = str(env.relative_to(out))

    smoke_out = out / 'smoke'; smoke_out.mkdir(exist_ok=True)
    if not (out / 'smoke-passed.json').exists():
        smoke_config = dict(config, _environment_record='../' + config['_environment_record'])
        smoke = [point('page_control', parameters(config, bytes=size, page_policy='THP-request'),
                       (smoke_out, smoke_config, rows, True)) for size in (32768, 262144)]
        if any(item.get('status') not in ('passed', 'noisy') for item in smoke):
            raise RuntimeError('Page-control wrapper smoke failed; attempts retained')
        write_json(out / 'smoke-passed.json', {
            'time': now(), 'wrapper_sha256': config['_source_digest'], 'samples_per_point': 2048
        })
    sizes = []
    size = config['min_bytes']
    while size <= config['max_bytes']:
        sizes.append(size); size *= 4
    random.Random(config['seed']).shuffle(sizes)
    results = [point('page_control', parameters(config, bytes=size, page_policy='THP-request'),
                     (out, config, rows, False)) for size in sizes]
    write_json(out / 'collection-finished.json', {
        'time': now(), 'points': len(results), 'sizes': sizes,
        'note': 'THP advice is not proof of actual huge-page backing; own-mapping smaps evidence is recorded.'
    })


def independent_setup(out, config, plan, constraint):
    rows, topo = topology(); inherited = sorted(os.sched_getaffinity(0))
    if len(inherited) < 2:
        raise RuntimeError('Expected two Slurm-assigned physical CPUs for alternate idle-core selection')
    files, digest = independent_worker.source_manifest()
    build = out / 'build' / digest; build.mkdir(parents=True, exist_ok=True)
    os.chdir(build)
    if not (build / 'verification.json').exists():
        for name in independent_worker.FILES:
            dest = build / 'source' / name; dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, dest)
        flags = ['-O0', '-g', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fno-omit-frame-pointer']
        compiler = shutil.which('gcc')
        command([compiler, '--version'], build, 'compiler')
        command([compiler] + flags + ['source/src/independent_load.c', '-o', 'independent_load'], build, 'compile')
        command([compiler] + flags + ['-S', 'source/src/independent_load.c', '-o', 'independent_load.s'], build, 'assembly')
        disassembly = command(['objdump', '-d', 'independent_load'], build, 'objdump')
        (build / 'independent_load.dis').write_text(disassembly)
        loops = independent_worker.audit_loops(disassembly, platform.machine())
        write_json(build / 'loop-audit.json', loops)
        write_json(build / 'manifest.json', {'files': files, 'source_digest': digest})
        write_json(build / 'verification.json', {
            'time': now(), 'source_digest': digest, 'binary_sha256': sha(build / 'independent_load'),
            'flags': flags
        })
    verified = json.loads((build / 'verification.json').read_text())
    if verified['binary_sha256'] != sha(build / 'independent_load'):
        raise RuntimeError('Independent-load binary changed')
    config.update(attempts=1, point_timeout_seconds=1200, _use_noise_history=True,
                  _source_digest=digest, _benchmark_path=str(build / 'independent_load'),
                  _provenance_manifest=str((build / 'manifest.json').relative_to(out)),
                  _hazel_constraint=constraint, _slurm_job_id=os.environ['SLURM_JOB_ID'])
    env = out / 'environment-history' / ('job-' + os.environ['SLURM_JOB_ID'] + '.json')
    env.parent.mkdir(exist_ok=True)
    config['_environment_record'] = str(env.relative_to(out))
    record = base_environment(constraint, 'independent_load', rows, topo)
    record.update(config=config, plan=plan, build_verification=verified)
    write_json(env, record)
    return rows, digest


def independent(constraint):
    out = ROOT.parent / 'runs' / constraint / 'independent-load-v1'
    out.mkdir(parents=True, exist_ok=True)
    config = json.loads((ROOT / 'config/phase1.json').read_text())
    plan = json.loads((ROOT / 'config/independent-load.json').read_text())
    rows, digest = independent_setup(out, config, plan, constraint)
    if not (out / 'smoke-passed.json').exists():
        independent_worker.run('smoke', out, config, rows, plan, digest)
    independent_worker.run('full', out, config, rows, plan, digest)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('kind', choices=('page_control', 'independent_load'))
    args = parser.parse_args()
    if not os.environ.get('SLURM_JOB_ID'):
        raise SystemExit('Refusing to run outside Slurm')
    constraint = os.environ.get('HAZEL_CONSTRAINT')
    if constraint not in ALLOWED:
        raise SystemExit('Invalid HAZEL_CONSTRAINT')
    out = ROOT.parent / 'runs' / constraint / (
        'page_control' if args.kind == 'page_control' else 'independent-load-v1')
    out.mkdir(parents=True, exist_ok=True)
    with open(out / 'worker.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        (page_control if args.kind == 'page_control' else independent)(constraint)


if __name__ == '__main__':
    main()
