#!/usr/bin/env python3
"""Read-only capture of current deployed source trees, independent of Git."""
import argparse
import concurrent.futures
import json
import shlex
import subprocess
import time
from common import now,sha,write_json
from phase1 import ROOT,ssh_args

def capture(host):
    root='/tmp/ece592-phase1-hlee58-'+sha(ROOT/'src/cache_bench.c')[:12]
    folder=ROOT/'access'/host/('source-snapshot-'+str(time.time_ns()));folder.mkdir(parents=True)
    destination=folder/'remote-source.tar.gz'
    cmd=ssh_args(host)+['tar -C '+shlex.quote(root)+' -czf - src scripts config']
    with open(destination,'wb') as out:p=subprocess.run(cmd,stdout=out,stderr=subprocess.PIPE,timeout=120)
    write_json(folder/'capture.json',dict(time=now(),command=cmd,returncode=p.returncode,stderr=p.stderr.decode(),
        archive_sha256=sha(destination),note='Current deployed source tree at capture time; correlate with dated deployment logs and per-run producing-source manifests. Does not rewrite historical provenance.'))
    print(json.dumps(dict(host=host,returncode=p.returncode,path=str(destination))),flush=True)
    return p.returncode==0

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--hosts',nargs='+');args=ap.parse_args()
    allowed=json.loads((ROOT/'config/phase1.json').read_text())['hosts'];hosts=args.hosts or allowed
    if set(hosts)-set(allowed):ap.error('Only assigned lab hosts allowed')
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:okay=list(pool.map(capture,hosts))
    raise SystemExit(0 if all(okay) else 1)
