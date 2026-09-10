#!/usr/bin/env python3
"""Phase II §8.4: run the three standardized eight-counter workloads
(L1-resident, LLC-sized randomized, larger-than-LLC) through the REAL frozen
kernel, main_code/common/phase1/src/cache_bench, wrapped by pmu_stat for
hardware counters.

FIXED from an earlier version: this driver previously built invocations
using the old, now-deleted cache_capacity CLI (BYTES SPACING SAMPLES STEPS
SEED MODE RAW) wrapped in taskset. That is wrong for the real kernel and
causes cache_bench to print its usage message and exit(2) immediately,
producing all-zero counters and time_running=0 -- the workload never ran.
This version uses cache_bench's actual CLI and does NOT wrap with taskset,
since cache_bench pins itself internally via the CPU argument:

    cache_bench MODE BYTES STRIDE OFFSET SAMPLES BATCH SEED CPU ORDER RAW

Event-count caution: requesting too many simultaneous hardware+cache events
in one perf group can exceed a core's physical counter count and cause a
hard EINVAL failure on the later events (not just soft multiplexing). Most
client CPUs have ~4 general-purpose counters per core. By default this
driver splits your event list into batches of --events-per-run (default 4)
and issues one pmu_stat invocation per batch per regime, then merges the
results -- so an 8-event request becomes 2 runs of 4 automatically.

IMPORTANT -- read before running:
The three regime sizes below (--l1-kib, --llc-kib, --over-llc-kib) should
come from resolve_phase1_boundaries.py now that Phase I is frozen -- they
are real bracket-derived values, not guesses. See PHASE2_GUIDE.md.

Usage example:
  python3 pmu_eight_counter.py \
      --binary main_code/common/phase1/src/cache_bench \
      --pmu-stat main_code/pmu/pmu_stat \
      --cpu 8 --stride 8 --samples 1000000 --batch 512 --seed 5922026 \
      --l1-kib 34.0 --llc-kib 20480.0 --over-llc-kib 131072.0 \
      --events cycles,instructions,L1D-read-access,L1D-read-miss,LL-read-access,LL-read-miss,DTLB-read-miss,cache-misses \
      --events-per-run 4 \
      --out data_raw/sunbird/pmu/eight_counter-$(date +%Y%m%d)
"""
import argparse
import csv
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def command(args):
    result = subprocess.run(args, text=True, capture_output=True)
    return result.stdout.strip() if result.returncode == 0 else result.stderr.strip()


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse_counter_line(line):
    out = {}
    for field in line.strip().rstrip(",").split(","):
        if "=" not in field:
            continue
        k, v = field.split("=", 1)
        out[k] = v
    return out


def chunk(seq, size):
    return [seq[i:i + size] for i in range(0, len(seq), size)]


