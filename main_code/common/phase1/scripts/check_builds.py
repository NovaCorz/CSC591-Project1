#!/usr/bin/env python3
"""Verify saved native build/source hashes and exact-source smoke gates."""
import json
from common import now,sha,write_json
from phase1 import ROOT

def main():
    hosts=json.loads((ROOT/'config/phase1.json').read_text())['hosts'];results={}
    for host in hosts:
        errors=[];build=ROOT/'machines'/host/'full/build'
        try:
            record=json.loads((build/'verification.json').read_text())
            if record['source_sha256']!=sha(ROOT/'src/cache_bench.c') or record['source_sha256']!=sha(build/'cache_bench.c'):
                errors.append('primary source hash mismatch')
            if record['binary_sha256']!=sha(build/'cache_bench'):errors.append('binary hash mismatch')
            compile_record=json.loads((build/'compile.json').read_text())
            if compile_record['returncode'] or '-O0' not in compile_record['command']:errors.append('build did not use the required successful -O0 command')
            if not record['assembly_pattern_check'] or not (build/'critical-loop.txt').read_text().strip():errors.append('missing native dependency-loop verification')
            gate=json.loads((ROOT/'machines'/host/'smoke/smoke-passed.json').read_text())
            if gate['source_sha256']!=record['source_sha256']:errors.append('smoke gate refers to a different source')
            page=ROOT/'machines'/host/'page_control';page_build=page/'build';supplemental={}
            if not (page/'control-unavailable.json').exists():
                for name in ('cache_bench.c','page_control.c'):
                    if sha(page_build/name)!=sha(ROOT/'src'/name):errors.append('supplemental included-source mismatch: '+name)
                page_compile=json.loads((page_build/'compile.json').read_text())
                if page_compile['returncode'] or '-O0' not in page_compile['command']:errors.append('supplemental build did not pass at -O0')
                page_gate=json.loads((page/'smoke-passed.json').read_text())
                if page_gate['wrapper_sha256']!=sha(ROOT/'src/page_control.c'):errors.append('supplemental smoke gate source mismatch')
                supplemental=dict(binary_sha256=sha(page_build/'page_control'),compile_command=page_compile['command'],smoke_gate=page_gate)
            results[host]=dict(passed=not errors,errors=errors,source_sha256=record['source_sha256'],binary_sha256=record['binary_sha256'],compile_command=compile_record['command'],smoke_gate=gate,
                supplemental=supplemental,
                manual_review='docs/assembly-review.md covers both native ISA paths; wrapper traffic remains outside the repeated load loop')
        except Exception as exc:results[host]=dict(passed=False,errors=[str(exc)])
    passed=all(d['passed'] for d in results.values())
    write_json(ROOT/'data_processed/build-verification.json',dict(time=now(),passed=passed,hosts=results))
    print(json.dumps(dict(passed=passed,hosts=len(results))))
    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
