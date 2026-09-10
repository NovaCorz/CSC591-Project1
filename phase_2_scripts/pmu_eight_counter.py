#!/usr/bin/env python3
"""Phase II: run the three standardized eight-counter workloads
(L1-resident, LLC-sized randomized, larger-than-LLC) around the existing
Phase-I cache_capacity binary, wrapped by pmu_stat for hardware counters.

Matches the provenance style of scripts/capacity.py: records hostname,
CPU model, git commit, binary hashes, and the exact invocation for every
run, so results are traceable the same way the capacity data already is.

IMPORTANT -- read before running:
The three regime sizes below (--l1-kib, --llc-kib, --over-llc-kib) are
PLACEHOLDER footprints, not confirmed Phase-I boundaries. Phase I capacity
results are still being verified (uncertain measured values, per team
update). This script deliberately only touches:
  - event discovery / tool plumbing (independent of Phase-I values), and
  - the eight-counter *ranking* study (§8.4), which only needs footprints
    in the right general regime, not exact boundaries.
It does NOT attempt the §8.3 boundary-correlation step (showing a PMU
miss-count transition lines up with a specific timing transition) --
that step requires your partner's frozen Phase-I capacity numbers and
should be re-run once those are available. If the placeholder L1/LLC
sizes turn out to be wrong once Phase I is frozen, re-run this script
with corrected --l1-kib/--llc-kib/--over-llc-kib; it is cheap to redo
(three workloads, not the full sweep).

Usage example:
  python3 pmu_eight_counter.py \
      --binary ../main_code/common/cache_capacity \
      --pmu-stat ../main_code/pmu/pmu_stat \
      --cpu 2 --spacing 8 --samples 1000000 --steps 4096 --seed 592 \
      --l1-kib 32 --llc-kib 8192 --over-llc-kib 65536 \
      --events cycles,instructions,L1D-read-access,L1D-read-miss,LL-read-access,LL-read-miss,dTLB-read-miss,cache-misses \
      --out ../data_raw/sunbird/pmu/eight_counter-$(date +%Y%m%d)
"""
import argparse
import csv
import datetime
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def command(args):
    result = subprocess.run(args, text=True, capture_output=True)
    return result.stdout.strip() if result.returncode == 0 else result.stderr.strip()


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse_counter_line(line):
    """Parse pmu_stat's trailing CSV line: name=value,name=value,...  """
    out = {}
    for field in line.strip().rstrip(",").split(","):
        if "=" not in field:
            continue
        k, v = field.split("=", 1)
        out[k] = v
    return out


