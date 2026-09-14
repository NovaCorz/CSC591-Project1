#!/usr/bin/env python3
"""Phase II associativity PMU verification: dense PMU sampling across a sweep
of conflicting-address counts at a fixed congruence period, to test whether a
hardware eviction/miss transition coincides with the frozen Phase-I
associativity ("ways") candidate for a given host/level
(main_code/common/phase1/config/uncertainty-plan.json's "l1_ways"/"l1_period",
cross-checked against main_code/pmu/phase1_boundaries.json's "ways_candidate").

Wraps the REAL frozen kernel, main_code/common/phase1/src/followup_bench.c
(built as build/followup_bench), not a placeholder benchmark. followup_bench
is cache_bench.c plus the address-list/probe extension that Phase I's own
conflict-set eviction search already uses (see conflict_stage() in
followup_worker.py, and conflict_offsets() in uncertainty_worker.py). Its
exact CLI (verified from source):

    followup_bench MODE BYTES STRIDE OFFSET SAMPLES BATCH SEED CPU ORDER RAW \
        ALIGN PAGE_POLICY ADDRESS_LIST HELPER_CPU

  MODE = probe   (the only mode this script uses: reload a target cache line
                   after applying N-way congruent conflict pressure)

In probe mode, one 8-byte "target" cell lives at offset 0 of the mapping and
points to itself; it is never part of the address list. Each timed sample:
(1) re-touches the target 32x to keep it hot, (2) walks BATCH loads through a
pointer-chase cycle built from the addresses in ADDRESS_LIST -- here N
addresses spaced PERIOD bytes apart, all landing on the same candidate cache
set as the target -- applying conflict pressure, then (3) times exactly one
reload of the target. As N grows past the true number of ways, the target
line should stop surviving the pressure pass, and the timed reload should
shift from a hit-latency class to a miss-latency class. This script attaches
PMU counters (via pmu_stat) to that same probe so the miss-count transition
-- not just timing -- can be checked against N == ways_candidate.

IMPORTANT -- read before trusting results:
Per PHASE1_HANDOFF.md, associativity values are CONDITIONAL CANDIDATES, not
confirmed hardware values, and LLC ways in particular may not be a simple
textbook number under slicing/hashing. This script independently re-tests the
conflict-count transition with PMU counters; it is NOT a byte-for-byte replay
of Phase I's own empirical chunk-deletion address-set search (that discovery
procedure and its selected address sets live in conflict_stage() in
followup_worker.py / the external raw archive, and are not reconstructed
here). The PERIOD used below is L1's frozen per-host congruence period from
uncertainty-plan.json ("l1_period"); L2/LLC have no single frozen period in
that file -- Phase I's own L2/LLC conflict search tries several candidate
strides (see l2_stage() in followup_worker.py) -- so --period/--ways must be
supplied explicitly for those levels, using whatever candidate your own
Phase-I L2/LLC conflict analysis settled on.

Usage:
  # L1 (period/ways/seed auto-filled from uncertainty-plan.json):
  python3 associativity_correlation.py \
      --host charnwood --level l1 \
      --plan-json ../common/phase1/config/uncertainty-plan.json \
      --binary ../common/phase1/src/followup_bench \
      --pmu-stat ../pmu/pmu_stat --cpu 2 \
      --events cycles,instructions,L1D-read-access,L1D-read-miss,cache-misses \
      --events-per-run 2 \
      --out ../../data_raw/charnwood/pmu/associativity_correlation_l1

  # L2/LLC (period/ways from your own Phase-I candidate, supplied explicitly):
  python3 associativity_correlation.py \
      --host charnwood --level l2 --period 32768 --ways 8 \
      --binary ../common/phase1/src/followup_bench \
      --pmu-stat ../pmu/pmu_stat --cpu 2 \
      --events cycles,instructions,LL-read-access,LL-read-miss,cache-misses \
      --events-per-run 2 \
      --out ../../data_raw/charnwood/pmu/associativity_correlation_l2
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


def load_plan(path, host):
    """Pull l1_period/l1_ways/seed from uncertainty-plan.json, if given.
    Returns {} if the host isn't present -- caller falls back to explicit
    CLI args."""
    if not path:
        return {}
    data = json.loads(Path(path).read_text())
    return data.get("hosts", {}).get(host, {})


def default_counts(ways):
    # Dense through and just past the candidate ways value (mirrors the
    # handout's Figure 8 illustrative associativity sweep -- 1..12
    # conflicting lines with the transition shown at the ways boundary),
    # sparser further out to confirm the eviction plateau holds.
    dense = list(range(1, ways + 4))
    tail = [n for n in (ways + 5, ways + 6, ways + 8, ways + 12, ways + 16)
            if n > dense[-1]]
    return dense + tail


def address_list_path(cache_dir, period, count):
    # N addresses spaced PERIOD bytes apart, starting at 1*PERIOD so offset 0
    # (the target's own cell) is never part of the conflict/pressure set.
    offsets = [period * i for i in range(1, count + 1)]
    content = "\n".join(map(str, offsets)) + "\n"
    digest = hashlib.sha256(content.encode()).hexdigest()
    path = cache_dir / f"{digest}.txt"
    if not path.exists():
        path.write_text(content)
    return path, digest, offsets


def run_one_point(binary, pmu_stat, events, events_per_run, cpu, bytes_,
                   period, samples, batch, seed, order, align, page,
                   address_list, out_bin):
    invocation = [str(binary), "probe", str(bytes_), str(period), "0",
                  str(samples), str(batch), str(seed), str(cpu), order,
                  str(out_bin), str(align), page, str(address_list), "-1"]

    event_list = [e.strip() for e in events.split(",") if e.strip()]
    event_batches = [event_list[i:i + events_per_run]
                      for i in range(0, len(event_list), events_per_run)]

    combined_counters = {}
    batch_results = []
    all_stderr = []
    overall_returncode = 0

    for batch_idx, event_batch in enumerate(event_batches):
        batch_events = ",".join(event_batch)
        batch_cmd = [str(pmu_stat), "-e", batch_events, "--"] + invocation
        print(f"    PMU batch {batch_idx}: {batch_events}", flush=True)
        result = subprocess.run(batch_cmd, text=True, capture_output=True)
        stdout_lines = [ln for ln in result.stdout.splitlines() if ln.strip()]

        bench_meta = None
        counters = {}
        if stdout_lines:
            try:
                bench_meta = json.loads(stdout_lines[0])
            except json.JSONDecodeError:
                bench_meta = {"raw_stdout_line0": stdout_lines[0]}
            counters = parse_counter_line(stdout_lines[-1])

        if result.returncode != 0:
            overall_returncode = result.returncode

        enabled = counters.get("time_enabled_ns")
        running = counters.get("time_running_ns")
        if enabled is not None and running is not None:
            try:
                if int(enabled) > 0 and int(running) == 0:
                    overall_returncode = 1
                    print(f"    WARNING: batch {batch_idx} has "
                          f"time_running=0; counters are invalid.",
                          file=sys.stderr, flush=True)
            except ValueError:
                pass

        combined_counters.update({k: v for k, v in counters.items()
                                   if k not in ("time_enabled_ns", "time_running_ns")})
        batch_results.append({
            "event_batch": event_batch, "returncode": result.returncode,
            "bench_metadata": bench_meta, "counters": counters,
            "pmu_stat_stderr": result.stderr,
        })
        all_stderr.append(f"--- batch {batch_idx}: {batch_events} ---\n{result.stderr}")

    return {
        "invocation": invocation,
        "returncode": overall_returncode,
        "bench_metadata": batch_results[0]["bench_metadata"] if batch_results else None,
        "counters": combined_counters,
        "batches": batch_results,
        "pmu_stat_stderr": "\n".join(all_stderr),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", required=True)
    ap.add_argument("--level", required=True, choices=["l1", "l2", "llc"])
    ap.add_argument("--plan-json",
                     help="e.g. main_code/common/phase1/config/uncertainty-plan.json "
                          "-- auto-fills --period/--ways/--seed for l1 from "
                          "this host's 'l1_period'/'l1_ways'/'seed'; explicit "
                          "CLI values below always win")
    ap.add_argument("--period", type=int, default=None,
                     help="byte spacing between congruent conflict addresses "
                          "(the candidate set-congruence period). Required "
                          "for l2/llc; auto-filled from --plan-json's "
                          "'l1_period' for l1")
    ap.add_argument("--ways", type=int, default=None,
                     help="frozen Phase-I associativity candidate being "
                          "tested. Required for l2/llc; auto-filled from "
                          "--plan-json's 'l1_ways' for l1")
    ap.add_argument("--binary", required=True, help="path to followup_bench")
    ap.add_argument("--pmu-stat", required=True, help="path to pmu_stat")
    ap.add_argument("--cpu", type=int, required=True,
                     help="logical CPU pin -- use the SAME core Phase I used "
                          "for this host if possible (check final-affinity-"
                          "summary.csv)")
    ap.add_argument("--counts", type=int, nargs="+", default=None,
                     help="conflict-set sizes (number of congruent addresses) "
                          "to sweep (default: dense set bracketing --ways, "
                          "see default_counts())")
    ap.add_argument("--batch-multiplier", type=int, default=2,
                     help="pressure-pass loads per point = max(2, "
                          "multiplier * count), matching Phase I's own "
                          "conflict_stage() convention (batch=max(2,2*N))")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--samples", type=int, default=1_000_000)
    ap.add_argument("--order", default="random", choices=["random", "regular"])
    ap.add_argument("--align", type=int, default=0)
    ap.add_argument("--page", default="huge", choices=["base", "huge"],
                     help="default huge, matching Phase I's own "
                          "conflict_stage() default (reduces TLB-miss "
                          "confounds during the conflict/pressure pass)")
    ap.add_argument("--events", required=True)
    ap.add_argument("--events-per-run", type=int, default=2,
                     help="number of PMU events measured together per run "
                          "(default: 2, to avoid multiplexing)")
    ap.add_argument("--keep-raw", action="store_true",
                     help="keep each point's raw .bin timing samples instead "
                          "of deleting them after the counters are read")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    plan = load_plan(args.plan_json, args.host)
    if args.level == "l1":
        period = args.period or plan.get("l1_period")
        ways = args.ways or plan.get("l1_ways")
    else:
        period = args.period
        ways = args.ways
    if not period or not ways:
        sys.exit(f"--period and --ways are required for level '{args.level}' "
                  f"on host '{args.host}' (l1 can auto-fill both from "
                  f"--plan-json; l2/llc must be supplied explicitly, since "
                  f"Phase I's own L2/LLC conflict search tries several "
                  f"candidate periods rather than freezing one -- see "
                  f"l2_stage() in followup_worker.py)")

    seed = args.seed or plan.get("seed", 5922026)
    counts = sorted(set(args.counts or default_counts(ways)))
    counts = [c for c in counts if c >= 1]
    if not counts:
        sys.exit("no valid conflict counts to sweep")

    binary = Path(args.binary).resolve()
    pmu_stat = Path(args.pmu_stat).resolve()
    if not binary.is_file():
        sys.exit(f"followup_bench binary not found at {binary} "
                  f"(build it with `make` in main_code/common/phase1)")
    if not pmu_stat.is_file():
        sys.exit(f"pmu_stat binary not found at {pmu_stat}")

    dest = Path(args.out)
    dest.mkdir(parents=True, exist_ok=False)
    address_dir = dest / "address-sets"
    address_dir.mkdir(exist_ok=True)

    environment = {
        "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "hostname": command(["hostname"]),
        "target_host": args.host,
        "target_level": args.level,
        "period_bytes": period,
        "ways_candidate": ways,
        "counts_swept": counts,
        "batch_multiplier": args.batch_multiplier,
        "seed": seed, "samples": args.samples, "order": args.order,
        "align": args.align, "page": args.page, "cpu": args.cpu,
        "git_commit": command(["git", "rev-parse", "HEAD"]),
        "binary_sha256": sha256_of(binary),
        "pmu_stat_sha256": sha256_of(pmu_stat),
        "command": sys.argv,
        "PHASE1_CAVEAT": (
            "ways_candidate is a conditional Phase-I candidate, not a "
            "confirmed hardware value, per PHASE1_HANDOFF.md. This script "
            "independently re-tests the conflict-count eviction transition "
            "with PMU counters attached to followup_bench's real probe-mode "
            "kernel; it does not replay Phase I's own empirical "
            "chunk-deletion address-set search (see conflict_stage() in "
            "followup_worker.py)."
        ),
    }
    (dest / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")

    print(f"[{args.host}/{args.level}] period={period} B  ways_candidate={ways}  "
          f"seed={seed} samples={args.samples} page={args.page}")
    print(f"Sweeping {len(counts)} conflict-set sizes: {counts}")

    summary_rows = []
    for i, n in enumerate(counts):
        addr_path, addr_sha, offsets = address_list_path(address_dir, period, n)
        bytes_ = period * (n + 2)
        batch = max(2, args.batch_multiplier * n)
        stem = dest / f"point_{i:02d}_{n:03d}way"
        out_bin = stem.with_suffix(".bin")
        relation = "below" if n < ways else ("at" if n == ways else "above")
        print(f"  [{i+1:2d}/{len(counts)}] N={n:>3d} conflicting lines "
              f"({relation} ways_candidate={ways})", flush=True)

        result = run_one_point(binary, pmu_stat, args.events, args.events_per_run,
                                args.cpu, bytes_, period, args.samples, batch,
                                seed, args.order, args.align, args.page,
                                addr_path, out_bin)

        (stem.with_suffix(".json")).write_text(json.dumps({
            "conflict_count": n, "period_bytes": period, "bytes": bytes_,
            "batch": batch, "address_list_sha256": addr_sha,
            "address_offsets": offsets, "relation_to_ways_candidate": relation,
            **result,
        }, indent=2) + "\n")
        (stem.with_suffix(".pmu_stat.stderr")).write_text(result["pmu_stat_stderr"])

        if result["returncode"] != 0:
            print(f"    WARNING: nonzero exit ({result['returncode']})",
                  file=sys.stderr)

        row = {"conflict_count": n, "period_bytes": period, "bytes": bytes_,
               "batch": batch, "relation_to_ways_candidate": relation,
               **result["counters"]}
        summary_rows.append(row)

        if out_bin.exists() and not args.keep_raw:
            out_bin.unlink()

    if summary_rows:
        fieldnames = sorted({k for row in summary_rows for k in row})
        lead = ["conflict_count", "period_bytes", "bytes", "batch",
                "relation_to_ways_candidate"]
        ordered = lead + [f for f in fieldnames if f not in lead]
        with open(dest / "summary.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=ordered)
            writer.writeheader()
            writer.writerows(summary_rows)

    print(f"\nDone. {len(summary_rows)} points written to {dest}/summary.csv")
    print(f"Plot a chosen miss/access-ratio column (e.g. L1D-read-miss / "
          f"L1D-read-access for an L1 sweep, LL-read-miss / LL-read-access "
          f"for LLC) against conflict_count; look for a transition near "
          f"N={ways} (the frozen Phase-I ways_candidate).")


if __name__ == "__main__":
    main()