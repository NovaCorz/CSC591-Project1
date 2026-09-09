#!/usr/bin/env python3
"""Restore the complete diagnostic archive into a new, separate workspace."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--archive',type=Path,required=True);ap.add_argument('--manifest',type=Path,required=True)
    ap.add_argument('--workspace',type=Path,required=True);a=ap.parse_args()
    manifest=json.loads(a.manifest.read_text());assert a.archive.stat().st_size==manifest['bytes'] and sha(a.archive)==manifest['sha256']
    dest=a.workspace.absolute()
    if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):ap.error('Workspace must be new or empty')
    if any(p.is_symlink() for p in [dest,*dest.parents]):ap.error('Use a canonical workspace path without symlinks')
    with zipfile.ZipFile(a.archive) as z:
        for member in z.infolist():
            path=Path(member.filename);mode=(member.external_attr>>16)&0o170000
            if path.is_absolute() or '..' in path.parts or mode not in (0,0o100000,0o040000):ap.error('Unsafe archive member')
        dest.mkdir(parents=True,exist_ok=True);(dest/'.restore-incomplete').write_text(str(a.archive)+'\n')
        z.extractall(dest)
    members=json.loads((dest/'independent-load-member-sha256.json').read_text())
    assert all(sha(dest/name)==h for name,h in members.items())
    (dest/'.restore-incomplete').unlink()
    print(json.dumps(dict(passed=True,files=len(members),workspace=str(dest))))

if __name__=='__main__':main()
