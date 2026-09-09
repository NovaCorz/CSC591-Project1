#!/usr/bin/env python3
"""Archive every diagnostic attempt and its producing/analysis sources externally."""
import hashlib
import json
from pathlib import Path
import zipfile
from common import now,sha,write_json
ROOT=Path(__file__).resolve().parents[1]

def main():
    verified=json.loads((ROOT/'data_processed/independent-load/verification.json').read_text())
    assert verified['passed'] and verified['all_hosts']
    paths=[]
    for host in verified['hosts']:paths+=list((ROOT/'machines'/host/'independent-load-v1').rglob('*'))
    for folder in ['access/independent-load','data_processed/independent-load','plots/independent-load']:paths+=list((ROOT/folder).rglob('*'))
    paths += [ROOT/n for n in ['src/cache_bench.c','src/independent_load.c','scripts/common.py','scripts/worker.py','scripts/phase1.py',
        'scripts/independent_worker.py','scripts/independent_repair.py','scripts/independent_load.py',
        'scripts/analyze_independent.py','scripts/plot_independent.py','scripts/package_independent.py',
        'scripts/restore_independent.py','tests/test_independent.py','config/phase1.json','config/independent-load.json','docs/independent-load-method.md']]
    files=sorted({p for p in paths if p.is_file() and p.name!='archive-manifest.json' and '__pycache__' not in p.parts})
    archive=ROOT/'artifacts/phase1-independent-load.zip'
    if archive.exists():raise RuntimeError('Archive exists; do not overwrite a published evidence archive')
    hashes={str(p.relative_to(ROOT)):sha(p) for p in files}
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in files:z.write(p,str(p.relative_to(ROOT)))
        z.writestr('independent-load-member-sha256.json',json.dumps(hashes,indent=2)+'\n')
    with zipfile.ZipFile(archive) as z:
        for name,h in hashes.items():
            digest=hashlib.sha256()
            with z.open(name) as stream:
                for b in iter(lambda:stream.read(1024*1024),b''):digest.update(b)
            assert digest.hexdigest()==h,name
    write_json(ROOT/'data_processed/independent-load/archive-manifest.json',dict(time=now(),filename=archive.name,bytes=archive.stat().st_size,
        sha256=sha(archive),members=len(hashes)+1,all_member_hashes_verified=True,
        scope='Every diagnostic raw/failed/noisy attempt, idle evidence, commands, environments, native builds, source snapshots, analysis and plots. Separate supplement; prior archives unchanged.'))
    print(archive)

if __name__=='__main__':main()
