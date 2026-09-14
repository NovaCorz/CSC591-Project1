"""Standard-library-only raw-data statistics, provenance, and idle-core selection."""
import array
import collections
import datetime
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
    tmp.replace(path)


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def stats(values, divisor=1):
    counts = collections.Counter(values)
    if not counts:
        raise ValueError('empty samples')
    pairs = sorted(counts.items())
    n = sum(counts.values())
    def quantile(q):
        rank = q * (n - 1)
        lo, hi = math.floor(rank), math.ceil(rank)
        cumul, a, b = 0, None, None
        for value, count in pairs:
            cumul += count
            if a is None and cumul > lo:
                a = value
            if cumul > hi:
                b = value
                break
        return (a + (b - a) * (rank - lo)) / divisor
    mean = sum(v * c for v, c in pairs) / n
    variance = math.fsum(c * (v - mean) ** 2 for v, c in pairs) / max(1, n - 1)
    q1, q3 = quantile(.25), quantile(.75)
    low, high = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
    return dict(n=n, mean=mean / divisor, stddev=math.sqrt(variance) / divisor,
                median=quantile(.5), q1=q1, q3=q3, p05=quantile(.05), p95=quantile(.95),
                minimum=min(counts) / divisor, maximum=max(counts) / divisor,
                outliers=sum(c for v, c in pairs if v / divisor < low or v / divisor > high),
                outlier_rule='outside Q1 - 1.5 IQR or Q3 + 1.5 IQR; retained',
                zero_samples=counts.get(0, 0))


def read_raw(path, little_endian=True):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rb') as f:
        data = f.read()
    if len(data) % 8:
        raise ValueError('truncated uint64 raw file')
    a = array.array('Q')
    a.frombytes(data)
    if little_endian != (sys.byteorder == 'little'):
        a.byteswap()
    return a


def topology():
    cmd = ['lscpu', '-p=CPU,CORE,SOCKET,NODE']
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=True)
    rows = []
    for line in p.stdout.splitlines():
        if line and not line.startswith('#'):
            fields = line.split(',')
            rows.append(dict(zip(('cpu', 'core', 'socket', 'node'), [int(v) if v not in ('', '-') else -1 for v in fields])))
    return rows, dict(command=cmd, stdout=p.stdout, stderr=p.stderr)


def activity():
    out = {}
    with open('/proc/stat') as f:
        for line in f:
            parts = line.split()
            if parts and parts[0].startswith('cpu') and parts[0][3:].isdigit():
                # guest and guest_nice already included in user and nice.
                v = [int(x) for x in parts[1:9]]
                out[int(parts[0][3:])] = dict(total=sum(v), idle=v[3], iowait=v[4], fields=v)
    return out


def utilization(before, after):
    out = {}
    for c in before.keys() & after.keys():
        dt = after[c]['total'] - before[c]['total']
        di = after[c]['idle'] - before[c]['idle']
        out[c] = max(0.0, min(1.0, (dt - di) / dt)) if dt > 0 else 1.0
    return out


def choose_idle(rows, windows, allowed, threshold=.05, avoid=(), preferred=None):
    by_cpu = {r['cpu']: r for r in rows}
    candidates = []
    for c in sorted(allowed):
        if c not in by_cpu:
            continue
        row = by_cpu[c]
        siblings = [r['cpu'] for r in rows if (r['socket'], r['core']) == (row['socket'], row['core'])]
        loads = [window.get(s, 1.0) for window in windows for s in siblings]
        if loads and max(loads) <= threshold:
            preferred_row = by_cpu.get(preferred)
            same_domain = preferred_row is None or (row['socket'],row['node']) == (preferred_row['socket'],preferred_row['node'])
            candidates.append((bool(set(siblings).intersection(avoid)), not same_domain, preferred is not None and c != preferred, max(loads), sum(loads), c, siblings))
    if not candidates:
        raise RuntimeError('No core and complete SMT sibling group passed all idle windows')
    _, _, _, peak, _, c, siblings = min(candidates)
    return dict(by_cpu[c], siblings=siblings, peak_busy_fraction=peak)


def choose_idle_pair(rows, windows, allowed, threshold=.05, avoid=(), preferred=None):
    remaining=set(allowed)
    while remaining:
        first=choose_idle(rows,windows,remaining,threshold,avoid,preferred)
        helpers={r['cpu'] for r in rows if r['cpu'] in allowed and r['socket']==first['socket'] and r['core']!=first['core']}
        try:
            second=choose_idle(rows,windows,helpers,threshold,avoid,first['cpu'])
            return first,second
        except RuntimeError:
            remaining.difference_update(first['siblings'])
    raise RuntimeError('No pair of idle physical cores in one socket passed every idle window')


def select_idle(rows, config, avoid=()):
    raw, windows = [], []
    before = activity()
    for _ in range(config['idle_windows']):
        start = now()
        time.sleep(config['idle_seconds'])
        after = activity()
        window = utilization(before, after)
        raw.append(dict(start=start, end=now(), before=before, after=after, busy_fraction=window))
        windows.append(window)
        before = after
    try:
        selected = choose_idle(rows, windows, os.sched_getaffinity(0), config['idle_fraction'], avoid, config.get('_preferred_cpu'))
        error = None
    except RuntimeError as exc:
        selected, error = None, str(exc)
    return dict(selected=selected, error=error, evidence=raw, threshold=config['idle_fraction'],
                method='/proc/stat deltas; iowait counts as busy; all SMT siblings must pass every window')


def statistics_agree(actual, recorded):
    if set(actual) != set(recorded):
        return False
    for key in actual:
        if key == 'stddev':
            if not math.isclose(actual[key], recorded[key], rel_tol=1e-12, abs_tol=1e-12):
                return False
        elif actual[key] != recorded[key]:
            return False
    return True
