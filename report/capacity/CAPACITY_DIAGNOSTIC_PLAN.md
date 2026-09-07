# Targeted timing-only repeatability checks

Authorized after the completed coarse/refinement comparison. This is not a new
phase or a request to identify cache parameters from specifications.

## Question and prior evidence

Do the disputed medians recur across fresh executions with the same relative
address order, footprint list, CPU placement, binary, and timing batch length?
The same-run lower-footprint controls help distinguish broad timing shifts from
changes confined to larger footprints, but do not identify the causal mechanism.

Read-only examination of ten consecutive 100,000-sample chunks showed persistent
differences, not merely a few isolated outliers. Charnwood's 4 MiB chunk medians
were approximately 66.04–66.23 in the coarse run and 114.55–115.27 in refinement.
Crux CPU 2's 256 KiB chunks were approximately 8.26 versus 10.41–10.45. Artemisia's
2 MiB chunks were approximately 16.07–17.45 versus 26.55–27.60. Units are TSC
ticks/access. These are descriptive time-order checks, not confidence intervals.

Whole-run activity records show Charnwood's sibling CPU 6 averaged 0.5% busy
during the coarse run and 1.3% during large refinement. Artemisia's sibling CPU 61
averaged 7.1% and 4.2%, respectively. Such averages cannot rule out short bursts,
shared-resource contention, or unrelated run-condition changes. Near-100% activity
on the selected CPU is expected while our benchmark runs, not proof of interference.

## Fixed plan

| Host | CPU/core/socket/NUMA; siblings | Footprints (KiB) |
| --- | --- | --- |
| Charnwood | 2/2/0/0; [2, 6] | 16, 32, 64, 2048, 2560, 3072, 3584, 4096, 5120 |
| Crux | 2/2/0/0; [2] | 32, 128, 256, 4096, 5120, 6144, 7168, 8192 |
| Artemisia | 5/5/0/0; [5, 61] | 32, 1536, 1792, 2048, 2304, 2560, 3072 |

The saved preflight metadata is authoritative for placement. Charnwood adds
0.5 MiB steps between 2 and 4 MiB, where its previous sampling was sparse.
Crux repeats the inconsistent 128/256 KiB and 4–8 MiB regions; Artemisia covers
both its old 2 MiB dip and the new 2.25 MiB dip. Small controls are deliberately
included in the same repeat list.

Each host runs **three identical repeats**, one at a time, using its saved native
`-O0` binary and collector. Each repeat includes both traversal modes and an empty
control, with 1,000,000 samples per point, 4,096 dependent loads/batch, seed 592,
and 8-byte spacing. No warmup samples count toward the million. This is 57/51/45
distributions on Charnwood/Crux/Artemisia, 153 million total samples (1.224 GB raw).
Each repeat is independently shuffled by the same seed, so configuration order
is the same across these repeats. The configuration order differs from earlier
full/refinement sweeps because the size list differs. Relative pointer order at
an overlapping footprint is unchanged. Fresh processes allocate fresh memory;
virtual/physical mappings and OS conditions are not held fixed. No page-policy,
frequency, or system settings are changed.

Before **each** repeat, the driver checks the original selected core and all its
SMT siblings for two seconds, and defers if any exceed 10% busy. This threshold is
an operational screen, not a spec requirement or reservation. There is no forced
CPU change, automatic retry, or stopping of another user's processes. Whole-repeat
OS activity is saved, including all CPUs; it includes setup and our own workload.

The reservation sheet was previously inaccessible (HTTP 401); the fresh browser
attempt also failed. No reservation is claimed. These checks test repeatability
under screened but unreserved conditions; they cannot establish absence of
interference. If interference prevents clean measurements, the spec requires
reservation coordination rather than treating this screen as a substitute.

## Reproduce and assess

From the shared project root on each listed host:

```bash
python3 test_diagnostic_capacity.py
python3 diagnostic_capacity.py results/capacity-diagnostic-20260907
```

The output host directory must not already exist. Source/plan snapshots, selected
placement, hashes, preflights, and activity records are retained. The driver stops
on a failed/busy check without overwriting or deleting completed repeats.
`repeatN/COMPLETE` marks one successful collection; host `COMPLETE` marks all three.
Analyze completed repeats with the existing `capacity.py plot DIRECTORY` command.

Compare means, medians, SD, quartiles, p5/p95, outlier counts and time-ordered
chunks against both earlier campaigns and between the three repeats. Keep all
distributions separate. Similar small controls with shifting large points would
argue against one uniform timing multiplier, but would not prove allocation or
interference as the cause. Report unresolved uncertainty if shifts remain. Do
not choose the run matching a textbook value, subtract empty overhead, infer
cache sharing from CPU topology alone, or freeze Phase I on this diagnostic.
