#!/usr/bin/env python3
"""Resolve real Phase-I boundaries from data_processed/all_machines/inferred-
cache-table.csv into per-host config usable by pmu_eight_counter.py and the
new boundary-correlation driver -- replaces the earlier PLACEHOLDER sizes now
that the phase1-timing-only tag exists.

IMPORTANT -- read this before trusting the numbers below:
Per PHASE1_HANDOFF.md, these are CONDITIONAL CANDIDATE BRACKETS, not exact
confirmed values -- the handoff explicitly states capacity brackets and
upper-level ways/sets are "conditional inferences," and that isolated
physical hit latency / miss penalty and inclusion/exclusion policy remain
UNRESOLVED. This script surfaces exactly what Phase I claims and nothing
more:
  - capacity: [low, high] byte interval per level -- treat the whole
    interval as the region to densely sample in Phase II, not a single point.
  - line size: 64 bytes, consistently observed across all 8 machines --
    this one is on firmer footing than the capacity brackets.
  - associativity: "candidate" ways only, several marked conditional.
  - hit_latency_median: present, but the handoff says isolated per-level
    hit latency is NOT independently established -- treat PMU comparison
    against this number as testing an already-acknowledged-uncertain
    baseline, not confirming a settled one.
  - inclusion/exclusion: uniformly "uncertain" for every host/level in the
    source table -- do not present a PMU result as resolving this.

Usage:
  python3 resolve_phase1_boundaries.py \
      --csv data_processed/all_machines/inferred-cache-table.csv \
      --out phase1_boundaries.json

Then feed a host's values into pmu_eight_counter.py, e.g. for sunbird:
  --l1-kib 33.0 --llc-kib 20480.0 --over-llc-kib 81920.0
(midpoints below; or use --low/--high per level for dense boundary sampling
in the new boundary-correlation step, §8.3.)
"""
import argparse
import ast
import csv
import json
from pathlib import Path


def parse_interval(raw):
    if not raw or raw == "[]":
        return None
    try:
        low, high = ast.literal_eval(raw)
        return float(low), float(high)
    except (ValueError, SyntaxError):
        return None


def bytes_to_kib(b):
    return round(b / 1024.0, 3)


LEVEL_KEY = {
    "L1-like candidate": "l1",
    "L2-like candidate": "l2",
    "LLC-like candidate": "llc",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", required=True,
                     help="path to data_processed/all_machines/inferred-cache-table.csv")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.csv, newline="")))

    hosts = {}
    for row in rows:
        host = row["host"]
        level = LEVEL_KEY.get(row["level"])
        if level is None:
            continue
        entry = hosts.setdefault(host, {})

        interval = parse_interval(row["prior_capacity_interval_bytes"])
        line_size = row["line_candidate_bytes"] or None
        ways = row["prior_ways_candidate"] or row["additional_conditional_ways"] or None
        hit_lat = row["hit_latency_median"] or None
        unit = row["unit"] or None
        inclusion = row["inclusion_exclusion"] or None
        sharing = row["sharing_scope"] or None

        level_entry = {
            "capacity_interval_bytes": list(interval) if interval else None,
            "capacity_interval_kib": [bytes_to_kib(interval[0]), bytes_to_kib(interval[1])]
                                       if interval else None,
            "capacity_midpoint_kib": bytes_to_kib((interval[0] + interval[1]) / 2)
                                       if interval else None,
            "line_size_bytes": int(line_size) if line_size else None,
            "ways_candidate": ways,
            "hit_latency_median": float(hit_lat) if hit_lat else None,
            "hit_latency_unit": unit,
            "inclusion_exclusion": inclusion,
            "sharing_scope": sharing,
            "status": "CONDITIONAL -- treat as bracket, not confirmed value",
        }
        entry[level] = level_entry

    # derive convenience over-LLC size: 4x the LLC bracket's high end,
    # rounded, per host -- purely a driver-input choice, not a Phase-I claim.
    for host, levels in hosts.items():
        if "llc" in levels and levels["llc"]["capacity_interval_bytes"]:
            llc_high = levels["llc"]["capacity_interval_bytes"][1]
            levels["over_llc_suggestion_kib"] = bytes_to_kib(4 * llc_high)

    Path(args.out).write_text(json.dumps(hosts, indent=2) + "\n")

    print(f"Resolved {len(hosts)} host(s) -> {args.out}")
    print("\nQuick reference (midpoint KiB per level, all CONDITIONAL per Phase-I handoff):")
    print(f"{'host':<12}{'L1 mid':>10}{'L2 mid':>12}{'LLC mid':>14}{'>LLC sugg.':>14}")
    for host, levels in sorted(hosts.items()):
        l1 = levels.get("l1", {}).get("capacity_midpoint_kib", "-")
        l2 = levels.get("l2", {}).get("capacity_midpoint_kib", "-")
        llc = levels.get("llc", {}).get("capacity_midpoint_kib", "-")
        over = levels.get("over_llc_suggestion_kib", "-")
        print(f"{host:<12}{l1!s:>10}{l2!s:>12}{llc!s:>14}{over!s:>14}")


if __name__ == "__main__":
    main()