#!/usr/bin/env python3
"""Submit one nonduplicated post-baseline timing-control job."""
import argparse
import datetime
import getpass
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MAP = {
    'haswell': ('compute', 'normal'), 'broadwell': ('compute', 'normal'),
    'skylake': ('compute_partners', 'short'), 'cascadelake': ('compute', 'normal'),
    'icelake_6326': ('compute_partners', 'short'), 'icelake_8358': ('compute_partners', 'short'),
    'sapphirerapids': ('compute_partners', 'short'), 'genoa': ('compute_partners', 'short'),
    'turin': ('compute_partners', 'short'),
}


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp'); temp.write_text(json.dumps(data, indent=2) + '\n'); temp.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('constraint', choices=MAP)
    parser.add_argument('kind', choices=('independent_load',))
    args = parser.parse_args()
    marker = ROOT / 'runs' / args.constraint / 'baseline/full/collection-finished.json'
    if not marker.exists():
        raise SystemExit('Refusing auxiliary submission before completed baseline')
    if (ROOT / 'runs' / args.constraint / 'independent-load-diagnostic-v2/full-finished.json').exists():
        raise SystemExit('Diagnostic already collected; inspect before resubmission')
    partition, qos = MAP[args.constraint]
    short_kind = 'page' if args.kind == 'page_control' else 'indep-v2'
    name = 'hz-' + args.constraint.replace('_', '')[:9] + '-' + short_kind
    active = subprocess.run(['squeue', '-h', '-u', getpass.getuser(), '-n', name, '-o', '%i|%T|%R'],
                            capture_output=True, text=True, timeout=30, check=True)
    if active.stdout.strip():
        raise SystemExit('Refusing duplicate active job: ' + active.stdout.strip())
    logs = ROOT / 'logs' / args.constraint; logs.mkdir(parents=True, exist_ok=True)
    command = [
        'sbatch', '--parsable', '--account=ece592f26_cpu', '--partition=' + partition,
        '--qos=' + qos, '--constraint=' + args.constraint, '--nodes=1', '--ntasks=1',
        '--cpus-per-task=2', '--hint=nomultithread', '--mem=2G', '--time=01:55:00',
        '--job-name=' + name, '--output=' + str(logs / (short_kind + '.%j.stdout')),
        '--error=' + str(logs / (short_kind + '.%j.stderr')),
        '--export=ALL,HAZEL_CONSTRAINT=' + args.constraint,
        '--wrap=srun --cpu-bind=cores --hint=nomultithread python3 ' +
        str(ROOT / 'suite/scripts/hazel_diagnostic_worker.py') + ' ' + args.kind,
    ]
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    path = ROOT / 'submissions' / args.constraint / (short_kind + '-' + stamp + '.json')
    record = {'requested': now(), 'constraint': args.constraint, 'kind': args.kind,
              'command': command, 'prediction_freeze': None,
              'protocol_deviation': 'Execution explicitly authorized without the required prediction freeze.'}
    save(path, record)
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    record.update(finished=now(), returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
    if result.returncode == 0: record['job_id'] = result.stdout.strip().split(';')[0]
    save(path, record)
    print(json.dumps({'record': str(path), 'returncode': result.returncode,
                      'job_id': record.get('job_id'), 'stderr': result.stderr}))
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
