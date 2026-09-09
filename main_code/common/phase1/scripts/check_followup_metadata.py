#!/usr/bin/env python3
"""Audit record references and independently recompute all follow-up smoke data."""
import json
from pathlib import Path
from common import now,read_raw,sha,statistics_agree,stats,write_json
ROOT=Path(__file__).resolve().parents[1]

def main():
    problems=[];aliases=[];records=0;smokes=0;incomplete=[]
    hosts=json.loads((ROOT/'config/phase1.json').read_text())['hosts']
    for host in hosts:
        root=ROOT/'machines'/host/'followup-v1'
        for path in sorted(root.rglob('run.json')):
            d=json.loads(path.read_text());base=path.parents[3];records+=1
            if d.get('raw'):
                raw=base/d['raw']
                if not raw.exists():problems.append(dict(record=str(path.relative_to(ROOT)),reason='missing raw file'))
                elif d['parameters']['samples']<1000000:
                    smokes+=1;values=read_raw(raw,d['measurement']['little_endian'])
                    recomputed=stats(values,d['parameters'].get('timed_loads',d['parameters']['batch']))
                    if len(values)!=2048 or sha(raw)!=d['raw_sha256'] or not statistics_agree(recomputed,d['statistics']):
                        problems.append(dict(record=str(path.relative_to(ROOT)),reason='functional smoke raw/statistics mismatch'))
            else:incomplete.append(dict(record=str(path.relative_to(ROOT)),status=d.get('status'),reason=d.get('error',d.get('reason'))))
            for field in ('environment_record','provenance_manifest'):
                if not d.get(field):continue
                target=base/d[field]
                if not target.exists():
                    # Historical conflict-smoke records omitted a parent prefix.
                    # Preserve their bytes and publish an explicit resolver map.
                    alternative=root/d[field]
                    if base.name=='conflict-smoke' and alternative.exists():
                        aliases.append(dict(record=str(path.relative_to(ROOT)),field=field,stored=d[field],resolved=str(alternative.relative_to(ROOT)),
                            reason='Historical conflict-smoke reference was relative to the main follow-up root; original record remains unchanged'))
                    else:problems.append(dict(record=str(path.relative_to(ROOT)),reason='unresolved '+field,stored=d[field]))
    result=dict(time=now(),passed=not problems,records=records,smoke_distributions_recomputed=smokes,
        historical_reference_resolutions=aliases,incomplete_records=incomplete,problems=problems)
    write_json(ROOT/'data_processed/followup/metadata-reference-audit.json',result)
    print(json.dumps(dict(passed=result['passed'],records=records,smokes=smokes,resolved_historical_references=len(aliases),problems=problems)),flush=True)
    raise SystemExit(0 if not problems else 1)

if __name__=='__main__':main()
