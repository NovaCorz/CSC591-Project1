"""Copy an existing capacity workspace into the team's submission layout.

    python3 package_capacity.py SOURCE_WORKSPACE SUBMISSION_REPOSITORY

Never overwrites an existing destination file. Raw .bin files are gzip-compressed.
"""
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys


HOSTS = {'sunbird', 'thunderbird', 'skylark', 'artemisia', 'charnwood', 'crux', 'ookay', 'upgrade'}


def destination(relative):
    p = Path(relative)
    if p.parts[0] != 'results':
        if p.suffix == '.c':
            return Path('main_code/common') / p
        if p.suffix in ('.py', '.json'):
            return Path('scripts') / p
        return Path('report/capacity') / p
    campaign, *rest = p.parts[1:]
    host = rest.pop(0) if rest and rest[0] in HOSTS else ('sunbird' if campaign.startswith('sunbird-') else 'all_machines')
    tail = Path(campaign, *rest)
    if p.suffix in ('.c', '.py'):
        return Path('main_code/common/snapshots') / host / tail
    if p.suffix in ('.pdf', '.png'):
        return Path('plots/capacity') / host / tail
    if p.suffix == '.csv' or host == 'all_machines':
        return Path('data_processed') / host / 'capacity' / tail
    result = Path('data_raw') / host / 'capacity' / tail
    return Path(str(result) + '.gz') if p.suffix == '.bin' else result


def digest(path, compressed=False):
    h = hashlib.sha256()
    with (gzip.open(path, 'rb') if compressed else path.open('rb')) as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    source, target = map(lambda x: Path(x).resolve(), sys.argv[1:])
    assert source != target and (target / '.git').is_dir()
    assert destination('results/capacity-20260906/crux/full/random_4KiB.bin') == Path('data_raw/crux/capacity/capacity-20260906/full/random_4KiB.bin.gz')
    assert destination('results/sunbird-repeat-X/repeat1/summary.csv') == Path('data_processed/sunbird/capacity/sunbird-repeat-X/repeat1/summary.csv')
    files = [p for p in source.iterdir() if p.is_file() and p.suffix in ('.py', '.c', '.json', '.md')]
    files += [p for p in (source / 'results').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    mapping = {str(p.relative_to(source)): str(destination(p.relative_to(source))) for p in files}
    assert len(set(mapping.values())) == len(mapping)
    manifest_path = target / 'data_processed/capacity_file_manifest.json'
    assert not manifest_path.exists()
    for relative in mapping.values():
        assert not (target / relative).exists(), relative
    records = []
    for i, p in enumerate(sorted(files), 1):
        original = str(p.relative_to(source))
        dest = target / mapping[original]
        dest.parent.mkdir(parents=True, exist_ok=True)
        compressed = p.suffix == '.bin'
        original_hash = digest(p)
        if compressed:
            with p.open('rb') as src, dest.open('xb') as raw:
                with gzip.GzipFile(filename='', fileobj=raw, mode='wb', compresslevel=1, mtime=0) as out:
                    shutil.copyfileobj(src, out)
        elif p.suffix == '.md':
            # Mechanical link relocation; historical commands/prose remain unchanged.
            def relocate(match):
                link = match.group(1)
                candidate = link.removeprefix(str(source) + '/')
                if candidate in mapping:
                    return '](' + os.path.relpath(target / mapping[candidate], dest.parent) + ')'
                return match.group(0)
            text = re.sub(r'\]\(([^)]+)\)', relocate, p.read_text())
            with dest.open('x') as out:
                out.write(text)
        else:
            shutil.copy2(p, dest)
        verified_hash = digest(dest, compressed)
        if p.suffix != '.md':
            assert original_hash == verified_hash, original
        records.append(dict(original=original, packaged=mapping[original], original_bytes=p.stat().st_size,
                            packaged_bytes=dest.stat().st_size, original_sha256=original_hash,
                            decoded_sha256=verified_hash, encoding='gzip' if compressed else 'identity'))
        if i % 250 == 0:
            print(f'Copied and verified {i}/{len(files)} files', flush=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open('x') as out:
        json.dump({'source_workspace': str(source), 'files': records,
                   'note': 'Raw gzip files are local Moodle data, intentionally excluded from Git. Markdown links mechanically relocated.'}, out, indent=2)
        out.write('\n')
    print(f'Copied and verified {len(records)} files; raw files: {sum(r["encoding"] == "gzip" for r in records)}', flush=True)


if __name__ == '__main__':
    main()
