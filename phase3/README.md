# Phase III: Hazel measurements and ECE-only prediction evaluation

Five generations: Haswell, Cascade Lake, Ice Lake 8358, Genoa and Turin. This directory adds Phase-III work without modifying Phase-I or Phase-II files. Reports and slides are maintained separately and are not included here.

## Start here

- `hazel/results/cache-inference-table.csv`: cache quantities and limitations, one row per machine/cache role.
- `hazel/results/machine-results.csv`: machine identities, completed/noisy point counts and timing summary.
- `prediction/post_hazel/outputs/comparison-summary.md`: prediction evaluation and source citations.
- `prediction/post_hazel/outputs/chronological-master.csv`: the eight ECE plus five Hazel machines and all supported cache fields.
- `prediction/post_hazel/outputs/prediction-timing-published.csv`: three-way comparison; specifications never replace timing results.
- `prediction/post_hazel/outputs/team-laws-and-future.md`: both unchanged laws and the 2029 forecast.
- `plots/`: consolidated curve/box evidence and the two Phase-II chronological PMU series.
- `prediction/post_hazel/outputs/plots/`: vector chronological/prediction plots; unsupported physical quantities are explicit.

All 1,612 baseline and 3,606 follow-up points were verified; noisy/failed attempts remain traceable. Diagnostic throughput is not physical hit latency. Deeper capacity/ways, physical hit/miss penalties, sharing and inclusion retain their uncertainty.

## Reproduce and audit

`hazel/suite/` is the acquisition/analysis source and Slurm-driver snapshot used on Hazel; its four C sources match the existing shared Phase-I implementations. It preserves original paths and configurations for audit, not an invitation to launch duplicate measurements. To acquire new data, select a new output workspace, inspect resources, update the Slurm constraints/output paths, and smoke-test before submission. Never run benchmarks or heavy analysis on login nodes. Scheduler access is through Slurm only.

`hazel/analysis/evidence-records.json` contains verified distribution summaries, commands, parameters, raw hashes and source references needed to redraw evidence. `tools/render_evidence.py` redraws the compact evidence through Slurm. `prediction/pre_hazel/` preserves the original ECE-only model builder, inputs and outputs; do not refit this snapshot using Hazel.

The historical `prediction/post_hazel/build.py` expects the original Hazel workspace at `/share/ece592f26/hlee58/tmp/hazel-phase3-20260911`. Its original input and freeze manifests record exact paths and hashes. To rerun that full audit, restore that workspace from the separately retained data first; the compact Git package does not replace the raw archive. Existing Phase-I baseline JSONs included under `data_processed/` are the unchanged standardized-workload checks, not new measurements.

The preserved freeze manifests describe the original full workspace, so not every listed raw file is included in Git. `inventory.json` is the authoritative inventory for THIS curated package. Small scheduler histories, build metadata and final validation logs are under `hazel/runs/`, `hazel/logs/` and `verification/`.

## Raw data and scope

Original raw arrays and unsuccessful attempts remain at `/share/ece592f26/hlee58/tmp/hazel-phase3-20260911/runs/`; record/raw hashes are in `hazel/results/raw-record-inventory.json`. This is scratch storage, not a permanent raw-data deposit. Preserve or transfer that workspace before purge; no multi-gigabyte timing arrays, compiled binaries, temporary/debug files, duplicate raster previews, report sources or slides are committed here.

The two PMU series use the partner's `f0b43d2` Phase-II table, L1-resident regime, with counts per dependent access. Kernel generic-event semantics remain architecture-dependent; neither series is a physical miss probability or a fitted law. Earlier frozen analysis snapshots still describe their then-missing Phase-II inputs; this package supplies the later chronological overlay separately under `pmu/`.
