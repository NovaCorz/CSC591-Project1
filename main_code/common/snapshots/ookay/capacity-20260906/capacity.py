#!/usr/bin/env python3
"""Run a Phase-I capacity sweep, or summarize and plot its saved distributions."""
import argparse
import csv
import datetime
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys


def command(args):
    result = subprocess.run(args, text=True, capture_output=True)
    return result.stdout.strip() if result.returncode == 0 else result.stderr.strip()


def run(args):
    if args.samples < 1_000_000 and not args.pilot:
        raise ValueError("Fewer than 1,000,000 samples requires --pilot; not final evidence.")
    if args.cpu not in os.sched_getaffinity(0):
        raise ValueError("Requested CPU is outside your allowed CPU set.")
    if args.spacing < 8 or args.spacing % 8:
        raise ValueError("Spacing must be a positive multiple of 8 bytes.")
    if any(k * 1024 % args.spacing or k * 1024 // args.spacing < 2 for k in args.sizes_kib):
        raise ValueError("Each footprint must be divisible by spacing and contain >=2 nodes.")
    binary = Path(args.binary).resolve()
    if not binary.is_file():
        raise ValueError("Compile cache_capacity first; see CAPACITY_GUIDE.md.")
    dest = Path(args.out)
    dest.mkdir(parents=True, exist_ok=False)
    cpu_model = next((line.strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                      if line.startswith(('model name', 'Hardware', 'Processor'))), 'unavailable')
    metadata = {
        'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'hostname': command(['hostname']), 'kernel': command(['uname', '-a']),
        'cpu_model': cpu_model,
        'topology': command(['lscpu', '-e=CPU,CORE,SOCKET,NODE']),
        'compiler_version': command([args.compiler, '--version']),
        'build_command': args.build_command,
        'git_commit': command(['git', 'rev-parse', 'HEAD']),
        'git_status': command(['git', 'status', '--short']),
        'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
        'source_sha256': hashlib.sha256(Path('cache_capacity.c').read_bytes()).hexdigest(),
        'arguments': vars(args), 'command': sys.argv,
        'locality': 'taskset before allocation; first-touch; OS policy unchanged',
        'notes': args.notes,
    }
    (dest / 'environment.json').write_text(json.dumps(metadata, indent=2) + '\n')
    jobs = [(k, mode) for k in sorted(set(args.sizes_kib)) for mode in ('random', 'sequential')]
    random.Random(args.seed).shuffle(jobs)
    jobs.insert(0, (min(args.sizes_kib), 'empty'))
    for k, mode in jobs:
        stem = dest / f'{mode}_{k}KiB'
        invocation = ['taskset', '-c', str(args.cpu), str(binary), str(k * 1024),
                      str(args.spacing), str(args.samples), str(args.steps), str(args.seed),
                      mode, str(stem.with_suffix('.bin'))]
        print(f'{mode:10s} {k:8d} KiB, {args.samples} batches x {args.steps} loads', flush=True)
        result = subprocess.run(invocation, text=True, capture_output=True)
        stem.with_suffix('.stderr').write_text(result.stderr)
        if result.returncode:
            raise RuntimeError(f'Benchmark failed ({result.returncode}): {result.stderr}; partial run in {dest}')
        point = json.loads(result.stdout)
        point['invocation'] = invocation
        stem.with_suffix('.json').write_text(json.dumps(point, indent=2) + '\n')
    (dest / 'COMPLETE').write_text(datetime.datetime.now(datetime.timezone.utc).isoformat() + '\n')
    print(f'Saved {dest}. Analyze with: python3 capacity.py plot {dest}')


def plot(args):
    # Plotting is separate so compute hosts need only Python's standard library.
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    dest = Path(args.directory)
    if not (dest / 'COMPLETE').exists():
        raise ValueError('Run has no COMPLETE marker; finish/investigate the failed run first.')
    environment = json.loads((dest / 'environment.json').read_text())
    rows, boxes = [], []
    units = set()
    for path in sorted(dest.glob('*.json')):
        if path.name == 'environment.json':
            continue
        meta = json.loads(path.read_text())
        units.add(meta['unit'])
        dtype = '<u8' if meta['byte_order'] == 'little' else '>u8'
        values = np.fromfile(path.with_suffix('.bin'), dtype=dtype)
        if values.size != meta['samples']:
            raise ValueError(f'Truncated/incorrect sample file: {path}')
        if not np.any(values):
            raise ValueError(f'Timer returned only zeros: {path}; increase batch length/check timer.')
        values = values.astype(float)
        empty = meta['mode'] == 'empty'
        if not empty:
            values /= meta['steps']
        p5, q1, median, q3, p95 = np.percentile(values, [5, 25, 50, 75, 95])
        iqr = q3 - q1
        low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        outliers = (values < low) | (values > high)
        row = dict(mode=meta['mode'], size_kib=meta['bytes'] / 1024,
                   spacing=meta['spacing'], samples=values.size, steps=meta['steps'],
                   unit=meta['unit'] + ('/timer pair' if empty else '/access'),
                   mean=float(np.mean(values)), median=float(median),
                   stddev=float(np.std(values, ddof=1)), q1=float(q1), q3=float(q3),
                   p5=float(p5), p95=float(p95), outliers=int(np.sum(outliers)),
                   zeros=int(np.count_nonzero(values == 0)))
        rows.append(row)
        if meta['mode'] == 'random':
            inliers = values[~outliers]
            boxes.append((row['size_kib'], dict(label=f"{row['size_kib']:g}",
                         med=median, q1=q1, q3=q3, whislo=float(inliers.min()),
                         whishi=float(inliers.max()), fliers=[])))
    if len(units) != 1 or not boxes:
        raise ValueError('Expected one timer unit and at least one random traversal.')
    rows.sort(key=lambda r: (r['mode'], r['size_kib']))
    with (dest / 'summary.csv').open('w', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    title = environment['hostname'] + (' — PILOT, not final evidence' if environment['arguments']['pilot'] else '')
    unit = next(iter(units)) + '/access'
    fig, ax = plt.subplots(figsize=(9, 5))
    for mode in ('random', 'sequential'):
        series = [r for r in rows if r['mode'] == mode]
        x = [r['size_kib'] for r in series]
        ax.plot(x, [r['median'] for r in series], 'o-', label=mode)
        ax.fill_between(x, [r['p5'] for r in series], [r['p95'] for r in series], alpha=.12)
    ax.set(xscale='log', xlabel='Working-set span (KiB)', ylabel=unit,
           title=title + '\nMedian with 5th–95th percentile bands')
    ax.grid(False)
    ax.legend()
    fig.tight_layout()
    fig.savefig(dest / 'capacity.pdf')
    plt.close(fig)
    boxes.sort(key=lambda pair: pair[0])
    fig, ax = plt.subplots(figsize=(max(9, len(boxes) * .45), 5))
    ax.bxp([box for _, box in boxes], showfliers=False)
    ax.set(xlabel='Working-set span (KiB), randomized traversal', ylabel=unit,
           title=title + '\nTukey box plots; outliers retained in raw files and counted in CSV')
    ax.tick_params(axis='x', labelrotation=60)
    ax.grid(False)
    fig.tight_layout()
    fig.savefig(dest / 'boxes.pdf')
    plt.close(fig)
    overhead = next(r for r in rows if r['mode'] == 'empty')
    print(f"Empty timer-pair median: {overhead['median']:g} {overhead['unit']}; not subtracted.")
    print(f'Saved {dest}/summary.csv, capacity.pdf, boxes.pdf')


def positive(value):
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError('must be positive')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    sweep = sub.add_parser('run')
    sweep.add_argument('--cpu', type=int, required=True)
    sweep.add_argument('--out', required=True, help='new directory; existing directories are refused')
    sweep.add_argument('--binary', default='./cache_capacity')
    sweep.add_argument('--samples', type=positive, default=1_000_000)
    sweep.add_argument('--steps', type=positive, default=256)
    sweep.add_argument('--spacing', type=positive, default=8)
    sweep.add_argument('--seed', type=positive, default=592)
    sweep.add_argument('--sizes-kib', nargs='+', type=positive,
                       default=[2**i for i in range(2, 19)])
    sweep.add_argument('--pilot', action='store_true')
    sweep.add_argument('--compiler', default='gcc')
    sweep.add_argument('--build-command', required=True, help='exact command used to compile this binary')
    sweep.add_argument('--notes', required=True, help='SMT activity, reservation, NUMA policy, interference, etc.')
    analysis = sub.add_parser('plot')
    analysis.add_argument('directory')
    args = parser.parse_args()
    try:
        (run if args.action == 'run' else plot)(args)
    except (ValueError, RuntimeError, OSError, ImportError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
