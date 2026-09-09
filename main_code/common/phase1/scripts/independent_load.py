#!/usr/bin/env python3
"""Deploy the diagnostic to assigned hosts; collect every completed/failed attempt."""
import argparse
import concurrent.futures
import getpass
import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import tarfile
import time
import phase1
from common import now,write_json
from independent_worker import FILES

ROOT=Path(__file__).resolve().parents[1]


def ssh_args(host):
    return ['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15',
        '-o','ServerAliveInterval=30','-o','ServerAliveCountMax=3','-o','StrictHostKeyChecking=yes',
        '-o','UserKnownHostsFile='+str(ROOT/'access/known_hosts'),host+'.ece.ncsu.edu']


phase1.ssh_args=ssh_args


def payload():
    buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w:gz') as tar:
        for name in FILES+['scripts/independent_repair.py']:tar.add(ROOT/name,arcname=name)
    return buf.getvalue()


def run(host,stages,data,digest):
    log=ROOT/'access/independent-load'/host/str(time.time_ns());log.mkdir(parents=True)
    remote='/tmp/ece592-independent-'+getpass.getuser()+'-'+digest[:12]
    if phase1.call(host,'hostname; uname -s -m; id -un',log/'access.json')['returncode']:return False
    if stages==['access']:return True
    if stages!=['collect']:
        if phase1.call(host,'mkdir -p '+shlex.quote(remote)+' && tar -xzf - -C '+shlex.quote(remote),log/'deploy.json',data)['returncode']:return False
    write_json(log/'remote.json',dict(root=remote,source_digest=digest,bundle_sha256=hashlib.sha256(data).hexdigest()))
    for stage in stages:
        if stage=='access':continue
        if stage=='collect':return phase1.collect(host,remote,log)
        if stage in ('full','repair'):
            state=remote+'/machines/'+host+'/independent-load-v1'
            history=state+'/history/'+str(time.time_ns())
            snapshot='mkdir -p '+shlex.quote(history)+'; '
            snapshot+='for name in timer-gate.json cohorts.json full-finished.json; do '
            snapshot+='if test -f '+shlex.quote(state)+'/$name; then cp -p '+shlex.quote(state)+'/$name '+shlex.quote(history)+'/; fi; done'
            if phase1.call(host,snapshot,log/'state-snapshot.json')['returncode']:return False
        worker_command='scripts/independent_repair.py' if stage=='repair' else 'scripts/independent_worker.py '+stage
        cmd=ssh_args(host)+['cd '+shlex.quote(remote)+' && python3 '+worker_command]
        write_json(log/(stage+'-invocation.json'),dict(time=now(),command=cmd))
        print(json.dumps(dict(host=host,stage=stage,event='started',log=str(log))),flush=True)
        with open(log/(stage+'.stdout.log'),'w') as stdout,open(log/(stage+'.stderr.log'),'w') as stderr:
            p=subprocess.run(cmd,stdout=stdout,stderr=stderr)
        write_json(log/(stage+'-exit.json'),dict(time=now(),returncode=p.returncode))
        collected=phase1.collect(host,remote,log)
        print(json.dumps(dict(host=host,stage=stage,event='finished',returncode=p.returncode,collected=collected)),flush=True)
        if p.returncode or not collected:return False
    return True


def main():
    ap=argparse.ArgumentParser();ap.add_argument('stages',nargs='+',choices=['access','smoke','full','repair','collect']);ap.add_argument('--hosts',nargs='+');a=ap.parse_args()
    allowed=json.loads((ROOT/'config/phase1.json').read_text())['hosts'];hosts=a.hosts or allowed
    if set(hosts)-set(allowed):ap.error('Only assigned lab hosts allowed')
    from independent_worker import source_manifest
    _,digest=source_manifest();data=payload()
    archive=ROOT/'access/independent-load/bundles'/(hashlib.sha256(data).hexdigest()+'.tar.gz')
    archive.parent.mkdir(parents=True,exist_ok=True)
    if not archive.exists():archive.write_bytes(data)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda host:run(host,a.stages,data,digest),hosts))
    raise SystemExit(0 if all(results) else 1)


if __name__=='__main__':main()
