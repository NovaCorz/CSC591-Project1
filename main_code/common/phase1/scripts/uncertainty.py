#!/usr/bin/env python3
"""Audited deployment and collection for additional Phase-I uncertainty tests."""
import argparse
import concurrent.futures
import hashlib
import getpass
import json
import os
from pathlib import Path
import shlex
import subprocess
import time
from common import now,write_json
from phase1 import ROOT,bundle,call,collect,ssh_args


def run(host,stages,payload):
    remote=os.environ.get('PHASE1_UNCERTAINTY_REMOTE','/tmp/ece592-phase1-uncertainty-'+getpass.getuser()+'-v1')
    log=ROOT/'access/uncertainty'/host/str(time.time_ns());log.mkdir(parents=True)
    access=call(host,'hostname; uname -s -m; id -un',log/'access.json')
    if access['returncode']:return False
    if stages==['access']:return True
    if stages!=['collect']:
        d=call(host,'mkdir -p '+shlex.quote(remote)+' && tar -xzf - -C '+shlex.quote(remote),log/'deploy.json',payload)
        if d['returncode']:return False
    write_json(log/'remote.json',dict(root=remote,bundle_sha256=hashlib.sha256(payload).hexdigest()))
    for stage in stages:
        if stage=='collect':return collect(host,remote,log)
        cmd=ssh_args(host)+['cd '+shlex.quote(remote)+' && python3 scripts/uncertainty_worker.py '+shlex.quote(stage)]
        write_json(log/(stage+'-invocation.json'),dict(command=cmd,started=now()))
        print(json.dumps(dict(host=host,stage=stage,event='started',log=str(log))),flush=True)
        with open(log/(stage+'.stdout.log'),'w') as stdout,open(log/(stage+'.stderr.log'),'w') as stderr:
            p=subprocess.run(cmd,stdout=stdout,stderr=stderr)
        write_json(log/(stage+'-exit.json'),dict(time=now(),returncode=p.returncode,command=cmd))
        collected=collect(host,remote,log)
        print(json.dumps(dict(host=host,stage=stage,event='finished',returncode=p.returncode,collected=collected)),flush=True)
        if p.returncode or not collected:return False
    return True


def main():
    ap=argparse.ArgumentParser();ap.add_argument('stages',nargs='+',choices=['access','smoke','controls','conflict','capacity','spatial','repair_smoke','repair','capacity_repair','collect']);ap.add_argument('--hosts',nargs='+');ap.add_argument('--after-spatial',action='store_true');ap.add_argument('--after-conflict-repair',action='store_true');args=ap.parse_args()
    allowed=json.loads((ROOT/'config/phase1.json').read_text())['hosts'];hosts=args.hosts or allowed
    if set(args.stages)<={'repair_smoke','repair'} and not args.hosts:hosts=['crux','thunderbird']
    if args.stages==['capacity_repair'] and not args.hosts:hosts=['sunbird','charnwood','crux','upgrade']
    if set(hosts)-set(allowed):ap.error('Only the eight specified hosts')
    if 'repair' in args.stages and set(hosts)-{'crux','thunderbird'}:ap.error('Conflict quality repairs apply to Crux and Thunderbird')
    payload=bundle();digest=hashlib.sha256(payload).hexdigest();archive=ROOT/'access/bundles'/(digest+'.tar.gz')
    archive.parent.mkdir(exist_ok=True,parents=True)
    if not archive.exists():archive.write_bytes(payload)
    def queued(host):
        if args.after_conflict_repair and host=='crux':
            while not (ROOT/'machines'/host/'uncertainty-v1/repair-finished.json').exists():time.sleep(5)
        if args.after_spatial:
            while not (ROOT/'machines'/host/'uncertainty-v1/spatial-finished.json').exists():time.sleep(5)
            current=bundle();digest=hashlib.sha256(current).hexdigest();saved=ROOT/'access/bundles'/(digest+'.tar.gz')
            if not saved.exists():saved.write_bytes(current)
            return run(host,args.stages,current)
        return run(host,args.stages,payload)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(queued,hosts))
    raise SystemExit(0 if all(results) else 1)

if __name__=='__main__':main()