def run_one(binary, pmu_stat, events_csv, cpu, mode, bytes_, stride, samples,
            batch, seed, order, out_bin):
    """One cache_bench invocation, wrapped by pmu_stat, for one event batch."""
    invocation = [str(binary), mode, str(bytes_), str(stride), "0",
                  str(samples), str(batch), str(seed), str(cpu), order,
                  str(out_bin)]
    full_cmd = [str(pmu_stat), "-e", events_csv, "--"] + invocation
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
    ap.add_argument("--binary", required=True, help="path to cache_bench")
    ap.add_argument("--pmu-stat", required=True, help="path to pmu_stat")
    ap.add_argument("--cpu", type=int, required=True)
    ap.add_argument("--stride", type=int, default=8)
    ap.add_argument("--samples", type=int, default=1_000_000)
    ap.add_argument("--batch", type=int, default=512)
    ap.add_argument("--seed", type=int, default=5922026)
    ap.add_argument("--mode", default="chase",
                     choices=["chase", "spatial", "reload", "overhead", "loop"])
    ap.add_argument("--order", default="random", choices=["random", "regular"])
    ap.add_argument("--l1-kib", type=float, required=True)
    ap.add_argument("--llc-kib", type=float, required=True)
    ap.add_argument("--over-llc-kib", type=float, required=True)
    ap.add_argument("--events", required=True,
                     help="comma-separated event list, any length -- "
                          "automatically split into --events-per-run batches")
    ap.add_argument("--events-per-run", type=int, default=4,
                     help="max simultaneous events per pmu_stat group "
                          "(default 4 -- most client CPUs have ~4 general-"
                          "purpose counters per core; raise cautiously, "
                          "lower if you see EINVAL failures in stderr)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--notes", default="")
    args = ap.parse_args()

    if args.samples < 1_000_000:
        print("WARNING: fewer than 1,000,000 samples -- pilot only.",
              file=sys.stderr)

    binary = Path(args.binary).resolve()
    pmu_stat = Path(args.pmu_stat).resolve()
    if not binary.is_file():
        sys.exit(f"cache_bench binary not found at {binary}")
    if not pmu_stat.is_file():
        sys.exit(f"pmu_stat binary not found at {pmu_stat}")

    dest = Path(args.out)
    dest.mkdir(parents=True, exist_ok=False)

    cpu_model = next((line.strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                       if line.startswith(("model name", "Hardware", "Processor"))),
                      "unavailable")

    event_list = [e.strip() for e in args.events.split(",") if e.strip()]
    event_batches = chunk(event_list, args.events_per_run)

    environment = {
        "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "hostname": command(["hostname"]),
        "kernel": command(["uname", "-a"]),
        "cpu_model": cpu_model,
        "git_commit": command(["git", "rev-parse", "HEAD"]),
        "git_status": command(["git", "status", "--short"]),
        "binary_sha256": sha256_of(binary),
        "pmu_stat_sha256": sha256_of(pmu_stat),
        "arguments": vars(args),
        "event_batches": event_batches,
        "command": sys.argv,
        "PLACEHOLDER_WARNING": (
            "l1_kib/llc_kib/over_llc_kib should come from "
            "resolve_phase1_boundaries.py now that Phase I is frozen -- "
            "confirm they are not left over from before the freeze."
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
        if bytes_ < args.stride * 2:
            sys.exit(f"{regime_name}: {size_kib} KiB too small for stride "
                      f"{args.stride}; adjust size or stride.")

        merged_counters = {}
        any_failure = False
        for batch_idx, event_batch in enumerate(event_batches):
            events_csv = ",".join(event_batch)
            stem = dest / f"{regime_name}_batch{batch_idx}"
            out_bin = stem.with_suffix(".bin")
            print(f"[{regime_name:16s} batch {batch_idx}] {size_kib:>10.1f} KiB "
                  f"events={events_csv}", flush=True)

            result = run_one(binary, pmu_stat, events_csv, args.cpu, args.mode,
                              bytes_, args.stride, args.samples, args.batch,
                              args.seed, args.order, out_bin)

            (dest / f"{regime_name}_batch{batch_idx}.json").write_text(
                json.dumps({"regime": regime_name, "size_kib": size_kib,
                            "event_batch": event_batch, **result}, indent=2) + "\n")
            (dest / f"{regime_name}_batch{batch_idx}.pmu_stat.stderr").write_text(
                result["pmu_stat_stderr"])

            if result["returncode"] != 0:
                print(f"  WARNING: nonzero exit ({result['returncode']}) for "
                      f"batch {batch_idx} -- see {regime_name}_batch{batch_idx}"
                      f".pmu_stat.stderr. Counters from this batch are invalid.",
                      file=sys.stderr)
                any_failure = True

            # merge this batch's counters into the regime's full row,
            # skipping counters if the whole batch's child process failed
            if result["returncode"] == 0:
                merged_counters.update(result["counters"])

            if out_bin.exists():
                out_bin.unlink()

        row = {"regime": regime_name, "size_kib": size_kib, "mode": args.mode,
               "order": args.order, "samples": args.samples,
               "batch_size": args.batch,
               "any_batch_failed": any_failure, **merged_counters}
        summary_rows.append(row)

    if summary_rows:
        fieldnames = sorted({k for row in summary_rows for k in row})
        ordered = ["regime", "size_kib", "mode", "order", "samples",
                   "batch_size", "any_batch_failed"] + [
            f for f in fieldnames
            if f not in ("regime", "size_kib", "mode", "order", "samples",
                         "batch_size", "any_batch_failed")]
        with open(dest / "summary.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=ordered)
            writer.writeheader()
            writer.writerows(summary_rows)

    print(f"\nDone. Results in {dest}/")
    print("Check 'any_batch_failed' in summary.csv and each "
          "*.pmu_stat.stderr for EINVAL/multiplexing warnings before "
          "trusting a row.")


if __name__ == "__main__":
    main()