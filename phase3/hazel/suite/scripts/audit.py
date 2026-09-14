#!/usr/bin/env python3
"""Static blind-boundary audit, specification/input hash, and source manifest.
This is defense in depth, not proof against arbitrary malicious replacement code.
"""
import json
from pathlib import Path
import re
from common import now, sha, write_json
ROOT=Path(__file__).resolve().parents[1]
# Match executable cache-answer/counter interfaces; prose/specification is not scanned.
FORBIDDEN=[r'perf_event_open\s*\(',r'\b__cpuid\b',r'\bcpuid\s*[;"\\]',r'/sys/[^\s"\']*/cache/',
           r'\[\s*["\']perf["\']',r'\bPAPI_[A-Z]',r'likwid-perfctr',r'\bgetauxval\s*\(']
def audit():
    violations=[];manifest={}
    for folder in ('src','scripts','config','tests'):
        for p in sorted((ROOT/folder).glob('*')):
            if not p.is_file() or p.name=='audit.py':continue
            manifest[str(p.relative_to(ROOT))]=sha(p)
            if p.suffix in ('.py','.c','.sh'):
                s=p.read_text()
                for pat in FORBIDDEN:
                    if re.search(pat,s):violations.append(dict(file=str(p.relative_to(ROOT)),pattern=pat))
    result=dict(time=now(),passed=not violations,violations=violations,source_sha256=manifest,
        specification_sha256=sha(ROOT/'PROJECT 1 (3).pdf'),
        allowed_metadata=['hostname/uname','one CPU model line','lscpu CPU,CORE,SOCKET,NODE only','/proc/stat','process affinity/rusage','OS page size and transparent-huge-page PMD size','own mapping smaps page-backing whitelist','timer frequency','compiler/version'],
        note='No cache-specification research or PMU validation has been performed. Package downloads were PDF/plotting tools only.')
    write_json(ROOT/'data_processed/blind-audit.json',result)
    print(json.dumps(dict(passed=result['passed'],violations=violations)))
    return result
if __name__=='__main__':raise SystemExit(0 if audit()['passed'] else 1)
