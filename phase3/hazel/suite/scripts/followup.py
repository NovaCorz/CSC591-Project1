#!/usr/bin/env python3
"""Deploy and collect the isolated second Phase-I round; never mutate baseline data."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import time
from common import now, write_json
from phase1 import ROOT, bundle, call, collect, ssh_args

def run(host,stages,payload):
    remote='/tmp/ece592-phase1-followup-hlee58-v1'
    log=ROOT/'access'/'followup'/host/str(time.time_ns());log.mkdir(parents=True)
    d=call(host,'mkdir -p '+shlex.quote(remote)+' && tar -xzf - -C '+shlex.quote(remote),log/'deploy.json',payload)
    if d['returncode']:return False
    write_json(log/'remote.json',dict(root=remote,bundle_sha256=hashlib.sha256(payload).hexdigest()))
    okay=True
    for stage in stages:
        if stage=='collect':continue
        cmd=ssh_args(host)+['cd '+shlex.quote(remote)+' && python3 scripts/followup_worker.py '+shlex.quote(stage)]
        write_json(log/(stage+'-invocation.json'),dict(command=cmd,started=now()))
        print(json.dumps(dict(host=host,stage=stage,event='started',log=str(log))),flush=True)
        with open(log/(stage+'.stdout.log'),'w') as stdout,open(log/(stage+'.stderr.log'),'w') as stderr:
            p=subprocess.run(cmd,stdout=stdout,stderr=stderr)
        write_json(log/(stage+'-exit.json'),dict(time=now(),command=cmd,returncode=p.returncode))
        print(json.dumps(dict(host=host,stage=stage,event='finished',returncode=p.returncode)),flush=True)
        if p.returncode:okay=False;break
        if not collect(host,remote,log):okay=False;break
    if stages==['collect']:okay=collect(host,remote,log)
    return okay

def main():
    ap=argparse.ArgumentParser();ap.add_argument('stages',nargs='+',choices=['smoke','spatial','capacity','conflict','cross','confirm','l2','l2confirm','collect']);ap.add_argument('--hosts',nargs='+');ap.add_argument('--after-capacity',action='store_true');ap.add_argument('--after-stage',choices=['cross','l2']);args=ap.parse_args()
    allowed=json.loads((ROOT/'config/phase1.json').read_text())['hosts'];hosts=args.hosts or allowed
    if set(hosts)-set(allowed):ap.error('Only the eight specified lab hosts are allowed')
    payload=bundle();digest=hashlib.sha256(payload).hexdigest()
    archive=ROOT/'access'/'bundles'/(digest+'.tar.gz');archive.parent.mkdir(exist_ok=True,parents=True)
    if not archive.exists():archive.write_bytes(payload)
    def queued(host):
        if args.after_capacity or args.after_stage:
            prerequisite=args.after_stage or 'capacity'
            marker=ROOT/'machines'/host/'followup-v1'/(prerequisite+'-finished.json')
            print(json.dumps(dict(host=host,event='waiting_for_completed_'+prerequisite+'_collection')),flush=True)
            while not marker.exists():time.sleep(5)
            # Snapshot the tested implementation when this host becomes ready,
            # rather than redeploying an older payload after a long queue wait.
            current=bundle();current_digest=hashlib.sha256(current).hexdigest()
            saved=ROOT/'access/bundles'/(current_digest+'.tar.gz')
            if not saved.exists():saved.write_bytes(current)
            return run(host,args.stages,current)
        return run(host,args.stages,payload)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(queued,hosts))
    raise SystemExit(0 if all(results) else 1)

if __name__=='__main__':main()
