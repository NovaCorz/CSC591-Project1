#!/usr/bin/env python3
"""Verify a curated selected-raw directory against its SHA-256 manifest."""
import argparse, hashlib, json
from pathlib import Path

def sha256(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args=parser.parse_args()
    manifest=json.loads((args.directory/'manifest.json').read_text())
    root=Path.cwd()
    problems=[]
    for item in manifest['file_inventory']:
        path=root/item['path']
        if not path.is_file():
            problems.append(f"missing: {path}")
        elif path.stat().st_size != item['bytes']:
            problems.append(f"size mismatch: {path}")
        elif sha256(path) != item['sha256']:
            problems.append(f"SHA-256 mismatch: {path}")
    if problems:
        print('\n'.join(problems))
        raise SystemExit(1)
    print(f"PASS: {manifest['phase']}: {manifest['records']} records, "
          f"{manifest['samples']} timed samples, {len(manifest['file_inventory'])} files")
if __name__ == '__main__':
    main()
