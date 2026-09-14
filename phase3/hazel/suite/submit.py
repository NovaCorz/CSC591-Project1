#!/usr/bin/env python3
"""Submit one auditable, nonduplicated Hazel baseline segment."""
import argparse
import datetime
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
MAP = {
    'haswell': ('compute', 'normal'),
    'broadwell': ('compute', 'normal'),
    'skylake': ('compute_partners', 'short'),
    'cascadelake': ('compute', 'normal'),
    'icelake_6326': ('compute_partners', 'short'),
    'icelake_8358': ('compute_partners', 'short'),
    'sapphirerapids': ('compute_partners', 'short'),
    'genoa': ('compute_partners', 'short'),
    'turin': ('compute_partners', 'short'),
}


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('constraint', choices=MAP)
    parser.add_argument('stage', choices=('smoke', 'full'))
    parser.add_argument('--continuation-of')
    args = parser.parse_args()
    partition, qos = MAP[args.constraint]
    if args.stage == 'full':
        gate = ROOT / 'runs' / args.constraint / 'baseline/smoke/smoke-passed.json'
        if not gate.exists():
            raise SystemExit('Refusing full submission without passing compute smoke gate')
    name = 'hz-' + args.constraint.replace('_', '')[:10] + '-' + args.stage
    active = subprocess.run(
        ['squeue', '-h', '-u', __import__('getpass').getuser(), '-n', name, '-o', '%i|%T|%R'],
        capture_output=True, text=True, timeout=30, check=True)
    active_rows = [line.split('|') for line in active.stdout.splitlines() if line.strip()]
    active_ids = {row[0].split('_', 1)[0] for row in active_rows}
    if args.continuation_of:
        if args.stage != 'full':
            raise SystemExit('Only full acquisition can be continued')
        if active_ids - {args.continuation_of}:
            raise SystemExit('Refusing continuation beside another active job: ' + active.stdout.strip())
    elif active_rows:
        raise SystemExit('Refusing duplicate active job: ' + active.stdout.strip())
    logs = ROOT / 'logs' / args.constraint
    logs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    record_path = ROOT / 'submissions' / args.constraint / (args.stage + '-' + stamp + '.json')
    minutes = '00:20:00' if args.stage == 'smoke' else '01:55:00'
    command = [
        'sbatch', '--parsable', '--account=ece592f26_cpu',
        '--partition=' + partition, '--qos=' + qos,
        '--constraint=' + args.constraint, '--nodes=1', '--ntasks=1',
        '--cpus-per-task=2', '--hint=nomultithread', '--mem=2G',
        '--time=' + minutes, '--job-name=' + name,
        '--output=' + str(logs / (args.stage + '.%j.stdout')),
        '--error=' + str(logs / (args.stage + '.%j.stderr')),
        '--export=ALL,HAZEL_CONSTRAINT=' + args.constraint + ',HAZEL_STAGE=' + args.stage,
        str(ROOT / 'suite/run_segment.sh')
    ]
    if args.continuation_of:
        command.insert(-1, '--dependency=afterany:' + args.continuation_of)
    record = {
        'requested': now(), 'constraint': args.constraint, 'stage': args.stage,
        'command': command, 'continuation_of': args.continuation_of,
        'prediction_freeze': None,
        'protocol_deviation': 'Execution explicitly authorized without the required pre-Hazel prediction freeze.'
    }
    write(record_path, record)
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    record.update(finished=now(), returncode=result.returncode,
                  stdout=result.stdout, stderr=result.stderr)
    if result.returncode == 0:
        record['job_id'] = result.stdout.strip().split(';')[0]
    write(record_path, record)
    print(json.dumps({'record': str(record_path), 'returncode': result.returncode,
                      'job_id': record.get('job_id'), 'stderr': result.stderr}), flush=True)
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
