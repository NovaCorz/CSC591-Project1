# Selected timing-only capacity results

The repository contains the eight main powers-of-two sweeps and their matching
small/middle/large refinements. The seven non-Crux hosts use `capacity-20260906`;
Crux uses `crux-new-core-20260906T235055Z` (CPU 2). **This selection is not a
Phase I freeze or a declaration of confirmed cache sizes.**

Pilots, old Crux CPU 0 results and additional diagnostic datasets are outside
this checkout by the user's request. Their originals remain in
`/mnt/ncsudrive/h/hlee58/ECE592_proj1`; see the
[exclusion manifest](../../data_processed/capacity_excluded_manifest.json).
The spec's all-collected-data handoff requirement remains applicable.

## Method and retained artifacts

Each workload distribution contains 1,000,000 timed batches of 4,096 dependent
reads, with seed 592 and 8-byte node spacing. The sweeps span 4 KiB–256 MiB;
refinement sizes were selected from observed timing regions, not cache specs.
The native binary, CPU placement, and settings match within each selected pair.
Both randomized and sequential traversals and empty controls are preserved.
The randomized traversal is the primary capacity evidence; sequential traversal
is the prefetch/locality sanity check. No raw samples or outliers were removed.

There are 918 retained distributions (280 coarse + 638 refinement). The analysis
checks completion, configurations, million-sample counts, file lengths, units,
CPU, source/binary hashes, seed/spacing/batch settings, and percentile ordering.
Every analyzed run has statistics, capacity curves and randomized box plots.

- [Selected eight-machine overview](../../plots/capacity/all_machines/capacity-20260906/capacity_overview.pdf) — updated to Crux CPU 2
- [Small-region comparison](../../plots/capacity/all_machines/capacity-20260906/refinement-analysis/small_comparison.pdf)
- [Middle-region comparison](../../plots/capacity/all_machines/capacity-20260906/refinement-analysis/middle_comparison.pdf)
- [Large-region comparison](../../plots/capacity/all_machines/capacity-20260906/refinement-analysis/large_comparison.pdf)
- [All 918 summary rows](../../data_processed/all_machines/capacity/capacity-20260906/refinement-analysis/all_summaries.csv)
- [176 same-placement overlap comparisons, both traversals](../../data_processed/all_machines/capacity/capacity-20260906/refinement-analysis/overlap_comparison.csv)
- [Input paths, placement and hashes](../../data_processed/all_machines/capacity/capacity-20260906/refinement-analysis/manifest.json)
- [Packaged file mapping and checksums](../../data_processed/capacity_file_manifest.json)

The comparison input manifest uses original `results/` paths; the packaged-file
manifest maps those to this checkout. Means, medians, sample SD, quartiles, p5/p95,
outlier and zero counts are retained. Empty controls are ticks/pair; workloads are
ticks/access. No overhead subtraction is applied. Shaded bands show distributions,
not confidence intervals; connecting lines are not measurements between points.

## What the retained data supports

The following first-rise brackets are adjacent measured sizes in the refinements.
Near-flat timing followed by a sustained rise supports a candidate first data-cache
capacity near the lower endpoint. These are not confidence intervals or proof of
exact physical capacities. Medians are the host's own ticks/access (TSC on x86;
Arm counter ticks on Thunderbird), not directly comparable cross-ISA core cycles.

| Host | First-rise bracket | Refinement medians, lower → upper |
| --- | --- | --- |
| Sunbird | 32–36 KiB | 4.052 → 5.077 |
| Thunderbird | 64–72 KiB | 0.03394 → 0.04272 |
| Skylark | 32–36 KiB | 2.977 → 3.715 |
| Artemisia | 48–52 KiB | 5.076 → 6.027 |
| Charnwood | 32–36 KiB | 5.375 → 6.750 |
| Crux CPU 2 | 32–36 KiB | 2.652 → 3.354 |
| Ookay | 32–36 KiB | 3.581 → 4.512 |
| Upgrade | 32–36 KiB | 2.941 → 3.713 |

