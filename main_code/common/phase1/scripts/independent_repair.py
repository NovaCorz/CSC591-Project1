#!/usr/bin/env python3
"""Fresh matched cohorts after a blocked calibration; preserve original acquisition."""
import fcntl
import json
import os
import platform
import shutil
import time
import independent_worker as worker
from common import now,select_idle,sha,write_json


def main():
    root=worker.ROOT;cfg=json.loads((root/'config/phase1.json').read_text())
    plan=json.loads((root/'config/independent-load.json').read_text());host=platform.node().split('.')[0]
    if host not in cfg['hosts']:raise RuntimeError('Unassigned host')
    out=root/'machines'/host/plan['round'];gate=json.loads((out/'timer-gate.json').read_text())
    if gate['passed']:raise RuntimeError('Calibration already passed; use ordinary resume')
    with open(out/'worker.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        rows,digest=worker.setup(out,cfg,plan)
        generation=str(time.time_ns());history=out/'repair'/generation;history.mkdir(parents=True)
        driver=root/'scripts/independent_repair.py';driver_hash=sha(driver)
        shutil.copy2(driver,history/'independent_repair.py');write_json(history/'previous-timer-gate.json',gate)
        write_json(history/'plan.json',dict(time=now(),driver_sha256=driver_hash,generation=generation,
            rule='After quality-only calibration failure, wait for 20 consecutive one-second <=5% idle windows on a core and all SMT siblings. Acquire fresh whole cohorts under the unchanged three-attempt, first-clean policy; do not reuse earlier individual clean arms. No effect-size selection.',
            source_digest=digest))
        wait_cfg=dict(cfg,idle_windows=20)
        while True:
            idle=select_idle(rows,wait_cfg);write_json(history/('quiet-check-'+str(time.time_ns())+'.json'),idle)
            if idle['selected'] is not None:cfg['_preferred_cpu']=idle['selected']['cpu'];break
            print(json.dumps(dict(event='waiting_for_quiet_core',host=host,reason=idle['error'])),flush=True);time.sleep(15)
        original=worker.point
        def fresh(family,params,context):
            return original(family,dict(params,repair_generation=generation,repair_driver_sha256=driver_hash),context)
        worker.point=fresh
        worker.run('full',out,cfg,rows,plan,digest)


if __name__=='__main__':main()