def run_one(binary, pmu_stat, events, cpu, bytes_, spacing, samples, steps,
            seed, mode, out_bin):
    invocation = [
        "taskset", "-c", str(cpu), str(binary),
        str(bytes_), str(spacing), str(samples), str(steps), str(seed),
        mode, str(out_bin),
    ]
    full_cmd = [str(pmu_stat), "-e", events, "--"] + invocation
    result = subprocess.run(full_cmd, text=True, capture_output=True)
    stdout_lines = [ln for ln in result.stdout.splitlines() if ln.strip()]

    bench_meta = None
    counters = {}
    if stdout_lines:
        # cache_capacity prints one JSON line; pmu_stat appends one CSV line.
        try:
            bench_meta = json.loads(stdout_lines[0])
        except json.JSONDecodeError:
            bench_meta = {"raw_stdout_line0": stdout_lines[0]}
        if len(stdout_lines) > 1:
            counters = parse_counter_line(stdout_lines[-1])
        else:
            counters = parse_counter_line(stdout_lines[0])

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
    ap.add_argument("--binary", required=True, help="path to cache_capacity")
    ap.add_argument("--pmu-stat", required=True, help="path to pmu_stat")
    ap.add_argument("--cpu", type=int, required=True)
    ap.add_argument("--spacing", type=int, default=8)
    ap.add_argument("--samples", type=int, default=1_000_000)
    ap.add_argument("--steps", type=int, default=4096)
    ap.add_argument("--seed", type=int, default=592)
    ap.add_argument("--l1-kib", type=float, required=True,
                     help="PLACEHOLDER L1-resident footprint (KiB)")
    ap.add_argument("--llc-kib", type=float, required=True,
                     help="PLACEHOLDER LLC-sized footprint (KiB)")
    ap.add_argument("--over-llc-kib", type=float, required=True,
                     help="PLACEHOLDER >LLC footprint (KiB)")
    ap.add_argument("--events", required=True,
                     help="comma-separated event list, max 8 recommended "
                          "(more may multiplex -- check pmu_stat stderr)")
    ap.add_argument("--mode", default="random", choices=["random", "sequential"],
                     help="traversal mode for all three regimes (default: random, "
                          "the prefetcher-resistant standard used in Phase I)")
    ap.add_argument("--out", required=True, help="output directory (created fresh)")
    ap.add_argument("--notes", default="", help="free-text notes for environment.json")
    args = ap.parse_args()

    if args.samples < 1_000_000:
        print("WARNING: fewer than 1,000,000 samples -- not final evidence, "
              "pilot only.", file=sys.stderr)

    binary = Path(args.binary).resolve()
    pmu_stat = Path(args.pmu_stat).resolve()
    if not binary.is_file():
        sys.exit(f"cache_capacity binary not found at {binary}")
    if not pmu_stat.is_file():
        sys.exit(f"pmu_stat binary not found at {pmu_stat}")

    dest = Path(args.out)
    dest.mkdir(parents=True, exist_ok=False)

    cpu_model = next((line.strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                       if line.startswith(("model name", "Hardware", "Processor"))),
                      "unavailable")

    environment = {
        "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "hostname": command(["hostname"]),
        "kernel": command(["uname", "-a"]),
        "cpu_model": cpu_model,
        "topology": command(["lscpu", "-e=CPU,CORE,SOCKET,NODE"]),
        "git_commit": command(["git", "rev-parse", "HEAD"]),
        "git_status": command(["git", "status", "--short"]),
        "binary_sha256": sha256_of(binary),
        "pmu_stat_sha256": sha256_of(pmu_stat),
        "arguments": vars(args),
        "command": sys.argv,
        "PLACEHOLDER_WARNING": (
            "l1_kib/llc_kib/over_llc_kib are provisional regime sizes, not "
            "confirmed Phase-I boundaries. Re-run once Phase I is frozen "
            "if these estimates change materially."
        ),
        "notes": args.notes,
    }
    (dest / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")

    regimes = [
        ("l1_resident", args.l1_kib),
        ("llc_sized", args.llc_kib),
        ("larger_than_llc", args.over_llc_kib),
    ]

    summary_rows = []
    for regime_name, size_kib in regimes:
        bytes_ = int(size_kib * 1024)
        if bytes_ % args.spacing or bytes_ // args.spacing < 2:
            sys.exit(f"{regime_name}: {size_kib} KiB not divisible by spacing "
                      f"{args.spacing} with >=2 nodes; adjust size or spacing.")
        stem = dest / regime_name
        out_bin = stem.with_suffix(".bin")
        print(f"[{regime_name:16s}] {size_kib:>10.1f} KiB, mode={args.mode}, "
              f"{args.samples} batches x {args.steps} loads", flush=True)

        result = run_one(binary, pmu_stat, args.events, args.cpu, bytes_,
                          args.spacing, args.samples, args.steps, args.seed,
                          args.mode, out_bin)

        (dest / f"{regime_name}.json").write_text(
            json.dumps({"regime": regime_name, "size_kib": size_kib,
                        **result}, indent=2) + "\n")
        (dest / f"{regime_name}.pmu_stat.stderr").write_text(result["pmu_stat_stderr"])

        if result["returncode"] != 0:
            print(f"  WARNING: nonzero exit ({result['returncode']}); "
                  f"see {regime_name}.pmu_stat.stderr", file=sys.stderr)

        row = {"regime": regime_name, "size_kib": size_kib, "mode": args.mode,
               "samples": args.samples, "steps": args.steps,
               **result["counters"]}
        summary_rows.append(row)

        # remove the raw .bin -- this driver only needs pmu_stat's counters;
        # your existing capacity.py pipeline still owns the real timing sweep.
        if out_bin.exists():
            out_bin.unlink()

    if summary_rows:
        fieldnames = sorted({k for row in summary_rows for k in row})
        # keep regime/size/mode first for readability
        ordered = ["regime", "size_kib", "mode", "samples", "steps"] + [
            f for f in fieldnames
            if f not in ("regime", "size_kib", "mode", "samples", "steps")]
        with open(dest / "summary.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=ordered)
            writer.writeheader()
            writer.writerows(summary_rows)

    print(f"\nDone. Results in {dest}/")
    print("Check each *.pmu_stat.stderr for multiplexing warnings "
          "(time_running < time_enabled).")


if __name__ == "__main__":
    main()