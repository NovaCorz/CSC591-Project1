#!/usr/bin/env python3
"""Phase II line-size PMU verification: dense PMU sampling across a sweep of
candidate byte strides, to test whether a hardware miss-rate transition
coincides with the frozen Phase-I line-size candidate (64 B on all eight
machines, per data_processed/all_machines/inferred-cache-table.csv).

Uses cache_bench's native "spatial" mode directly (main_code/common/phase1/
src/cache_bench.c) -- no address-list machinery needed, unlike associativity.
In spatial mode, each chase node performs two dereferences: one at the node's
base address, one at base+OFFSET. If OFFSET falls within the same physical
cache line as the base (STRIDE >= true line size keeps them separated cleanly;
STRIDE close to or below the line size means neighboring nodes' base and
offset positions can share lines), the second dereference is fast; once
STRIDE crosses the true line-size boundary the spatial-locality benefit
should disappear and miss behavior should shift.

CLI (confirmed from source): cache_bench MODE BYTES STRIDE OFFSET SAMPLES
BATCH SEED CPU ORDER RAW

IMPORTANT -- read before trusting results:
This independently re-tests the line-size boundary using PMU counters, but
it is NOT a byte-for-byte replication of Phase I's own raw spatial_residency
run parameters (those raw run.json manifests live in the external archive,
not in this git checkout -- see data_processed/<host>/final-inference.json's
"spatial" section for the curated summary). The BYTES footprint below
(default 262144, i.e. 256 KiB) matches the footprint Phase I itself used for
spatial-residency testing on machines, per that curated summary, but the
specific STRIDE candidates swept here are independently chosen to bracket
the already-established 64 B line size, not reconstructed from Phase I's
exact historical sweep.

Usage:
  python3 stride_correlation.py \
      --host ookay --binary ../common/phase1/src/cache_bench \
      --pmu-stat ../pmu/pmu_stat --cpu 3 \
      --host-config ../common/phase1/config/followup-plan.json \
      --events cycles,instructions,L1D-read-access,L1D-read-miss \
      --out ../../data_raw/ookay/pmu/stride_correlation
"""
import argparse
import csv
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def command(args):
    result = subprocess.run(args, text=True, capture_output=True)
    return result.stdout.strip() if result.returncode == 0 else result.stderr.strip()


def parse_counter_line(line):
    out = {}
    for field in line.strip().rstrip(",").split(","):
        if "=" not in field:
            continue
        k, v = field.split("=", 1)
        out[k] = v
    return out


def load_host_config(path, host):
    if not path:
        return {}
    data = json.loads(Path(path).read_text())
    return data.get("hosts", {}).get(host, {})


def default_stride_candidates():
    # Dense around the established 64 B line size, sparser further out, per
    # the handout's "repeat densely around candidate powers of two such as
    # 32, 64, 128, and 256 bytes" guidance. All values satisfy cache_bench's
    # spatial-mode constraint stride >= 16 (since offset=8 requires
    # offset + 8 <= stride).
    return [16, 24, 32, 40, 48, 56, 64, 72, 80, 96, 112, 128, 160, 192, 256]


