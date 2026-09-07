"""Restore packaged files to the original analysis layout, verifying each checksum.

    python3 scripts/restore_capacity_workspace.py NEW_DIRECTORY

Requires local data_raw/**/*.bin.gz (not stored in Git). Creates a new directory;
does not overwrite existing data. Does not launch any benchmark.
"""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    repo = Path(__file__).resolve().parent.parent
    manifest = json.loads((repo / 'data_processed/capacity_file_manifest.json').read_text())
    dest = Path(sys.argv[1]).resolve()
    assert not dest.exists(), 'Choose a new output directory'
    for row in manifest['files']:
        for name in ('original', 'packaged'):
            p = Path(row[name])
            assert not p.is_absolute() and '..' not in p.parts
        assert (repo / row['packaged']).is_file(), f'Missing packaged data: {row["packaged"]}'
    dest.mkdir(parents=True)
    for row in manifest['files']:
        source, output = repo / row['packaged'], dest / row['original']
        output.parent.mkdir(parents=True, exist_ok=True)
        if row['encoding'] == 'gzip':
            with gzip.open(source, 'rb') as src, output.open('xb') as out:
                shutil.copyfileobj(src, out)
        else:
            shutil.copy2(source, output)
        h = hashlib.sha256()
        with output.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                h.update(block)
        assert h.hexdigest() == row['decoded_sha256'], output
    print(f'Restored and verified {len(manifest["files"])} files in {dest}')
    print('Use this directory for the original relative-path commands; do not run old absolute-path commands blindly.')


if __name__ == '__main__':
    main()
