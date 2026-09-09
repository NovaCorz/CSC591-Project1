#!/usr/bin/env python3
"""Audited SSH deployment, per-host smoke gate, resumable execution and collection."""
import argparse
import concurrent.futures
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import tarfile
import tempfile
import time
from common import now, sha, write_json

ROOT = Path(__file__).resolve().parents[1]


def ssh_args(host):
    return ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '-o', 'ConnectionAttempts=1',
            '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=3', '-o', 'StrictHostKeyChecking=accept-new',
            '-o', 'UserKnownHostsFile=' + str(ROOT / 'access/known_hosts'), host + '.ece.ncsu.edu']


def bundle():
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w:gz') as tar:
        for parent in ('src', 'scripts', 'config'):
            for path in sorted((ROOT / parent).glob('*')):
                if path.is_file():
                    tar.add(str(path), arcname=str(path.relative_to(ROOT)))
    return data.getvalue()


def call(host, remote_command, log, payload=None, timeout=120):
    cmd = ssh_args(host) + [remote_command]
    started = now()
    try:
        p = subprocess.run(cmd, input=payload, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        d = dict(command=cmd, started=started, finished=now(), returncode=p.returncode,
                 stdout=p.stdout.decode(errors='replace'), stderr=p.stderr.decode(errors='replace'))
    except subprocess.TimeoutExpired as e:
        d = dict(command=cmd, started=started, finished=now(), returncode=-1, stdout='', stderr=str(e))
    write_json(log, d)
    return d


def collect(host, remote, log):
    cmd = ssh_args(host) + ['tar -C ' + shlex.quote(remote) + ' -czf - machines']
    target = log / ('collection-' + str(time.time_ns()) + '.tar.gz')
    with open(target, 'wb') as output:
        p = subprocess.run(cmd, stdout=output, stderr=subprocess.PIPE, timeout=600)
    write_json(log / 'collection.json', dict(command=cmd, time=now(), returncode=p.returncode, stderr=p.stderr.decode(), archive=str(target), sha256=sha(target)))
    if p.returncode:
        return False
    # Validate every archive member; do not extract links or paths outside this host.
    with tarfile.open(target) as tar:
        members = tar.getmembers()
        for member in members:
            path = Path(member.name)
            if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
                raise RuntimeError('Unsafe archive member')
            if path.parts[:2] not in (('machines', host),) and member.name != 'machines':
                raise RuntimeError('Unexpected archive host')
        # Publish each file atomically, so a concurrent read never sees a gzip
        # temporarily truncated by extraction. Publish references/finish markers
        # after raw files. Final analysis is still run after collection finishes.
        with tempfile.TemporaryDirectory(prefix='.phase1-collect-',dir=ROOT) as scratch:
            tar.extractall(scratch, members=members)
            paths=[p for p in Path(scratch).rglob('*') if p.is_file()]
            def publication_order(p):
                rank=2 if p.name.endswith('-finished.json') else 1 if p.name in ('run.json','complete.json') else 0
                return rank,str(p)
            for path in sorted(paths,key=publication_order):
                dest=ROOT/path.relative_to(scratch);dest.parent.mkdir(parents=True,exist_ok=True)
                os.replace(path,dest)
    # Keep a hash of the transport archive; unpacked files retain original bytes.
    target.unlink()
    return True


def run_host(host, stage, payload):
    stamp = str(time.time_ns())
    log = ROOT / 'access' / host / stamp
    log.mkdir(parents=True)
    access = call(host, 'hostname; uname -s -m; id -un', log / 'ssh.json')
    if access['returncode']:
        print(json.dumps(dict(host=host, stage=stage, status='access_failed', error=access['stderr'])), flush=True)
        return False
    if stage == 'access':
        return True
    # Stable per-source path enables resume. New source gets isolated data.
    remote = '/tmp/ece592-phase1-hlee58-' + sha(ROOT / 'src/cache_bench.c')[:12]
    deploy = call(host, 'mkdir -p ' + shlex.quote(remote) + ' && tar -xzf - -C ' + shlex.quote(remote), log / 'deploy.json', payload)
    if deploy['returncode']:
        return False
    write_json(log / 'remote.json', dict(host=host, root=remote, bundle_sha256=__import__('hashlib').sha256(payload).hexdigest()))
    cmd = ssh_args(host) + ['cd ' + shlex.quote(remote) + ' && python3 scripts/' + ('page_control_worker.py' if stage == 'controls' else 'worker.py') + (' --smoke' if stage == 'smoke' else '')]
    write_json(log / 'invocation.json', dict(command=cmd, started=now(), stage=stage))
    print(json.dumps(dict(host=host, stage=stage, status='started', log=str(log), remote=remote)), flush=True)
    with open(log / 'worker.stdout.log', 'w') as stdout, open(log / 'worker.stderr.log', 'w') as stderr:
        p = subprocess.run(cmd, stdout=stdout, stderr=stderr)
    write_json(log / 'exit.json', dict(command=cmd, finished=now(), returncode=p.returncode))
    collected = collect(host, remote, log)
    print(json.dumps(dict(host=host, stage=stage, status='finished', returncode=p.returncode, collected=collected)), flush=True)
    return p.returncode == 0 and collected


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('stage', choices=('access','smoke','full','controls','collect'))
    ap.add_argument('--hosts', nargs='+')
    ap.add_argument('--jobs', type=int, default=8)
    args = ap.parse_args()
    cfg = json.loads((ROOT / 'config/phase1.json').read_text())
    hosts = args.hosts or cfg['hosts']
    if set(hosts) - set(cfg['hosts']):
        ap.error('Only the eight specified ECE lab hosts are allowed')
    if args.stage == 'full':
        for host in hosts:
            gate = ROOT / 'machines' / host / 'smoke/smoke-passed.json'
            if not gate.exists() or json.loads(gate.read_text())['source_sha256'] != sha(ROOT / 'src/cache_bench.c'):
                ap.error('Missing passing smoke gate for ' + host)
    payload = bundle()
    # Retain the exact deployed archive as well as its hash, including producing
    # drivers/configuration. Archives are immutable and shared across this launch.
    digest = __import__('hashlib').sha256(payload).hexdigest()
    archive = ROOT / 'access' / 'bundles' / (digest + '.tar.gz')
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        archive.write_bytes(payload)
    if args.stage == 'collect':
        ok = []
        for host in hosts:
            log = ROOT / 'access' / host / str(time.time_ns()); log.mkdir(parents=True)
            remote = '/tmp/ece592-phase1-hlee58-' + sha(ROOT / 'src/cache_bench.c')[:12]
            ok.append(collect(host, remote, log))
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            ok = list(pool.map(lambda h: run_host(h, args.stage, payload), hosts))
    raise SystemExit(0 if all(ok) else 1)

if __name__ == '__main__':
    main()