def run_one_point(binary, pmu_stat, events, cpu, bytes_, stride, offset,
                   samples, batch, seed, order, out_bin):
    invocation = [str(binary), "spatial", str(bytes_), str(stride),
                  str(offset), str(samples), str(batch), str(seed),
                  str(cpu), order, str(out_bin)]
    full_cmd = [str(pmu_stat), "-e", events, "--"] + invocation
    result = subprocess.run(full_cmd, text=True, capture_output=True)
    stdout_lines = [ln for ln in result.stdout.splitlines() if ln.strip()]

    bench_meta = None
    counters = {}
    if stdout_lines:
        try:
            bench_meta = json.loads(stdout_lines[0])
        except json.JSONDecodeError:
            bench_meta = {"raw_stdout_line0": stdout_lines[0]}
        counters = parse_counter_line(stdout_lines[-1])

    return {
        "invocation": invocation,
        "returncode": result.returncode,
        "bench_metadata": bench_meta,
        "counters": counters,
        "pmu_stat_stderr": result.stderr,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", required=True)
    ap.add_argument("--host-config",
                     help="e.g. main_code/common/phase1/config/followup-plan.json "
                          "-- auto-fills --batch/--seed if present for this host")
    ap.add_argument("--binary", required=True, help="path to cache_bench")
    ap.add_argument("--pmu-stat", required=True, help="path to pmu_stat")
    ap.add_argument("--cpu", type=int, required=True)
    ap.add_argument("--bytes", type=int, default=262144,
                     help="fixed footprint (default 256 KiB, matching Phase-I's "
                          "own spatial-residency footprint per final-inference.json)")
    ap.add_argument("--offset", type=int, default=8,
                     help="fixed spatial offset within each node (default 8, "
                          "the minimum valid value)")
    ap.add_argument("--strides", type=int, nargs="+", default=None,
                     help="candidate strides to sweep (default: dense set "
                          "bracketing 64 B, see default_stride_candidates())")
    ap.add_argument("--batch", type=int, default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--samples", type=int, default=1_000_000)
    ap.add_argument("--order", default="random", choices=["random", "regular"])
    ap.add_argument("--events", required=True)
    ap.add_argument("--keep-raw", action="store_true")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    host_cfg = load_host_config(args.host_config, args.host)
    batch = args.batch or host_cfg.get("batch", 128)
    seed = args.seed or host_cfg.get("seed", 5922026)
    strides = args.strides or default_stride_candidates()

    binary = Path(args.binary).resolve()
    pmu_stat = Path(args.pmu_stat).resolve()
    if not binary.is_file():
        sys.exit(f"cache_bench binary not found at {binary}")
    if not pmu_stat.is_file():
        sys.exit(f"pmu_stat binary not found at {pmu_stat}")

    for s in strides:
        if s < args.offset + 8:
            sys.exit(f"stride {s} invalid: must be >= offset+8 ({args.offset + 8}) "
                      f"for spatial mode")

    dest = Path(args.out)
    dest.mkdir(parents=True, exist_ok=False)

    environment = {
        "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "hostname": command(["hostname"]),
        "target_host": args.host,
        "bytes": args.bytes, "offset": args.offset, "batch": batch,
        "seed": seed, "samples": args.samples, "order": args.order,
        "cpu": args.cpu, "strides_swept": strides,
        "git_commit": command(["git", "rev-parse", "HEAD"]),
        "binary_sha256": sha256_of(binary),
        "pmu_stat_sha256": sha256_of(pmu_stat),
        "command": sys.argv,
        "METHODOLOGY_NOTE": (
            "Independent PMU re-test of the line-size boundary using "
            "cache_bench's native spatial mode. NOT a replication of "
            "Phase-I's exact historical stride candidates (those raw run "
            "manifests are in the external archive, not this checkout). "
            "The established Phase-I line-size candidate is 64 B on all "
            "eight machines per inferred-cache-table.csv."
        ),
    }
    (dest / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")

    print(f"[{args.host}] line-size sweep: bytes={args.bytes} offset={args.offset} "
          f"batch={batch} seed={seed} samples={args.samples}")
    print(f"Sweeping {len(strides)} strides: {strides}")

    summary_rows = []
    for i, stride in enumerate(strides):
        stem = dest / f"stride_{i:02d}_{stride}B"
        out_bin = stem.with_suffix(".bin")
        print(f"  [{i+1:2d}/{len(strides)}] stride={stride:>4d} B", flush=True)

        result = run_one_point(binary, pmu_stat, args.events, args.cpu,
                                args.bytes, stride, args.offset, args.samples,
                                batch, seed, args.order, out_bin)

        (stem.with_suffix(".json")).write_text(
            json.dumps({"stride": stride, **result}, indent=2) + "\n")
        (stem.with_suffix(".pmu_stat.stderr")).write_text(result["pmu_stat_stderr"])

        if result["returncode"] != 0:
            print(f"    WARNING: nonzero exit ({result['returncode']})",
                  file=sys.stderr)

        row = {"stride_bytes": stride, **result["counters"]}
        summary_rows.append(row)

        if out_bin.exists() and not args.keep_raw:
            out_bin.unlink()

    if summary_rows:
        fieldnames = sorted({k for row in summary_rows for k in row})
        ordered = ["stride_bytes"] + [f for f in fieldnames if f != "stride_bytes"]
        with open(dest / "summary.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=ordered)
            writer.writeheader()
            writer.writerows(summary_rows)

    print(f"\nDone. {len(summary_rows)} points written to {dest}/summary.csv")
    print("Plot L1D-read-miss/access rate against stride_bytes; look for a "
          "transition near 64 B (the frozen Phase-I line-size candidate).")


if __name__ == "__main__":
    main()