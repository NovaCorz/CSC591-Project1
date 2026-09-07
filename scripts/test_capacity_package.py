"""Runnable packaging checks; use from the repository root."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('restore', 'scripts/restore_capacity_workspace.py')
restore = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restore)
with tempfile.TemporaryDirectory(prefix='capacity-package-test-') as directory:
    root = Path(directory)
    repo = root / 'repo'
    (repo / 'data_processed').mkdir(parents=True)
    raw = b'\x01\x00\x00\x00\x00\x00\x00\x00' * 32
    with gzip.open(repo / 'raw.gz', 'wb') as out:
        out.write(raw)
    row = {'original': 'results/test.bin', 'packaged': 'raw.gz', 'encoding': 'gzip',
           'decoded_sha256': hashlib.sha256(raw).hexdigest()}
    manifest = repo / 'data_processed/capacity_file_manifest.json'
    manifest.write_text(json.dumps({'files': [row]}))
    dest = root / 'restored'
    with patch.object(restore, '__file__', str(repo / 'scripts/restore.py')), patch('sys.argv', ['restore', str(dest)]):
        restore.main()
        assert (dest / 'results/test.bin').read_bytes() == raw
        try:
            restore.main()
        except AssertionError:
            pass
        else:
            raise AssertionError('Existing destination must be refused')
    row['original'] = '../escape'
    manifest.write_text(json.dumps({'files': [row]}))
    with patch.object(restore, '__file__', str(repo / 'scripts/restore.py')), patch('sys.argv', ['restore', str(root / 'unsafe')]):
        try:
            restore.main()
        except AssertionError:
            pass
        else:
            raise AssertionError('Path traversal must be refused')
    assert not (root / 'unsafe').exists()
print('PASS: lossless restore/checksum, overwrite refusal, unsafe-path refusal')
