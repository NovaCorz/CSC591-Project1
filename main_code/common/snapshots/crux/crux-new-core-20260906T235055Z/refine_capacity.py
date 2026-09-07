"""Run data-selected refinement points on the original host/core/native binary.

    python3 refine_capacity.py [CAMPAIGN_DIRECTORY]

Uses refinement_plan.json. Writes new directories; never edits coarse results.
"""
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from lab_capacity import HOSTS, activity


def main():
    if len(sys.argv) > 2:
        raise SystemExit(__doc__)
    project = Path(__file__).resolve().parent
    host = os.uname().nodename.split('.')[0]
    if host not in HOSTS:
        raise SystemExit('Assigned ECE hosts only.')
    campaign = Path(sys.argv[1]).resolve() if len(sys.argv) == 2 else project / 'results/capacity-20260906'
    dest = campaign / host
    preflight = json.loads((dest / 'preflight.json').read_text())
    selected = preflight['selected']
    if selected['cpu'] not in os.sched_getaffinity(0):
        raise SystemExit('Original selected CPU is no longer allowed.')
    plan = json.loads((project / 'refinement_plan.json').read_text())[host]
    groups = [('small', plan['small_kib']), ('middle', plan['middle_kib']),
              ('large', [1024 * n for n in plan['large_mib']])]
    for group, sizes in groups:
        assert sizes == sorted(set(sizes)) and all(isinstance(n, int) and n > 0 for n in sizes)
        if (dest / ('refine-' + group)).exists():
            raise SystemExit('Refinement directory already exists; inspect it instead of overwriting.')
    before = activity()
    time.sleep(2)
    after = activity()
    busy = {cpu: 100 * (1 - (after[cpu][1] - before[cpu][1]) /
                       max(1, after[cpu][0] - before[cpu][0])) for cpu in selected['siblings']}
    record = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'selected': selected, 'busy_percent': busy, 'groups_kib': dict(groups),
              'reservation': 'Sheet HTTP 401 previously; no reservation',
              'comparison': 'Overlapping coarse points intentionally repeated with same seed/core/binary'}
    (dest / 'refinement-preflight.json').write_text(json.dumps(record, indent=2) + '\n')
    if max(busy.values()) > 10:
        raise SystemExit('Original core/sibling is busy (>10%); defer refinement until quiet.')
    shutil.copy2(project / 'refine_capacity.py', dest / 'refine_capacity.py')
    shutil.copy2(project / 'refinement_plan.json', dest / 'refinement_plan.json')
    os.chdir(dest)
    for group, sizes in groups:
        before = activity()
        started = time.monotonic()
        notes = ('Timing-only refinement selected from this host\'s original '
                 'results/capacity-20260906 full/summary.csv; '
                 'see project CAPACITY_FINDINGS.md and refinement-preflight.json. '
                 'Same CPU, binary, spacing, batch length, and seed as coarse run; '
                 'overlaps check repeatability. First-touch after pinning; OS policy unchanged. '
                 'No reservation (sheet HTTP 401). User handles commits; no PMU/cache specs.')
        args = [sys.executable, 'capacity.py', 'run', '--cpu', str(selected['cpu']),
                '--binary', './cache_capacity', '--out', 'refine-' + group,
                '--samples', '1000000', '--steps', '4096', '--seed', '592', '--spacing', '8',
                '--sizes-kib', *map(str, sizes), '--build-command', Path('build.txt').read_text().strip(),
                '--notes', notes]
        subprocess.run(args, check=True)
        record = {'elapsed_seconds': time.monotonic() - started,
                  'before': before, 'after': activity(),
                  'scope': 'OS totals over setup/collection; not proof of isolation during timed loads'}
        Path('refine-' + group + '-activity.json').write_text(json.dumps(record, indent=2) + '\n')
    print('All refinement groups collected for ' + host, flush=True)


if __name__ == '__main__':
    main()
