#!/usr/bin/env python3
"""Verify and restore the immutable Phase-I evidence archives externally."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'data_processed/all_machines/archive-manifest.json'
MARKER = '.phase1-restore.json'


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def member_path(info):
    name = info.filename
    p = PurePosixPath(name)
    mode = info.external_attr >> 16
    if (not name or '\\' in name or p.is_absolute() or '..' in p.parts
            or ':' in name or not p.parts or p.parts[0] in ('.git', MARKER)
            or any(part in ('', '.') for part in name.rstrip('/').split('/'))
            or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
        raise ValueError('Unsafe archive member: ' + name)
    return Path(*p.parts)


def validate_destination(destination, manifest):
    raw = Path(destination).absolute()
    if any(p.is_symlink() for p in (raw, *raw.parents)):
        raise ValueError('Workspace path must not contain symlinks')
    dest = raw.resolve()
    protected = [ROOT, Path(manifest['source_workspace']).resolve()]
    for path in protected:
        if dest == path or path in dest.parents or dest in path.parents:
            raise ValueError('Workspace must be separate from the clone and source repository')
    if dest.exists():
        if not dest.is_dir():
            raise ValueError('Workspace is not a directory')
        if any(dest.iterdir()):
            raise ValueError('Workspace must be empty; choose a new directory for each restore')
    return dest


def verify_archives(directory, manifest):
    checked = []
    specs = {a['name']: a for a in manifest['archives']}
    for name in manifest['restore_order']:
        expected = specs[name]
        path = Path(directory) / name
        if not path.is_file() or path.stat().st_size != expected['bytes']:
            raise ValueError('Archive missing or size mismatch: ' + str(path))
        digest = sha(path)
        if digest != expected['sha256']:
            raise ValueError('Archive SHA256 mismatch: ' + str(path))
        with zipfile.ZipFile(path) as archive:
            seen = set()
            for info in archive.infolist():
                relative = member_path(info)
                if relative in seen:
                    raise ValueError('Duplicate member within archive: ' + str(relative))
                seen.add(relative)
        checked.append(dict(name=name, sha256=digest, bytes=expected['bytes'], members=len(seen)))
        print('Verified ' + name, flush=True)
    return checked


def restore(directory, destination, manifest, checked):
    destination.mkdir(parents=True, exist_ok=True)
    state = dict(schema=1, complete=False, archives=checked, completed_archives=[])
    marker = destination / MARKER
    marker.write_text(json.dumps(state, indent=2) + '\n')
    for entry in checked:
        with zipfile.ZipFile(Path(directory) / entry['name']) as archive:
            for info in archive.infolist():
                target = destination / member_path(info)
                if any(p.is_symlink() for p in (target, *target.parents)):
                    raise ValueError('Symlink appeared in destination: ' + str(target))
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open('wb') as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
                mode = info.external_attr >> 16
                target.chmod(0o755 if mode & 0o111 else 0o644)
        state['completed_archives'].append(entry['name'])
        marker.write_text(json.dumps(state, indent=2) + '\n')
        print('Restored ' + entry['name'], flush=True)
    state['complete'] = True
    marker.write_text(json.dumps(state, indent=2) + '\n')
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-dir', type=Path, required=True)
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text())
    if not args.check_only and args.workspace is None:
        parser.error('--workspace is required unless --check-only is used')
    dest = validate_destination(args.workspace, manifest) if args.workspace else None
    if dest and (dest == args.archive_dir.resolve() or dest in args.archive_dir.resolve().parents):
        raise ValueError('Workspace cannot contain the input archives')
    checked = verify_archives(args.archive_dir, manifest)
    if not args.check_only:
        restore(args.archive_dir, dest, manifest, checked)
        print('Complete external workspace: ' + str(dest))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        print('Restore failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
