#!/usr/bin/env python3
"""Check curated file hashes, directory preservation and result completeness."""
import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resolve', help='Resolve an original source path through the import manifest')
    args = parser.parse_args()
    folder = ROOT / 'data_processed/all_machines'
    imported = json.loads((folder / 'import-manifest.json').read_text())
    if args.resolve:
        matches = [d['destination'] for d in imported['files'] if d['source'] == args.resolve]
        if matches:
            print('\n'.join(str(ROOT / p) for p in matches))
        else:
            print('External archive member: ' + args.resolve)
            
            if 'independent-load' in args.resolve:
                print('Use the separate phase1-independent-load.zip and main_code/common/phase1/scripts/restore_independent.py.')
            else:
                print('Restore both original archives in archive-manifest.json order; the original supplement takes precedence.')
        return
    inventory = json.loads((folder / 'curated-files.json').read_text())
    problems = []
    for rel, expected in inventory['files'].items():
        p = ROOT / rel
        if not p.is_file() or p.is_symlink():
            problems.append('Missing file or symlink: ' + rel)
        elif p.stat().st_size != expected['bytes'] or sha(p) != expected['sha256']:
            problems.append('Changed file: ' + rel)
    for rel in imported['preserved_directories']:
        if not (ROOT / rel).is_dir():
            problems.append('Missing original directory: ' + rel)
    actual = set()
    for base, dirs, files in os.walk(ROOT):
        if Path(base) == ROOT:
            dirs[:] = [d for d in dirs if d != '.git']
        for d in dirs:
            if (Path(base) / d).is_symlink():
                problems.append('Unexpected directory symlink: ' + str(Path(base) / d))
        for name in files:
            p = Path(base) / name
            rel = str(p.relative_to(ROOT))
            actual.add(rel)
            if p.relative_to(ROOT).parts[0] in ('report', 'slides') and (name != '.gitkeep' or p.stat().st_size):
                problems.append('Report/slide payload: ' + rel)
    allowed = set(inventory['files']) | {'data_processed/all_machines/curated-files.json'}
    if actual != allowed:
        problems.append('Unexpected/missing files: ' + str(sorted(actual ^ allowed)))
    final = json.loads((folder / 'final-verification.json').read_text())
    expected = dict(selected_points=2067, full_attempts=2483, smoke_attempts=36,
                    noisy_selected=140, flagged_attempts=556)
    if not final['complete'] or len(final['hosts']) != 8:
        problems.append('Final verification is incomplete')
    for key, value in expected.items():
        if final[key] != value:
            problems.append('Final count differs: ' + key)
    for entry in imported['files']:
        p = ROOT / entry['destination']
        if not p.is_file() or sha(p) != entry['sha256']:
            problems.append('Import hash differs: ' + entry['destination'])
    print(json.dumps(dict(passed=not problems, files=len(actual),
                         preserved_directories=len(imported['preserved_directories']),
                         results=expected, problems=problems), indent=2))
    raise SystemExit(bool(problems))


if __name__ == '__main__':
    main()
