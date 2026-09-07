"""Prepare or run the capacity experiment on an assigned ECE host.

Usage: python3 lab_capacity.py prepare|pilot|full RUN_DIRECTORY
Run prepare first, inspect its topology/activity and native disassembly, then pilot.
The full run must be explicitly selected after reviewing the pilot.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time


HOSTS = {'sunbird', 'thunderbird', 'skylark', 'artemisia', 'charnwood', 'crux', 'ookay', 'upgrade'}


def activity():
    result = {}
    for line in Path('/proc/stat').read_text().splitlines():
        fields = line.split()
        if fields[0].startswith('cpu') and fields[0][3:].isdigit():
            values = list(map(int, fields[1:9]))
            result[int(fields[0][3:])] = (sum(values), values[3] + values[4])
    return result


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ('prepare', 'pilot', 'full'):
        raise SystemExit(__doc__)
    action, directory = sys.argv[1:]
    host = os.uname().nodename.split('.')[0]
    if host not in HOSTS:
        raise SystemExit('Assigned ECE machines only; never run on Hazel.')
    dest = Path(directory).resolve() / host
    if action == 'prepare':
        dest.mkdir(parents=True, exist_ok=False)
        topology_text = subprocess.check_output(['lscpu', '-p=CPU,CORE,SOCKET,NODE'], text=True)
        topology = [list(map(int, line.split(','))) for line in topology_text.splitlines()
                    if line and not line.startswith('#')]
        before = activity()
        time.sleep(2)
        after = activity()
        busy = {cpu: 100 * (1 - (after[cpu][1] - before[cpu][1]) /
                           max(1, after[cpu][0] - before[cpu][0])) for cpu in before}
        allowed = sorted(os.sched_getaffinity(0))
        candidates = []
        for cpu, core, socket, node in topology:
            if cpu in allowed:
                siblings = [row[0] for row in topology if row[1:3] == [core, socket]]
                candidates.append((max(busy[s] for s in siblings), cpu, core, socket, node, siblings))
        chosen = min(candidates)
        metadata = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    'host': host, 'allowed_cpus': allowed, 'topology': topology_text,
                    'busy_percent': busy, 'selected': dict(zip(
                        ['max_sibling_busy_percent', 'cpu', 'core', 'socket', 'node', 'siblings'], chosen)),
                    'reservation': 'Sheet access previously HTTP 401; no reservation',
                    'memory': [line for line in Path('/proc/meminfo').read_text().splitlines()
                               if line.startswith(('MemAvailable:', 'MemTotal:'))],
                    'microarchitecture': 'Use student-completed Table 1; no cache lookup',
                    'disk_free_bytes': shutil.disk_usage(dest).free}
        (dest / 'preflight.json').write_text(json.dumps(metadata, indent=2) + '\n')
        if chosen[0] > 10:
            raise SystemExit('No sufficiently idle core/sibling pair in this preflight; defer run.')
        for name in ('cache_capacity.c', 'capacity.py', 'lab_capacity.py'):
            shutil.copy2(name, dest / name)
        build = ['gcc', '-O0', '-g', '-std=c11', '-Wall', '-Wextra', '-Werror',
                 '-fno-omit-frame-pointer', '-o', str(dest / 'cache_capacity'), str(dest / 'cache_capacity.c')]
        subprocess.run(build, check=True)
        (dest / 'build.txt').write_text(shlex.join(build) + '\n')
        with (dest / 'benchmark.dis').open('w') as stream:
            subprocess.run(['objdump', '-d', '-S', str(dest / 'cache_capacity')], stdout=stream, check=True)
        print(json.dumps(metadata['selected']), flush=True)
        return
    metadata = json.loads((dest / 'preflight.json').read_text())
    if metadata['selected']['max_sibling_busy_percent'] > 10:
        raise SystemExit('Preflight core was busy; inspect before proceeding.')
    # Run from frozen source copies so later development cannot change this run.
    os.chdir(dest)
    before = activity()
    started = time.monotonic()
    notes = (f"Selected topology/activity in {dest}/preflight.json. No reservation; sheet HTTP 401. "
             'First-touch after affinity, OS policy unchanged. Git commit deferred by user until Phase I ends. '
             'Exact source copies and native disassembly saved in parent. No PMU/cache specification queries.')
    args = [sys.executable, 'capacity.py', 'run', '--cpu', str(metadata['selected']['cpu']),
            '--binary', './cache_capacity', '--out', action, '--steps', '4096', '--seed', '592',
            '--samples', '1000' if action == 'pilot' else '1000000',
            '--build-command', (dest / 'build.txt').read_text().strip(), '--notes', notes]
    if action == 'pilot':
        args += ['--pilot', '--sizes-kib', '4', '16', '64', '256', '1024', '4096', '16384', '65536']
    subprocess.run(args, check=True)
    after = activity()
    cpu_activity = {'elapsed_seconds': time.monotonic() - started, 'before': before, 'after': after,
                    'scope': 'OS CPU totals over collection/setup; not PMU measurements or proof of isolation',
                    'source_sha256': hashlib.sha256(Path('cache_capacity.c').read_bytes()).hexdigest()}
    Path(action + '-activity.json').write_text(json.dumps(cpu_activity, indent=2) + '\n')
    # Plotting may be done later on a host with NumPy/Matplotlib available.
    print(f'Collection complete: {dest / action}', flush=True)


if __name__ == '__main__':
    main()
