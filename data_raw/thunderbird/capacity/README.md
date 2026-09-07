# Selected capacity data for this machine

Only the main `full` sweep and `refine-small`, `refine-middle`, `refine-large`
follow-ups are included, with their build/run/environment/source provenance.
Crux uses its CPU 2 campaign only. Pilots and additional diagnostics are not in
this checkout; originals remain in the working archive named by the exclusion
manifest. See the [root README](../../../README.md) for the exact selection.

In `data_raw`, gzip-decode `.bin.gz` files to uint64 durations according to each
matching JSON's byte order. Each full-count distribution has 1,000,000 samples.
Workload durations time 4,096 dependent reads/batch; divide by 4,096 for ticks/read.
Empty controls remain ticks/pair, without subtraction. Warmup is excluded.
CSV and plot counterparts keep the same campaign/run suffix under
`data_processed/<host>/capacity/` and `plots/capacity/<host>/`.

The [active manifest](../../../data_processed/capacity_file_manifest.json) lists
only retained files and decoded checksums. The
[exclusion manifest](../../../data_processed/capacity_excluded_manifest.json)
records removed copies, not inputs needed for restoration. Raw archives remain
Git-ignored locally. The spec-required final all-data handoff must also include
the preserved excluded runs separately; this selected checkout alone is incomplete.
