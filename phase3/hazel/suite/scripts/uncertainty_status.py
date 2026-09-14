#!/usr/bin/env python3
"""Read collected markers and controller logs without disturbing lab workloads."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
    for host in json.loads((ROOT/'config/phase1.json').read_text())['hosts']:
        root=ROOT/'machines'/host/'uncertainty-v1'
        finished=[s for s in ('smoke','controls','conflict','capacity','spatial','repair_smoke','repair','capacity_repair') if (root/(s+'-finished.json')).exists()]
        folders=[p for p in (ROOT/'access/uncertainty'/host).glob('[0-9]*') if list(p.glob('*.stdout.log'))]
        result=dict(host=host,collected_stages=finished)
        if folders:
            folder=max(folders,key=lambda p:int(p.name));log=max(folder.glob('*.stdout.log'),key=lambda p:p.stat().st_mtime)
            events=[]
            for line in log.read_text().splitlines():
                try:events.append(json.loads(line))
                except json.JSONDecodeError:pass  # A live log may end mid-write.
            result.update(latest_stage=log.name.split('.')[0],clean_points_in_stage=sum(d.get('event')=='point_passed' for d in events),
                flagged_attempts_in_stage=sum(d.get('event')=='point_noisy' for d in events),
                latest_event=events[-1].get('event') if events else 'starting',log=str(log.relative_to(ROOT)))
            points=[d for d in events if d.get('event')=='point_passed']
            if points:result['latest_series']=points[-1].get('params',{}).get('series')
        print(json.dumps(result),flush=True)

if __name__=='__main__':main()
