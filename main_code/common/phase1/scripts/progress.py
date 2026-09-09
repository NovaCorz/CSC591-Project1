#!/usr/bin/env python3
"""Read-only progress snapshot; does not interrupt running benchmarks."""
import concurrent.futures
import json
from pathlib import Path
import subprocess
import time
from phase1 import ROOT, ssh_args
from common import now, write_json

REMOTE='''
from pathlib import Path
import collections,json,os,time
root=Path("/tmp/ece592-phase1-hlee58-741fb78c475d/machines")/os.uname().nodename.split(".")[0]/"full"
completed=[];attempts=[]
for p in root.glob("*/*/complete.json"):
 try: completed.append(json.loads(p.read_text()))
 except (ValueError,FileNotFoundError):pass
for p in root.glob("*/*/attempt-*/run.json"):
 try: attempts.append(json.loads(p.read_text()))
 except (ValueError,FileNotFoundError):pass
counts=dict(collections.Counter(r["family"] for r in completed))
flags=dict(collections.Counter(flag for r in attempts for flag in r.get("flags",[])))
current=[dict(parameters=r["parameters"],started=r.get("started"),command=r.get("command")) for r in attempts if r["status"]=="started"]
print(json.dumps(dict(completed=counts,flags=flags,attempt_statuses=dict(collections.Counter(r["status"] for r in attempts)),current=current,finished=(root/"collection-finished.json").exists())))
'''

def check(host):
    cmd=ssh_args(host)+['python3 -']
    p=subprocess.run(cmd,input=REMOTE.encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
    d=dict(host=host,time=now(),command=cmd,returncode=p.returncode,stdout=p.stdout.decode(),stderr=p.stderr.decode())
    if not p.returncode:d['progress']=json.loads(d['stdout'])
    write_json(ROOT/'access'/host/('progress-'+str(time.time_ns())+'.json'),d)
    return d

if __name__=='__main__':
    cfg=json.loads((ROOT/'config/phase1.json').read_text())
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for d in ex.map(check,cfg['hosts']):print(json.dumps(dict(host=d['host'],progress=d.get('progress'),error=d['stderr'])),flush=True)