Middle-region capacities remain unresolved. Sunbird/Charnwood show changes around
160–192 KiB and further rises through 256–512 KiB; Skylark rises across 256–1024 KiB;
Thunderbird's stronger rise develops around 640–1024 KiB and continues toward
4 MiB. Crux has intermediate plateaus; Ookay/Upgrade have local reversals;
Artemisia is non-monotonic around 2 MiB. Do not count each bend as another cache.

| Host | Large-region observation and qualification |
| --- | --- |
| Sunbird | Approximately flat through 24 MiB (44.19), then 54.55 at 26 MiB; candidate onset 24–26 MiB, with wide tails at some later points. |
| Skylark | 28.61 at 16 MiB to 60.77 at 18 MiB, then sustained rise; candidate onset 16–18 MiB, with consistent coarse overlap. |
| Ookay | Rise develops over 4–6 MiB (43.65, 53.90, 77.09); not one exact capacity. |
| Upgrade | Near-flat 4–5 MiB, then a developing rise through 6–9 MiB; broad transition. |
| Thunderbird | Rise around 20–26 MiB, but irregular increases/decreases at larger footprints; provisional. |
| Artemisia | Broad distributions and reversals at middle/large footprints; no stable sharp boundary established. |
| Charnwood | Strong rise between 2 and 4 MiB, but sparse coverage there and substantial cross-run disagreement. |
| Crux CPU 2 | Strong rise at 5–7 MiB followed by a decrease at 8 MiB; no clean unique boundary established. |

Sequential traversal is faster at the largest refined footprint on every host.
For example, Skylark at 64 MiB is 217.79 randomized versus 3.06 sequential TSC
ticks/access. This is consistent with regular-access locality/prefetch effects,
not a measurement isolating their individual causes.

## Disagreement within the selected pairs

Relative median change is `100 × (refinement/coarse − 1)` at the same footprint
and traversal. This table concerns randomized overlaps; the CSV includes both
modes and all statistics. The 5% screen is descriptive, not a spec requirement,
significance test, or automatic acceptance threshold.

| Host | Overlaps within 5% | Largest absolute shift, signed |
| --- | --- | --- |
| Sunbird | 9/10 | +26.7% at 256 KiB |
| Thunderbird | 8/11 | +9.9% at 16 MiB |
| Skylark | 10/10 | +3.5% at 1 MiB |
| Artemisia | 7/13 | +64.9% at 2 MiB |
| Charnwood | 1/11 | +73.6% at 4 MiB |
| Crux CPU 2 | 6/11 | +26.2% at 256 KiB |
| Ookay | 10/11 | −14.5% at 128 KiB |
| Upgrade | 9/11 | −21.5% at 128 KiB |

Keep both curves separate; do not select a convenient median or silently average
away disagreement. The preserved external diagnostics also found variability;
excluding their copies here does not overturn that finding. CPU frequency,
allocation/page effects, address translation, and contention remain possible
explanations rather than established causes. No exact full hierarchy, per-level
pure-hit latency, or proven pure-DRAM latency is finalized.

## Reproduction and constraints

Follow the [root README](../../README.md) to restore only retained inputs, rerun
all selected per-run plots, and regenerate the overview and refinement comparison.
No excluded pilot/diagnostic or old Crux CPU 0 data is needed for those commands.
Original absolute commands in historical records are provenance; use new output
paths and native builds if conducting any new, separately authorized experiment.

The spec's timing-only, `-O0`, warmup, dependent-load, affinity, distribution and
sequential-control requirements are retained. Quiet-core preflights are not
reservations; no reservation or isolation guarantee is claimed. PMU/cache-spec
lookups, Hazel execution and a Phase I freeze have not occurred. Remaining
experiments, final report/source listings/diagrams, AI disclosure, and accurate
student contributor labels are still required. Do not invent contributor names
or change findings to resemble reference cache specifications.
