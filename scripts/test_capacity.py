"""Small workflow check; these samples are NOT assignment measurements.

Run on an ECE compute machine, not a Hazel login node:
    python3 test_capacity.py
With NumPy and Matplotlib installed this also checks analysis/plotting.
"""
import csv
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    os.chdir(Path(__file__).resolve().parent)
    with tempfile.TemporaryDirectory(prefix='capacity-check-') as temporary:
        root = Path(temporary)
        binary = root / 'bench'
        build = ['gcc', '-O0', '-g', '-std=c11', '-Wall', '-Wextra', '-Werror',
                 '-fno-omit-frame-pointer', '-o', str(binary), 'cache_capacity.c']
        subprocess.run(build, check=True)
        cpu = min(os.sched_getaffinity(0))
        out = root / 'pilot'
        invocation = [sys.executable, 'capacity.py', 'run', '--cpu', str(cpu),
                      '--binary', str(binary), '--out', str(out), '--pilot',
                      '--samples', '32', '--steps', '16', '--sizes-kib', '4', '8',
                      '--build-command', ' '.join(build), '--notes', 'automated smoke test']
        subprocess.run(invocation, check=True)
        assert (out / 'COMPLETE').exists()
        files = list(out.glob('*.bin'))
        assert len(files) == 5
        for path in files:
            metadata = json.loads(path.with_suffix('.json').read_text())
            assert path.stat().st_size == metadata['samples'] * 8 == 256
            assert metadata['cpu'] == cpu
            assert metadata['nodes'] == metadata['bytes'] // metadata['spacing']
        # Never overwrite an existing run, and never silently accept short final runs.
        assert subprocess.run(invocation, capture_output=True).returncode != 0
        without_pilot = [arg for arg in invocation if arg != '--pilot']
        assert subprocess.run(without_pilot, capture_output=True).returncode != 0
        target = files[0]
        before = target.read_bytes()
        direct = ['taskset', '-c', str(cpu), str(binary), '4096', '8', '32', '16', '592',
                  'random', str(target)]
        assert subprocess.run(direct, capture_output=True).returncode != 0
        assert target.read_bytes() == before
        direct[6] = '0'  # sample count
        assert subprocess.run(direct, capture_output=True).returncode != 0
        if all(importlib.util.find_spec(name) for name in ('numpy', 'matplotlib')):
            subprocess.run([sys.executable, 'capacity.py', 'plot', str(out)], check=True)
            with (out / 'summary.csv').open() as stream:
                rows = list(csv.DictReader(stream))
            assert len(rows) == 5
            assert all(float(row['p5']) <= float(row['median']) <= float(row['p95']) for row in rows)
            assert all(int(row['samples']) == 32 for row in rows)
            assert (out / 'capacity.pdf').stat().st_size > 0
            assert (out / 'boxes.pdf').stat().st_size > 0
            # A broken raw file must be rejected, not summarized as a complete point.
            target.write_bytes(before[:-8])
            assert subprocess.run([sys.executable, 'capacity.py', 'plot', str(out)],
                                  capture_output=True).returncode != 0
            print('PASS: collection, validation, overwrite protection, analysis, and plots')
        else:
            print('PASS: collection and validation; plotting SKIPPED (install numpy/matplotlib)')


if __name__ == '__main__':
    main()
