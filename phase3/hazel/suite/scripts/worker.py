#!/usr/bin/env python3
"""Runs locally ON an allowed ECE host. Never execute this on an HPC login node."""
import argparse
import datetime
import fcntl
import gzip
import json
import os
from pathlib import Path
import platform
import random
import re
import shutil
import subprocess
import sys
import time
import traceback
from common import choose_idle_pair, activity, choose_idle, now, read_raw, select_idle, sha, stats, topology, utilization, write_json

ROOT = Path(__file__).resolve().parents[1]


def command(cmd, folder, name, timeout=120):
    start = now()
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=timeout)
        d = dict(command=cmd, cwd=str(Path.cwd()), started=start, finished=now(), returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)
    except subprocess.TimeoutExpired as e:
        d = dict(command=cmd, cwd=str(Path.cwd()), started=start, finished=now(), returncode=-1, stdout=str(e.stdout), stderr='timeout: ' + str(e.stderr))
    write_json(folder / (name + '.json'), d)
    if d['returncode']:
        raise RuntimeError(name + ' failed: ' + d['stderr'])
    return d['stdout']


def build(folder):
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / 'src/cache_bench.c', folder / 'cache_bench.c')
    flags = ['-O0', '-g', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fno-omit-frame-pointer']
    compiler = shutil.which('gcc')
    if not compiler:
        raise RuntimeError('gcc unavailable')
    command([compiler, '--version'], folder, 'compiler')
    command([compiler] + flags + ['cache_bench.c', '-o', 'cache_bench'], folder, 'compile')
    command([compiler] + flags + ['-S', 'cache_bench.c', '-o', 'cache_bench.s'], folder, 'assembly')
    dis = command(['objdump', '-d', 'cache_bench'], folder, 'objdump')
    (folder / 'cache_bench.dis').write_text(dis)
    match = re.search(r'<chase>:\n(.*?)(?=\n\n)', dis, re.S)
    if not match:
        raise RuntimeError('chase disassembly not found')
    excerpt = match.group(0)
    expected = ('ldr' in excerpt and 'b.ne' in excerpt) if platform.machine() == 'aarch64' else ('mov' in excerpt and 'jne' in excerpt)
    if not expected:
        raise RuntimeError('dependent loop assembly check failed')
    (folder / 'critical-loop.txt').write_text(excerpt)
    write_json(folder / 'verification.json', dict(source_sha256=sha(folder / 'cache_bench.c'), binary_sha256=sha(folder / 'cache_bench'),
               flags=flags, assembly_pattern_check=expected, caveat='Pattern check supplemented by manual instruction inspection; O0 wrapper overhead retained'))


def point(family, params, context):
    out, config, rows, smoke = context
    source_digest = config.get('_source_digest', sha(ROOT / 'src/cache_bench.c'))
    if config.get('_use_noise_history') and '_recent_noisy_cores' not in config:
        history=[]
        for path in out.glob('*/*/attempt-*/run.json'):
            try:
                prior=json.loads(path.read_text())
                stamp=datetime.datetime.fromisoformat(prior.get('finished','')).timestamp()
                if prior.get('flags') and time.time()-stamp<900:
                    history.append(dict(time=stamp,cpu=prior['selected']['cpu'],record=str(path.relative_to(out))))
            except (ValueError,KeyError,OSError):pass
        config['_recent_noisy_cores']=history
    if (ROOT / 'stop-after-point').exists():
        raise InterruptedError('Cooperative stop requested between configurations')
    identity = dict(params, samples=2048 if smoke else config['samples'])
    key = __import__('hashlib').sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    base = out / family / key
    base.mkdir(parents=True, exist_ok=True)
    done = base / 'complete.json'
    if done.exists():
        prior = json.loads(done.read_text())
        raw = out / prior['raw']
        if raw.exists() and sha(raw) == prior['raw_sha256'] and prior['source_sha256'] == source_digest:
            if not config.get('_use_noise_history') or '_preferred_cpu' not in config:
                config['_preferred_cpu'] = prior['selected']['cpu']
            return prior
        raise RuntimeError('Resume integrity mismatch: ' + str(done))
    avoided = []
    for attempt in range(config['attempts']):
        attempt_dir = base / ('attempt-' + str(time.time_ns()))
        attempt_dir.mkdir()
        record = dict(parameters=identity, family=family, started=now(), source_sha256=source_digest, status='started',
                      environment_record=config.get('_environment_record'), provenance_manifest=config.get('_provenance_manifest'))
        try:
            while True:
                history=[d for d in config.get('_recent_noisy_cores',[]) if time.time()-d['time']<900]
                if config.get('_use_noise_history'):config['_recent_noisy_cores']=history
                by_cpu={r['cpu']:r for r in rows}
                domain_cores={}
                for entry in history:
                    row=by_cpu.get(entry['cpu'])
                    if row:domain_cores.setdefault((row['socket'],row['node']),set()).add(row['core'])
                noisy_domains={domain for domain,cores in domain_cores.items() if len(cores)>=3}
                domain_avoid=[r['cpu'] for r in rows if (r['socket'],r['node']) in noisy_domains]
                idle = select_idle(rows, config, avoided+[d['cpu'] for d in history]+domain_avoid)
                if config.get('_use_noise_history'):
                    idle['recent_noise_history']=history
                    idle['recent_noisy_domains']=[list(d) for d in sorted(noisy_domains)]
                    idle['history_policy']='Deprioritize physical cores with flagged attempts in preceding 900 seconds, and domains with >=3 such physical cores, before domain preference; still require every idle window. If all qualifying cores have history, retain the flags and select by the remaining idle/domain criteria.'
                if params.get('paired_core') and idle['selected'] is not None:
                    try:
                        idle['selected'],idle['helper']=choose_idle_pair(rows,[w['busy_fraction'] for w in idle['evidence']],
                            set(os.sched_getaffinity(0)),config['idle_fraction'],
                            avoided+[d['cpu'] for d in history]+domain_avoid,idle['selected']['cpu'])
                    except RuntimeError as exc:
                        idle['selected']=None;idle['error']=str(exc)+'; waiting for a pair'
                write_json(attempt_dir / ('idle-check-' + str(time.time_ns()) + '.json'), idle)
                if idle['selected'] is not None:
                    write_json(attempt_dir / 'idle.json', idle)
                    break
                record.update(status='waiting_for_idle', reason=idle['error'])
                write_json(attempt_dir / 'run.json', record)
                print(json.dumps(dict(event='waiting_for_idle', family=family, reason=idle['error'], next_check_seconds=15)), flush=True)
                time.sleep(15)
            record['status'] = 'started'
            cpu = idle['selected']['cpu']
            config['_preferred_cpu'] = cpu
            avoided.append(cpu)
            raw = attempt_dir / 'samples.u64'
            cmd = [str(config.get('_benchmark_path', out / 'build/cache_bench')), params['mode'], str(params['bytes']), str(params['stride']), str(params.get('offset', 0)),
                   str(identity['samples']), str(params['batch']), str(params['seed']), str(cpu), params['order'], str(raw)]
            if 'extra_args' in params:
                cmd += [str(v) for v in params['extra_args']]
                if params.get('paired_core'):
                    cmd[-1] = str(idle['helper']['cpu'])
            record['command'] = cmd
            write_json(attempt_dir / 'run.json', record)
            before = activity()
            t0 = time.monotonic()
            with open(attempt_dir / 'stdout.log', 'w') as stdout, open(attempt_dir / 'stderr.log', 'w') as stderr:
                p = subprocess.Popen(cmd, stdout=stdout, stderr=stderr)
                record['pid'] = p.pid
                # Check actual process affinity without reading any cache data.
                try:
                    record['observed_affinity_initial'] = sorted(os.sched_getaffinity(p.pid))
                except ProcessLookupError:
                    record['observed_affinity_initial'] = []
                trace = []
                while p.poll() is None:
                    try:
                        p.wait(timeout=1.0)
                    except subprocess.TimeoutExpired:
                        pass
                    after = activity()
                    trace.append(dict(time=now(), before=before, after=after, busy_fraction=utilization(before, after)))
                    before = after
                    if time.monotonic() - t0 > config['point_timeout_seconds']:
                        p.kill(); p.wait()
                        record['timeout'] = True
                        break
            record['returncode'] = p.returncode
            write_json(attempt_dir / 'activity.json', trace)
            if p.returncode:
                raise RuntimeError('benchmark failed: ' + (attempt_dir / 'stderr.log').read_text())
            meta = json.loads((attempt_dir / 'stdout.log').read_text())
            record['measurement'] = meta
            if config.get('_page_control'):
                record['page_control'] = json.loads(Path(str(raw) + '.pages.json').read_text())
            values = read_raw(raw, meta['little_endian'])
            if len(values) != identity['samples'] or meta['samples'] != len(values):
                raise RuntimeError('raw sample count mismatch')
            divisor = params.get('timed_loads', 1 if params['mode'] in ('overhead', 'reload') else params['batch'])
            record['statistics'] = stats(values, divisor)
            # Separate sequential blocks expose drift without discarding any samples.
            block = max(1, len(values) // 10)
            record['block_medians'] = [stats(values[i:i+block], divisor)['median'] for i in range(0, len(values), block)]
            flags = []
            if meta['final_cpu'] != cpu or meta['cpu'] != cpu:
                flags.append('affinity mismatch')
            if meta['major_faults']:
                flags.append('major page faults during measurement')
            if meta['involuntary_switches'] > max(5, meta['elapsed_ns'] / 1e9 * 5):
                flags.append('frequent involuntary context switches')
            siblings = set(idle['selected']['siblings']) - {cpu}
            if params.get('paired_core'):
                siblings |= set(idle['helper']['siblings']) - {idle['helper']['cpu']}
                record['helper_selected'] = idle['helper']
                if meta.get('helper_cpu') != idle['helper']['cpu']:
                    flags.append('helper affinity mismatch')
            if any(w['busy_fraction'].get(s, 1) > config['idle_fraction'] for w in trace for s in siblings):
                flags.append('SMT sibling became busy')
            medians = record['block_medians']
            if max(medians) > 1.20 * max(min(medians), 1e-9) and (max(medians)-min(medians))*divisor > 2:
                flags.append('block median drift exceeds 20 percent')
            if params['mode'] in ('chase', 'spatial') and params['batch'] > 1 and record['statistics']['zero_samples'] > .01 * len(values):
                flags.append('timer resolution: more than 1 percent zero intervals')
            record['flags'] = flags
            if flags and config.get('_use_noise_history'):
                config['_recent_noisy_cores'].append(dict(time=time.time(),cpu=cpu,record=str((attempt_dir/'run.json').relative_to(out))))
            gz = raw.with_suffix('.u64.gz')
            with open(raw, 'rb') as src, open(gz, 'wb') as dst:
                with gzip.GzipFile(fileobj=dst, mode='wb', mtime=0) as z:
                    shutil.copyfileobj(src, z)
            if read_raw(gz, meta['little_endian']) != values:
                raise RuntimeError('lossless compression verification failed')
            raw.unlink()
            record.update(raw=str(gz.relative_to(out)), raw_sha256=sha(gz), finished=now(), status='noisy' if flags else 'passed',
                          selected=idle['selected'], attempt=str(attempt_dir.relative_to(out)), exact_raw_count=len(values))
            write_json(attempt_dir / 'run.json', record)
            if flags:
                print(json.dumps(dict(event='point_noisy', family=family, flags=flags, attempt=str(attempt_dir))), flush=True)
            if not flags:
                write_json(done, record)
                print(json.dumps(dict(event='point_passed', family=family, params=params, median=record['statistics']['median'])), flush=True)
                return record
        except Exception as e:
            record.update(status='failed', error=str(e), finished=now())
            write_json(attempt_dir / 'run.json', record)
            print(json.dumps(dict(event='attempt_failed', family=family, error=str(e))), flush=True)
    write_json(base / 'unresolved.json', record)
    return record


def parameters(config, **kw):
    d = dict(mode='chase', bytes=1024, stride=8, offset=0, batch=config['batch'], seed=config['seed'], order='random')
    d.update(kw)
    return d


def run_suite(out, config, rows, smoke):
    context = out, config, rows, smoke
    rng = random.Random(config['seed'])
    if smoke:
        points = [('timer', parameters(config, mode='overhead')),
                  ('loop', parameters(config, mode='loop')),
                  ('capacity', parameters(config)),
                  ('capacity', parameters(config, bytes=65536, order='regular')),
                  ('line_size', parameters(config, mode='spatial', bytes=65536, stride=512, offset=56)),
                  ('associativity', parameters(config, bytes=4096*9, stride=4096)),
                  ('inclusion_policy', parameters(config, mode='reload', bytes=65536))]
        result = [point(f, p, context) for f, p in points]
        if any(r['status'] not in ('passed', 'noisy') for r in result):
            raise RuntimeError('Smoke test functional validation failed')
        write_json(out / 'smoke-passed.json', dict(time=now(), source_sha256=sha(ROOT / 'src/cache_bench.c'), points=len(result), purpose='functional validation; noise flags retained; full data have separate quality gates'))
        return
    # Every measured point, including controls and refinements, has >= 1e6 samples.
    overhead = point('timer', parameters(config, mode='overhead'), context)
    point('loop', parameters(config, mode='loop'), context)
    small = point('latency', parameters(config), context)
    if overhead.get('status') != 'passed' or small.get('status') != 'passed':
        raise RuntimeError('Timer calibration/control did not pass')
    ratio = overhead['statistics']['median'] / (small['statistics']['median'] * config['batch'])
    write_json(out / 'timer-validation.json', dict(overhead_fraction=ratio, maximum_fraction=.05,
               unit=small['measurement']['unit'], empirical_frequency_only=True,
               policy='Raw tick units; empirical TSC frequency is diagnostic, not used to invent core cycles'))
    calibrations = [dict(batch=config['batch'], overhead_fraction=ratio)]
    while ratio > .05 and config['batch'] < 8192:
        config = dict(config, batch=config['batch'] * 2)
        context = out, config, rows, smoke
        check = point('latency', parameters(config), context)
        if check.get('status') != 'passed':
            raise RuntimeError('Adaptive batch calibration remained noisy')
        ratio = overhead['statistics']['median'] / (check['statistics']['median'] * config['batch'])
        calibrations.append(dict(batch=config['batch'], overhead_fraction=ratio))
    write_json(out / 'batch-calibration.json', dict(trials=calibrations, chosen_batch=config['batch'], passed=ratio <= .05))
    if ratio > .05:
        raise RuntimeError('Timer overhead still exceeds 5%; no full sweep launched')
    sizes = []
    n = config['min_bytes']
    while n <= config['max_bytes']:
        sizes.append(n); n *= 2
    plans = [parameters(config, bytes=n, order=o) for n in sizes for o in ('random', 'regular')]
    rng.shuffle(plans)
    coarse = [point('capacity', p, context) for p in plans]
    random_rows = sorted([r for r in coarse if r.get('status') == 'passed' and r['parameters']['order'] == 'random'], key=lambda r:r['parameters']['bytes'])
    candidates = []
    for a,b in zip(random_rows, random_rows[1:]):
        if b['statistics']['median'] > 1.18 * a['statistics']['median']:
            candidates.append((a['parameters']['bytes'], b['parameters']['bytes']))
    write_json(out / 'candidate-boundaries.json', dict(rule='adjacent random medians increase >18%; candidates, not cache answers', intervals=candidates))
    dense = set()
    for lo, hi in candidates:
        for i in range(1,8):
            dense.add((lo + (hi-lo)*i//8)//8*8)
    plans = [parameters(config, bytes=n, order=o) for n in sorted(dense) for o in ('random','regular')]
    rng.shuffle(plans)
    for p in plans:
        point('capacity', p, context)
    # Spatial pairing: random 512-byte blocks, A at aligned base -> B at offset
    # -> next random A. Fixed allocation and node count while offset varies.
    first_transition = min([b for a,b in candidates] or [65536])
    footprints = sorted(set([min(config['max_bytes'], first_transition*8), min(config['max_bytes'], first_transition*32)]))
    offsets = sorted(set(list(range(8, 137, 8)) + [184,192,200,248,256,264]))
    plans = [parameters(config, mode='spatial', bytes=w, stride=512, offset=s) for w in footprints for s in offsets]
    rng.shuffle(plans)
    for p in plans:
        point('line_size', p, context)
    # Candidate low-bit congruence; physical indexing and TLB confounding remain explicit.
    strides = [4096, 16384, 65536, 262144]
    plans = [parameters(config, bytes=stride*n, stride=stride) for stride in strides for n in range(2,25)]
    rng.shuffle(plans)
    for p in plans:
        point('associativity', p, context)
    # Cross-level occupancy diagnostics AFTER hierarchy exploration. Same-core pressure
    # can directly evict upper levels: this is explicitly an uncertain policy test.
    for w in sorted(set([1024] + [b for a,b in candidates] + [config['max_bytes']])):
        for pressure in (32, 512, 2048):
            point('inclusion_policy', parameters(config, mode='reload', bytes=w, batch=pressure), context)
    # Standardized timing-residency workload: all hosts use identical working set.
    for w in (1024, 1048576, config['max_bytes']):
        point('software_metric', parameters(config, bytes=w, batch=1), context)
    write_json(out / 'collection-finished.json', dict(time=now(), note='Collection ended; final verification decides completeness.'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--smoke', action='store_true')
    args = ap.parse_args()
    config = json.loads((ROOT / 'config/phase1.json').read_text())
    host = platform.node().split('.')[0].lower()
    if host not in config['hosts']:
        raise SystemExit('Refusing benchmark outside the eight specified ECE lab hosts')
    out = ROOT / 'machines' / host / ('smoke' if args.smoke else 'full')
    out.mkdir(parents=True, exist_ok=True)
    lock = open(ROOT / 'worker.lock', 'w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if not args.smoke:
        if config['samples'] < 1000000:
            raise SystemExit('Phase-I full mode requires at least one million timed samples per configuration')
        gate = ROOT / 'machines' / host / 'smoke/smoke-passed.json'
        if not gate.exists() or json.loads(gate.read_text())['source_sha256'] != sha(ROOT / 'src/cache_bench.c'):
            raise SystemExit('Full run requires successful smoke tests for this exact source')
    rows, topo = topology()
    inherited_affinity = sorted(os.sched_getaffinity(0))
    affinity_expansion_error = None
    try:
        os.sched_setaffinity(0, {r['cpu'] for r in rows})
    except OSError as exc:
        affinity_expansion_error = str(exc)
    model = ''
    with open('/proc/cpuinfo') as f:
        for line in f:
            if re.match(r'^(model name|Hardware|Processor)\s*:', line):
                model = line.strip(); break
    if (out / 'environment.json').exists():
        prior = out / 'environment.json'
        archived = out / 'environment-history' / (sha(prior) + '.json')
        archived.parent.mkdir(exist_ok=True)
        if not archived.exists(): shutil.copy2(prior, archived)
    write_json(out / 'environment.json', dict(time=now(), host=host, uname=list(platform.uname()), cpu_model=model,
        topology=rows, topology_command=topo, page_size=os.sysconf('SC_PAGE_SIZE'), initial_affinity=inherited_affinity, available_affinity=sorted(os.sched_getaffinity(0)), affinity_expansion_error=affinity_expansion_error,
        environment={k:os.environ.get(k) for k in ('LANG','LC_ALL','PATH','CC','CFLAGS','OMP_NUM_THREADS')},
        locality='anonymous mmap and first touch after one-CPU binding; MADV_NOHUGEPAGE; no privileged changes',
        config=config, python=sys.version, source_sha256=sha(ROOT / 'src/cache_bench.c')))
    launch_env = out / 'environment-history' / (sha(out / 'environment.json') + '.json')
    launch_env.parent.mkdir(exist_ok=True)
    shutil.copy2(out / 'environment.json', launch_env)
    config['_environment_record'] = str(launch_env.relative_to(out))
    snapshot = out / 'provenance'
    snapshot.mkdir(exist_ok=True)
    manifest = {}
    for parent in ('src', 'scripts', 'config'):
        for path in sorted((ROOT / parent).glob('*')):
            if path.is_file():
                digest = sha(path)
                target = snapshot / (digest + '-' + path.name)
                if not target.exists():
                    shutil.copy2(path, target)
                manifest[str(path.relative_to(ROOT))] = dict(sha256=digest, snapshot=target.name)
    manifest_path = snapshot / ('manifest-' + str(time.time_ns()) + '.json')
    write_json(manifest_path, manifest)
    config['_provenance_manifest'] = str(manifest_path.relative_to(out))
    (out / 'build').mkdir(exist_ok=True)
    os.chdir(out / 'build')
    try:
        build(out / 'build')
        run_suite(out, config, rows, args.smoke)
    except Exception as e:
        write_json(out / ('failure-' + str(time.time_ns()) + '.json'), dict(time=now(), error=str(e), traceback=traceback.format_exc()))
        raise

if __name__ == '__main__':
    main()
