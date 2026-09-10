#!/usr/bin/env python3
"""Phase II, Step 4: dense PMU sampling across a real frozen Phase-I capacity
bracket, to show a PMU miss-count transition coincides with (or refines) the
Phase-I timing bracket -- the actual evidence required by handout Sec.8.3.2:
"show where an inferred L1 capacity boundary coincides with increasing L1
misses, or where an LLC boundary coincides with increasing last-level misses."

Wraps the REAL frozen kernel, main_code/common/phase1/src/cache_bench.c, not
a placeholder benchmark. Its exact CLI (verified from source):

    cache_bench MODE BYTES STRIDE OFFSET SAMPLES BATCH SEED CPU ORDER RAW

  MODE  = chase | spatial | reload | overhead | loop   (use "chase" here)
  ORDER = random | regular                              (use "random" here)

Reuses the SAME per-host STRIDE/BATCH/SEED/SAMPLES that produced the frozen
Phase-I curve wherever possible (see --host-config), so this correlation run
is not a new experiment with new confounds -- it is the same sweep with PMU
counters attached via pmu_stat.

IMPORTANT per PHASE1_HANDOFF.md:
- Capacity/associativity values are CONDITIONAL BRACKETS, not point values.
  This script sweeps densely across the whole bracket (plus margin on both
  sides), not just a single boundary value.
- Do NOT use this script to "confirm" hit latency or inclusion/exclusion --
  the handoff states those remain unresolved in Phase I; this driver only
  targets the capacity/associativity boundary-correlation requirement.

Usage:
  # auto-fill stride/batch/seed for a host from the frozen config file:
  python3 boundary_correlation.py \
      --host sunbird --level l1 \
      --boundaries-json phase1_boundaries.json \
      --host-config main_code/common/phase1/config/followup-plan.json \
      --binary main_code/common/phase1/src/cache_bench \
      --pmu-stat main_code/pmu/pmu_stat \
      --cpu 2 \
      --events cycles,instructions,L1D-read-access,L1D-read-miss,LL-read-access,LL-read-miss,dTLB-read-miss,cache-misses \
      --out data_raw/sunbird/pmu/boundary_correlation-$(date +%Y%m%d)_l1

  # or supply stride/batch/seed/samples explicitly (no --host-config needed):
  python3 boundary_correlation.py \
      --host sunbird --level l1 --boundaries-json phase1_boundaries.json \
      --binary ... --pmu-stat ... --cpu 2 \
      --stride 8 --batch 512 --seed 5922026 --samples 1000000 \
      --events ... --out ...
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
    """Pull batch/l1 bracket/etc. from the frozen followup-plan.json-style
    config, if given. Returns {} if the host isn't present -- caller falls
    back to explicit CLI args."""
    if not path:
        return {}
    data = json.loads(Path(path).read_text())
    hosts = data.get("hosts", {})
    return hosts.get(host, {})


def log_spaced_points(low, high, n, margin_frac):
    """n points log-spaced from low*(1-margin_frac) to high*(1+margin_frac),
    always including the exact low/high bracket edges."""
    import math
    ext_low = max(low * (1 - margin_frac), 1.0)
    ext_high = high * (1 + margin_frac)
    log_lo, log_hi = math.log(ext_low), math.log(ext_high)
    pts = {round(math.exp(log_lo + i * (log_hi - log_lo) / (n - 1)))
           for i in range(n)}
    pts.add(round(low))
    pts.add(round(high))
    return sorted(pts)

def run_one_point(binary, pmu_stat, events, events_per_run, cpu, bytes_,
                  stride, samples, batch, seed, mode, order, out_bin):

    invocation = [
        str(binary), mode, str(bytes_), str(stride), "0",
        str(samples), str(batch), str(seed), str(cpu), order,
        str(out_bin)
    ]

    event_list = [e.strip() for e in events.split(",") if e.strip()]

    event_batches = [
        event_list[i:i + events_per_run]
        for i in range(0, len(event_list), events_per_run)
    ]

    combined_counters = {}
    batch_results = []
    all_stderr = []
    overall_returncode = 0

    for batch_idx, event_batch in enumerate(event_batches):

        batch_events = ",".join(event_batch)

        batch_cmd = [
            str(pmu_stat),
            "-e",
            batch_events,
            "--"
        ] + invocation

        print(
            f"    PMU batch {batch_idx}: {batch_events}",
            flush=True
        )

        result = subprocess.run(
            batch_cmd,
            text=True,
            capture_output=True
        )

        stdout_lines = [
            ln for ln in result.stdout.splitlines()
            if ln.strip()
        ]

        bench_meta = None
        counters = {}

        if stdout_lines:
            try:
                bench_meta = json.loads(stdout_lines[0])
            except json.JSONDecodeError:
                bench_meta = {
                    "raw_stdout_line0": stdout_lines[0]
                }

            counters = parse_counter_line(stdout_lines[-1])

        batch_time_enabled = counters.get("time_enabled_ns")
        batch_time_running = counters.get("time_running_ns")

        if result.returncode != 0:
            overall_returncode = result.returncode

        if (
            batch_time_enabled is not None
            and batch_time_running is not None
        ):
            try:
                enabled = int(batch_time_enabled)
                running = int(batch_time_running)

                if enabled > 0 and running == 0:
                    overall_returncode = 1
                    print(
                        f"    WARNING: batch {batch_idx} has "
                        f"time_running=0; counters are invalid.",
                        file=sys.stderr,
                        flush=True
                    )

            except ValueError:
                pass

        combined_counters.update({
            k: v
            for k, v in counters.items()
            if k not in ("time_enabled_ns", "time_running_ns")
        })

        batch_results.append({
            "event_batch": event_batch,
            "returncode": result.returncode,
            "bench_metadata": bench_meta,
            "counters": counters,
            "pmu_stat_stderr": result.stderr
        })

        all_stderr.append(
            f"--- batch {batch_idx}: {batch_events} ---\n"
            f"{result.stderr}"
        )

    return {
        "invocation": invocation,
        "returncode": overall_returncode,
        "bench_metadata": (
            batch_results[0]["bench_metadata"]
            if batch_results else None
        ),
        "counters": combined_counters,
        "batches": batch_results,
        "pmu_stat_stderr": "\n".join(all_stderr)
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", required=True)
    ap.add_argument("--level", required=True, choices=["l1", "l2", "llc"])
    ap.add_argument("--boundaries-json", required=True,
                     help="output of resolve_phase1_boundaries.py")
    ap.add_argument("--host-config",
                     help="e.g. main_code/common/phase1/config/followup-plan.json "
                          "-- auto-fills --stride/--batch/--seed if present for "
                          "this host; explicit CLI values below always win")
    ap.add_argument("--binary", required=True, help="path to cache_bench")
    ap.add_argument("--pmu-stat", required=True, help="path to pmu_stat")
    ap.add_argument("--cpu", type=int, required=True,
                     help="logical CPU pin -- use the SAME core Phase I used "
                          "for this host if possible (check final-affinity-"
                          "summary.csv)")
    ap.add_argument("--stride", type=int, default=None,
                     help="default: from --host-config, else 8 (bare pointer)")
    ap.add_argument("--batch", type=int, default=None,
                     help="default: from --host-config, else 128")
    ap.add_argument("--seed", type=int, default=None,
                     help="default: from --host-config, else the Phase-I "
                          "global default seed 5922026")
    ap.add_argument("--samples", type=int, default=1_000_000)
    ap.add_argument("--mode", default="chase", choices=["chase", "spatial", "reload", "overhead", "loop"])
    ap.add_argument("--order", default="random", choices=["random", "regular"])
    ap.add_argument("--n-points", type=int, default=13,
                     help="log-spaced sweep points across the bracket + margin")
    ap.add_argument("--margin-frac", type=float, default=0.5,
                     help="extend the swept range this fraction below/above "
                          "the bracket on each side (0.5 = ±50%%)")
    ap.add_argument("--events", required=True)
    ap.add_argument("--events-per-run", type=int, default=2,
                help="number of PMU events to measure together per run "
                     "(default: 2)")
    ap.add_argument("--keep-raw", action="store_true",
                     help="keep each point's raw .bin timing samples instead "
                          "of deleting them after the counter is read")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    boundaries = json.loads(Path(args.boundaries_json).read_text())
    if args.host not in boundaries:
        sys.exit(f"host '{args.host}' not found in {args.boundaries_json}")
    level_data = boundaries[args.host].get(args.level)
    if not level_data or not level_data.get("capacity_interval_bytes"):
        sys.exit(f"no capacity_interval_bytes for {args.host}/{args.level} -- "
                  f"check {args.boundaries_json}")
    low, high = level_data["capacity_interval_bytes"]

    host_cfg = load_host_config(args.host_config, args.host)
    stride = args.stride or host_cfg.get("stride", 8)
    batch = args.batch or host_cfg.get("batch", 128)
    seed = args.seed or host_cfg.get("seed", 5922026)

    binary = Path(args.binary).resolve()
    pmu_stat = Path(args.pmu_stat).resolve()
    if not binary.is_file():
        sys.exit(f"cache_bench binary not found at {binary}")
    if not pmu_stat.is_file():
        sys.exit(f"pmu_stat binary not found at {pmu_stat}")

    dest = Path(args.out)
    dest.mkdir(parents=True, exist_ok=False)

    environment = {
        "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "hostname": command(["hostname"]),
        "target_host": args.host,
        "target_level": args.level,
        "bracket_bytes": [low, high],
        "bracket_status": level_data.get("status"),
        "stride": stride, "batch": batch, "seed": seed,
        "samples": args.samples, "mode": args.mode, "order": args.order,
        "cpu": args.cpu,
        "git_commit": command(["git", "rev-parse", "HEAD"]),
        "binary_sha256": sha256_of(binary),
        "pmu_stat_sha256": sha256_of(pmu_stat),
        "command": sys.argv,
        "PHASE1_CAVEAT": (
            "This bracket is a conditional Phase-I candidate, not a confirmed "
            "boundary. Hit latency and inclusion/exclusion remain unresolved "
            "per PHASE1_HANDOFF.md and are NOT validated by this script."
        ),
    }
    (dest / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")

    points = log_spaced_points(low, high, args.n_points, args.margin_frac)
    print(f"[{args.host}/{args.level}] bracket=[{low},{high}] bytes  "
          f"stride={stride} batch={batch} seed={seed} samples={args.samples}")
    print(f"Sweeping {len(points)} points: {points}")

    summary_rows = []
    for i, bytes_ in enumerate(points):
        if bytes_ < stride * 2:
            print(f"  skip {bytes_} B -- below stride*2 minimum", file=sys.stderr)
            continue
        stem = dest / f"point_{i:02d}_{bytes_}B"
        out_bin = stem.with_suffix(".bin")
        in_bracket = low <= bytes_ <= high
        print(f"  [{i+1:2d}/{len(points)}] {bytes_:>10d} B "
              f"({'IN BRACKET' if in_bracket else 'margin'})", flush=True)

        result = run_one_point(
                binary,
                pmu_stat,
                args.events,
                args.events_per_run,
                args.cpu,
                bytes_,
                stride,
                args.samples,
                batch,
                seed,
                args.mode,
                args.order,
                out_bin
                )

        (stem.with_suffix(".json")).write_text(
            json.dumps({"bytes": bytes_, "in_bracket": in_bracket, **result},
                       indent=2) + "\n")
        (stem.with_suffix(".pmu_stat.stderr")).write_text(result["pmu_stat_stderr"])

        if result["returncode"] != 0:
            print(f"    WARNING: nonzero exit ({result['returncode']})",
                  file=sys.stderr)

        row = {"bytes": bytes_, "kib": round(bytes_ / 1024, 3),
               "in_bracket": in_bracket, **result["counters"]}
        summary_rows.append(row)

        if out_bin.exists() and not args.keep_raw:
            out_bin.unlink()

    if summary_rows:
        fieldnames = sorted({k for row in summary_rows for k in row})
        ordered = ["bytes", "kib", "in_bracket"] + [
            f for f in fieldnames if f not in ("bytes", "kib", "in_bracket")]
        with open(dest / "summary.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=ordered)
            writer.writeheader()
            writer.writerows(summary_rows)

    print(f"\nDone. {len(summary_rows)} points written to {dest}/summary.csv")
    print("Plot a chosen miss-count column (e.g. L1D-read-miss for an L1 "
          "sweep, LL-read-miss for LLC) against 'kib' on the SAME x-axis as "
          "the frozen Phase-I timing curve for this host/level, and shade "
          f"the bracket region [{round(low/1024,1)}, {round(high/1024,1)}] KiB.")


if __name__ == "__main__":
    main()