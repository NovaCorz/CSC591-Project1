"""Three targeted full-count repeats; run from the project root on an ECE host.

    python3 diagnostic_capacity.py results/capacity-diagnostic-20260907

Uses unchanged saved collectors/binaries. No automatic retry on a busy core.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from lab_capacity import activity


SIZES = {
    'charnwood': [16, 32, 64, 2048, 2560, 3072, 3584, 4096, 5120],
    'crux': [32, 128, 256, 4096, 5120, 6144, 7168, 8192],
    'artemisia': [32, 1536, 1792, 2048, 2304, 2560, 3072],
}


def busy_percent(before, after):
    return {cpu: 100 * (1 - (after[cpu][1] - value[1]) /
                       max(1, after[cpu][0] - value[0])) for cpu, value in before.items()}


def invocation(source, dest, host, cpu):
    return [sys.executable, str(source / 'capacity.py'), 'run', '--cpu', str(cpu),
            '--binary', str(source / 'cache_capacity'), '--out', str(dest),
            '--samples', '1000000', '--steps', '4096', '--spacing', '8', '--seed', '592',
            '--sizes-kib', *map(str, SIZES[host]),
            '--build-command', (source / 'build.txt').read_text().strip(),
            '--notes', 'Targeted repeatability check: three identical size lists, seed 592, '
            'same CPU/binary/batch length/spacing. Fresh process/allocation per point; '
            'physical page mapping is not held fixed. Same relative address order at each size. '
            'Small-footprint control plus disputed sizes. First-touch after pinning; '
            'no system changes, PMU, or cache-specification lookup. No reservation; sheet '
            'access unavailable. Preflight and whole-repeat OS activity in parent; '
            'neither proves isolation during timed loads. See CAPACITY_DIAGNOSTIC_PLAN.md.']


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    project = Path.cwd()
    host = os.uname().nodename.split('.')[0]
    if host not in SIZES:
        raise SystemExit('This diagnostic is restricted to Charnwood, Crux, and Artemisia.')
    source = project / ('results/crux-new-core-20260906T235055Z/crux' if host == 'crux'
                        else 'results/capacity-20260906/' + host)
    selected = json.loads((source / 'preflight.json').read_text())['selected']
    env = json.loads((source / 'full/environment.json').read_text())
    assert selected['cpu'] == env['arguments']['cpu']
    assert selected['cpu'] in os.sched_getaffinity(0)
    assert hashlib.sha256((source / 'cache_capacity').read_bytes()).hexdigest() == env['binary_sha256']
    assert hashlib.sha256((source / 'cache_capacity.c').read_bytes()).hexdigest() == env['source_sha256']
    dest = Path(sys.argv[1]).resolve() / host
    dest.mkdir(parents=True, exist_ok=False)
    for name in ('diagnostic_capacity.py', 'lab_capacity.py', 'CAPACITY_DIAGNOSTIC_PLAN.md'):
        shutil.copy2(project / name, dest / name)
    manifest = {'host': host, 'source': str(source), 'selected': selected,
                'sizes_kib': SIZES[host], 'repeats': 3, 'binary_sha256': env['binary_sha256'],
                'source_sha256': env['source_sha256'], 'samples': 1000000,
                'steps': 4096, 'spacing': 8, 'seed': 592,
                'reservation': 'Unavailable; no reservation claimed'}
    (dest / 'plan.json').write_text(json.dumps(manifest, indent=2) + '\n')
    for repeat in range(1, 4):
        before = activity()
        time.sleep(2)
        after = activity()
        busy = busy_percent(before, after)
        record = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'selected': selected, 'all_cpu_busy_percent': busy}
        (dest / f'repeat{repeat}-preflight.json').write_text(json.dumps(record, indent=2) + '\n')
        if max(busy[c] for c in selected['siblings']) > 10:
            raise SystemExit(f'Repeat {repeat} deferred: original core/sibling exceeds 10% busy.')
        print(f'Repeat {repeat} passed quiet-core check: ' +
              str({c: busy[c] for c in selected['siblings']}), flush=True)
        started = time.monotonic()
        before = activity()
        with (dest / f'repeat{repeat}.log').open('x') as log:
            # Saved collector hashes its source relative to this working directory.
            subprocess.run(invocation(source, dest / f'repeat{repeat}', host, selected['cpu']),
                           cwd=source, stdout=log, stderr=subprocess.STDOUT, check=True)
        after = activity()
        record = {'elapsed_seconds': time.monotonic() - started, 'before': before,
                  'after': after, 'all_cpu_busy_percent': busy_percent(before, after),
                  'scope': 'Whole collection/setup, not isolated timed loads; selected CPU includes our benchmark'}
        (dest / f'repeat{repeat}-activity.json').write_text(json.dumps(record, indent=2) + '\n')
        print(f'Repeat {repeat} completed.', flush=True)
    (dest / 'COMPLETE').write_text(datetime.datetime.now(datetime.timezone.utc).isoformat() + '\n')
    print(f'All three targeted repeats collected: {dest}', flush=True)


if __name__ == '__main__':
    main()
