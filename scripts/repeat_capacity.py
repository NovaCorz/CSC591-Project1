"""Repeat the unchanged Sunbird pilot three times; run from the project directory.

    python3 repeat_capacity.py

Diagnostic samples only, not the assignment's million-sample final evidence.
"""
import csv
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def cpu_times():
    result = {}
    for line in Path('/proc/stat').read_text().splitlines():
        fields = line.split()
        if fields[0] in ('cpu2', 'cpu26'):
            values = list(map(int, fields[1:9]))
            result[fields[0]] = [sum(values), values[3] + values[4]]
    return result


def main():
    if os.uname().nodename.split('.')[0] != 'sunbird':
        raise SystemExit('Run this diagnostic on Sunbird only.')
    if 2 not in os.sched_getaffinity(0):
        raise SystemExit('CPU 2 is not available in this session.')
    binary = Path('results/sunbird-pilot-20260906/cache_capacity')
    if not binary.is_file():
        raise SystemExit('Original pilot executable is missing.')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    root = Path('results') / ('sunbird-repeat-' + stamp)
    root.mkdir(exist_ok=False)
    rows = []
    for repeat in range(1, 4):
        dest = root / f'repeat{repeat}'
        args = [sys.executable, 'capacity.py', 'run', '--cpu', '2', '--binary', str(binary),
                '--out', str(dest), '--pilot', '--samples', '1000', '--steps', '4096',
                '--spacing', '8', '--seed', '592', '--sizes-kib', '4', '16', '64',
                '--build-command', 'gcc -O0 -g -std=c11 -Wall -Wextra -Werror '
                '-fno-omit-frame-pointer -o results/sunbird-pilot-20260906/cache_capacity cache_capacity.c',
                '--notes', 'Repeatability diagnostic; unchanged binary, seed, batch length and sizes. '
                'CPU 2/core 2/socket 0/NUMA 0; SMT sibling 26. First-touch; OS policy unchanged. '
                'Reservation sheet previously HTTP 401; no reservation. CPU activity deltas in parent '
                'activity JSON cover collection including process setup, not just timed loads. '
                'No usable Git repository; not final evidence.']
        before = cpu_times()
        start = time.monotonic()
        with (root / f'repeat{repeat}.log').open('x') as log:
            subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, check=True)
        elapsed = time.monotonic() - start
        after = cpu_times()
        activity = {'elapsed_seconds': elapsed, 'before': before, 'after': after,
                    'busy_percent': {}}
        for cpu in before:
            total = after[cpu][0] - before[cpu][0]
            idle = after[cpu][1] - before[cpu][1]
            activity['busy_percent'][cpu] = 100 * (total - idle) / total if total else None
        (root / f'repeat{repeat}-activity.json').write_text(json.dumps(activity, indent=2) + '\n')
        subprocess.run([sys.executable, 'capacity.py', 'plot', str(dest)], check=True)
        with (dest / 'summary.csv').open() as stream:
            for row in csv.DictReader(stream):
                assert int(row['samples']) == 1000 and int(row['steps']) == 4096
                rows.append({'repeat': repeat, **row})
        print(f'Repeat {repeat}: {activity}', flush=True)
    assert len(rows) == 21
    with (root / 'comparison.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f'All three repeats completed: {root}', flush=True)


if __name__ == '__main__':
    main()
