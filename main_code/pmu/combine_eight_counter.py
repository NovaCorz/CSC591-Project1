#!/usr/bin/env python3
"""Combine per-host eight_counter-<date>/ output directories (one produced per
machine by pmu_eight_counter.py, run separately over SSH on each of the 8 ECE
machines) into one cross-machine dataset, normalized and ranked, per §8.4.

You cannot run pmu_eight_counter.py itself across all 8 machines at once --
each host requires its own SSH session and its own compiled binaries. This
script instead runs *after* you've pulled each host's output directory back
to one place (e.g. via `git pull` once every machine's results are committed,
or `scp` directly), and does the cross-host combination step.

Usage:
  python3 combine_eight_counter.py \
      --dirs data_raw/sunbird/pmu/eight_counter \
             data_raw/thunderbird/pmu/eight_counter \
             data_raw/skylark/pmu/eight_counter \
             ... (all 8) \
      --out data_processed/eight_counter_cross_machine

Produces:
  <out>/combined_long.csv   -- one row per (host, regime, event), normalized
  <out>/ranked_<regime>.csv -- one wide table per regime: rows=host sorted by
                               rank, columns=normalized event values
"""
import argparse
import csv
import json
from pathlib import Path


def load_host_dir(d):
    d = Path(d)
    env_path = d / "environment.json"
    summary_path = d / "summary.csv"
    if not env_path.is_file() or not summary_path.is_file():
        raise SystemExit(f"{d}: missing environment.json or summary.csv "
                          f"-- did pmu_eight_counter.py finish successfully here?")
    env = json.loads(env_path.read_text())
    hostname = env.get("hostname", d.parent.parent.name)
    cpu_model = env.get("cpu_model", "unknown")

    rows = []
    with open(summary_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return hostname, cpu_model, rows


def numeric_event_columns(rows):
    skip = {"regime", "size_kib", "mode", "samples", "steps"}
    cols = set()
    for row in rows:
        for k, v in row.items():
            if k in skip:
                continue
            if v == "UNAVAILABLE":
                continue
            try:
                float(v)
                cols.add(k)
            except (TypeError, ValueError):
                pass
    return sorted(cols)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dirs", nargs="+", required=True,
                     help="one eight_counter-<date> directory per host")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    long_rows = []
    for d in args.dirs:
        hostname, cpu_model, rows = load_host_dir(d)
        for row in rows:
            try:
                samples = float(row.get("samples", 0))
                batch_size = float(row.get("batch_size", 0))
                denom = samples * batch_size
            except (TypeError, ValueError):
                samples = batch_size = 0

            for k, v in row.items():
                # Only process actual PMU events.
                if k not in {
                    "DTLB-read-miss",
                    "L1D-read-access",
                    "L1D-read-miss",
                    "LL-read-access",
                    "LL-read-miss",
                    "cache-misses",
                    "cycles",
                    "instructions",
                }:
                    continue

                if v == "UNAVAILABLE":
                    normalized = None
                else:
                    try:
                        raw = float(v)
                        normalized = raw / denom if denom else None
                    except (TypeError, ValueError):
                        normalized = None

                long_rows.append({
                    "hostname": hostname,
                    "cpu_model": cpu_model,
                    "regime": row.get("regime"),
                    "size_kib": row.get("size_kib"),
                    "mode": row.get("mode"),
                    "event": k,
                    "raw_value": v,
                    "per_access": normalized,
                })

    if not long_rows:
        raise SystemExit("No data loaded -- check --dirs paths.")

    long_fields = ["hostname", "cpu_model", "regime", "size_kib", "mode",
                   "event", "raw_value", "per_access"]
    with open(out / "combined_long.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=long_fields)
        writer.writeheader()
        writer.writerows(long_rows)

    # Wide, ranked table per regime: rows = host, columns = per-access event
    # values, sorted by the first event for readability. One file per regime
    # (l1_resident / llc_sized / larger_than_llc) so it matches the three
    # standardized workloads in §8.4.
    regimes = sorted({r["regime"] for r in long_rows if r["regime"]})
    all_events = sorted({r["event"] for r in long_rows})

    for regime in regimes:
        wide = {}
        for r in long_rows:
            if r["regime"] != regime:
                continue
            key = (r["hostname"], r["cpu_model"])
            wide.setdefault(key, {})[r["event"]] = r["per_access"]

        rank_event = all_events[0] if all_events else None
        def sort_key(item):
            v = item[1].get(rank_event)
            return (v is None, v if v is not None else 0)
        ordered_hosts = sorted(wide.items(), key=sort_key)

        fieldnames = ["hostname", "cpu_model"] + all_events
        with open(out / f"ranked_{regime}.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for (hostname, cpu_model), events in ordered_hosts:
                row = {"hostname": hostname, "cpu_model": cpu_model}
                row.update({e: events.get(e, "") for e in all_events})
                writer.writerow(row)

    print(f"Combined {len(args.dirs)} host(s) into {out}/")
    print(f"  combined_long.csv          -- full normalized long-format data")
    for regime in regimes:
        print(f"  ranked_{regime}.csv  -- wide ranked table for that workload")


if __name__ == "__main__":
    main()