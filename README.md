# CSC591 Project 1: Cache experiments and prediction

This repository contains the eight-machine ECE timing experiments (Phase I), ECE PMU measurements and estimator comparisons (Phase II), five-generation Hazel measurements and prediction evaluation (Phase III), and the frozen competition estimator. Timing inferences, published cache information, and PMU comparisons remain separate; later verification does not replace the original measurements or resolve every cache property.

- [GitHub repository](https://github.com/NovaCorz/CSC591-Project1)
- [Overleaf report](https://www.overleaf.com/read/gyrqznmvwbsd#2b5b1c)

Final submission PDFs are included in this repository:

- [Final report (`report/HW1_report.pdf`)](report/HW1_report.pdf)
- [Final slide deck (`slides/HW1_slides.pdf`)](slides/HW1_slides.pdf)

The Overleaf report source is maintained in the shared Overleaf project linked above. Before submission, both team members must verify that the instructor and TA can access both GitHub and Overleaf; access-control settings are not recorded in this repository. Large timing archives remain external at the locations recorded below and in each phase's manifests and must be included in the Moodle package or an instructor-approved alternate handoff.

## Start here

| Work | Code, results, and documentation |
|---|---|
| Phase I: eight ECE machines | [Final timing-inference table](data_processed/all_machines/inferred-cache-table.csv), [latency classes](data_processed/all_machines/followup-latency-classes.csv), [selected report-supporting raw data](data_raw/phase1_timing_selected/), and [shared benchmark suite](main_code/common/phase1/). Methodology and reproduction instructions follow below. |
| Phase II: PMU measurements | [PMU code](main_code/pmu/), per-machine `data_raw/<host>/pmu/` records, and [three-workload cross-machine counter tables](data_processed/eight_counter_cross_machine/). Unavailable events are retained as limitations. |
| Phase II: software-estimator comparison | [Method, verified comparisons, and raw-data locations](estimator_validation/README.md). Counter populations and timing classifications differ, limiting accuracy claims. |
| Phase III: Hazel and predictions | [Results and reproduction guide](phase3/README.md) and [selected report-supporting raw data](data_raw/phase3_timing_selected/): Haswell, Cascade Lake, Ice Lake 8358, Genoa, and Turin; ECE-only predictions, timing/published comparisons, chronological plots, two cache laws, and the 2029 forecast. |
| Competition | [Fixed estimator and execution instructions](competition/README.md), [70-candidate scorecard](competition/scorecard.csv), and [release handoff](COMPETITION_HANDOFF.md). |

## Competition release

The annotated tag **`competition-v1`** identifies release commit **`62d3d2b1b8539303772e2783c575cd0972df3335`**. Parameters and source hashes were frozen at `2026-09-14T03:22:58.604722+00:00`; the commit timestamp is `2026-09-14T03:24:02Z`. Later documentation commits do not move this tag or change the frozen estimator.

[COMPETITION_HANDOFF.md](COMPETITION_HANDOFF.md) records the release verification and submission references. The release includes 648 manifest-listed Phase-III files and 107 estimator-validation files. The competition entry point passed a small smoke test and agreement checks against the original classifier; these checks are not an official competition score. Its runtime estimator uses timing only.

On Hazel, use Slurm for benchmarks, raw-data processing, and substantial analysis; never run them on a login node or connect directly to compute nodes. ECE acquisition commands below target the designated lab hosts. Use fresh output locations for new runs and preserve the frozen evidence.

## Historical Phase-I freeze and handoff

Read [PHASE1_HANDOFF.md](PHASE1_HANDOFF.md) for the original timing-only handoff. The annotated `phase1-timing-only` tag preserves this dataset; [phase1-freeze.json](phase1-freeze.json) identifies the separate report and all three raw archives. The handoff records the unresolved controls and inclusion sequencing limitation.

## Phase-I results and limitations

These are conditional timing candidates. Capacity brackets describe observed transitions, not statistical confidence intervals or verified hardware specifications. Earlier correct baseline and follow-up evidence is retained because the additional experiment builds on it; the final table and final inference JSON take precedence over earlier candidate interpretations.

| Machine | L1-like KiB / conditional ways | L2-like KiB / conditional ways | LLC-like timing evidence, MiB | Additional noisy/full configurations |
|---|---|---|---|---|
| sunbird | 32–36 / 8 | 256–288 / 8 | 8–32 | 0/132 |
| thunderbird | 64–72 / 4 | 1024–1152 / 8 | 16–18 | 101/1099 |
| skylark | 32–36 / 8 | 512–576 / 8 | 16–18 | 0/29 |
| artemisia | 48–52 / 12 | 2048–2304 / 16 | 24–26 | 0/29 |
| charnwood | 32–36 / 8 | 256–288 / 4 | 4–8 | 33/107 |
| crux | 32–36 / 8 | 256–288 / 4 | 4–16 | 2/509 |
| ookay | 32–36 / 8 | 256–288 / 4 | 5–5.5 | 0/26 |
| upgrade | 32–36 / 8 | 256–288 / 4 | 2–16; new departure 7.6875–8.125 | 4/136 |

All eight machines supported a visible 64 B spatial boundary in all eight additional cohorts per machine. This does not independently identify the physical line size of every level. Thunderbird's additional 8-way and Crux's 4-way lower-level candidates depend on the tested indexing period and hierarchy interpretation. LLC ways, exact sharing domains, inclusion/exclusion, individual hardware hit latencies and isolated miss penalties remain uncertain. The new Upgrade departure does not by itself establish a physical LLC capacity. Noise flags and unsuccessful historical attempts have been retained without altering measurements.

The additional round contains **2,067 selected full configurations, 2,483 full attempts and 36 smoke attempts**. Of these, **140 selected distributions are noisy** and **556 attempts carry flags**; these totals include different units of counting. Full coverage and raw-integrity checks passed, with no incomplete raw attempt in this additional round. This does not mean every physical-cache question was resolved.

The authoritative machine-readable result is [inferred-cache-table.csv](data_processed/all_machines/inferred-cache-table.csv). Effective latency distributions and descriptive same-core differences are in [followup-latency-classes.csv](data_processed/all_machines/followup-latency-classes.csv). The software timing metric, hot/cold calibration, threshold sensitivity and uncertainty are in each machine's `baseline-inference.json` under `software_metric`. It is a software timing proxy. The later [matched PMU comparison](estimator_validation/README.md) quantifies differences against hardware-counter references, but does not establish individual-load classification accuracy. Native TSC/CNTVCT timer ticks are not labelled core cycles.

## Measurements retained

| Experiment family | Evidence and purpose |
|---|---|
| Capacity and hierarchy | Dependent random pointer cycles from 1 KiB to 256 MiB, regular-order controls, dense/sparse spacing, ordinary/huge-page comparisons, adaptive refinement, additional same-core matched comparisons. |
| Spatial granularity | Offset and alignment sweeps; shifted-boundary confirmations across footprints, seeds and mapping cohorts. |
| Conflict/associativity | Conflict-stride/count sweeps, empirical candidate sets, held-out tests, fixed upper-level scrub controls, batched conflict measurements and prospective matched repairs. |
| Latency and miss behavior | Full native-time distributions, effective residency classes, hot/pressure reloads and same-core class differences; hardware-level assignments qualified. |
| Sharing and inclusion behavior | Paired-core pressure versus handshake-only controls; same measuring/helper-pair and quality checks; unresolved physical policy stated. |
| Software metric | Hot/cold calibration and workload classification with threshold sensitivity; no hardware-counter validation in Phase I. |
| Measurement quality | Timer/loop controls, native build and smoke gates, affinity, two idle windows, SMT sibling activity, page backing, seeds, source/environment records, raw hashes and retry explanations. |

At least one million timed intervals were required for each full distribution; small smoke measurements were excluded from inference. Correlated intervals are not treated as independent experimental replications. The worker checks idle activity on a physical core and its SMT siblings using two one-second windows at a maximum 5% busy threshold. It waits if none qualifies and reselects when necessary. Per-attempt `idle.json` files and affinity records remain in the external archives; [final-affinity-summary.csv](data_processed/all_machines/final-affinity-summary.csv) links to that evidence.

## Independent-load diagnostic supplement

The required §8.2 diagnostic is now completed on all eight hosts. One dependency
chain and four independent chains traverse the same 1 KiB randomized address set,
with four loads per loop iteration and 4,096 loads per timed interval. Three seeds
in both execution orders give **48/48 qualified same-core pairs**. Every full
configuration has one million intervals. Independent timing is throughput evidence,
not a replacement physical hit-latency estimate or a new cache-geometry result.

| Machine | Median D/I ratio across six pairs | Full pair-ratio range | Selected logical CPUs |
|---|---:|---|---|
| sunbird | 3.9378 | 3.9340–3.9378 | 5, 7 |
| thunderbird | 3.9429 | 3.9429–3.9429 | 1 |
| skylark | 3.9062 | 3.9062–3.9062 | 3 |
| artemisia | 3.9611 | 3.9596–3.9615 | 28, 54 |
| charnwood | 3.9709 | 3.9664–4.0781 | 1, 2 |
| crux | 3.9925 | 3.9855–3.9948 | 2 |
| ookay | 3.9850 | 3.9828–3.9855 | 3 |
| upgrade | 3.9880 | 3.9839–3.9893 | 4 |

Ratios above are rounded to four decimals; exact statistics and ratios are in
[data_processed/independent-load/summary.csv](data_processed/independent-load/summary.csv).
The supplement retains 180 full attempts, including 20 noisy attempts, plus 32
smoke attempts. All 180,065,536 raw intervals were checked. Charnwood required a
fresh-cohort calibration repair after noise/core mismatch and a longer quiet
window. Every earlier failed calibration and noisy attempt remains in the external
archive. Native ticks are not core cycles; frequency/interference between runs,
wrapper costs, and the single hot footprint limit interpretation.

The combined figure is [distributions.svg](plots/independent-load/distributions.svg).
Full per-run statistics, all-attempt metadata, native loop audits, compiler records,
calibration/selection gates, and the selected runs' original idle evidence are under
`data_processed/independent-load/`. Public lab host keys are included for reproducible
SSH checks; no passwords or private keys are included. The existing report and
slides directories remain empty.

[Method and reproduction instructions](main_code/common/phase1/docs/independent-load-method.md)
include the new controller, raw verifier, plotter, and quality-repair procedure.
Run acquisition from a separate working copy of `main_code/common/phase1/`.
The complete supplement archive remains outside Git at
`/gpfs_common/share03/rotenberg/hlee58/ECE592_proj1/artifacts/phase1-independent-load.zip`.
Restore it independently of the two older archives, into a new empty workspace:

```bash
python3 main_code/common/phase1/scripts/restore_independent.py \
  --archive /path/to/phase1-independent-load.zip \
  --manifest data_processed/independent-load/archive-manifest.json \
  --workspace /absolute/canonical/path/to/new-workspace
cd /absolute/canonical/path/to/new-workspace
python3 scripts/analyze_independent.py
python3 scripts/plot_independent.py
```

## Repository layout and Phase-I provenance

- `main_code/common/phase1/`: native C kernels, Makefile, frozen policies, acquisition/analysis scripts and 48 functional tests (42 original plus six diagnostic tests). Original measurement and analysis files are byte-for-byte copies. Two plotting-only modules extract the original figure functions, switch output to SVG and add an external-workspace CLI; extraction provenance is recorded.
- `data_processed/<host>/`: baseline controls/software metric, follow-up inference and verified records, final inference and all additional attempt metadata. `baseline-`, `followup-`, and `final-` identify the three correct rounds, not the deleted experiment.
- `data_processed/all_machines/`: shared statistics, final data tables, build/coverage/blind-boundary checks, archive/import manifests and curation verification.
- `plots/`: Phase-I evidence includes 302 selected SVG figures and their provenance JSON. Capacity figures use `plots/capacity/<host>/`; later-phase plots are also available in their respective packages.
- `scripts/`: external archive restore, integrity checks, representative raw verification, and final CSV export. These do not acquire data automatically.
- `main_code/pmu/`: Phase-II counter collection, capacity-boundary correlation, and cross-machine aggregation code.
- `data_raw/<host>/pmu/`: Phase-II measurements, summaries, and logs; these directories are populated.
- `data_processed/eight_counter_cross_machine/`: combined and workload-specific counter comparison tables.
- `estimator_validation/`: matched software-only estimator / PMU comparison, source, verified summaries, and archive locations.
- `phase3/`: Hazel source and Slurm snapshots, verified evidence, predictions, published comparisons, and plots.
- `competition/`: fixed parameters, timing-only entry points, scorecard, and freeze/verification manifests.
- `report/`, `slides/`, `hpc_slurm/`, and other unused directories: retained placeholder structure. Hazel Slurm scripts are in the Phase-III package; the competition runner is `competition/run.slurm`.

[import-manifest.json](data_processed/all_machines/import-manifest.json) maps every imported file's original path to its curated destination and SHA-256. Paths inside immutable CSV/JSON/provenance remain **original archive-relative identifiers**. They are not broken relative links to be silently rewritten. Resolve them with:

```bash
python3 scripts/verify_phase1_import.py --resolve data_processed/followup/latency-classes.csv
```

If a path is not copied, resolve it in the restored archive overlay. Absolute paths embedded in original command logs describe the producing environment. The follow-up metadata audit explicitly resolves historical conflict-smoke aliases without rewriting records. [curation-reference-checks.json](data_processed/all_machines/curation-reference-checks.json) records the reference audit.

## Check the Phase-I curated copy

From the clone root, with Python 3.9+:

```bash
python3 scripts/verify_phase1_import.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts -p 'test_*.py' -v
```

To test the C/analysis toolkit without creating build files in the curated copy:

```bash
TOOLKIT_TEST=$(mktemp -d)
cp -a main_code/common/phase1/. "$TOOLKIT_TEST/"
make -C "$TOOLKIT_TEST" test
```

The native build needs GCC, GNU make and binutils (`objdump`). No plot packages are needed for these tests. For analysis plots, install `main_code/common/phase1/requirements-analysis.txt` into a separate virtual environment. Set `MPLCONFIGDIR` to a writable external directory on the lab servers.

## Selected raw evidence and external archives

The repository includes compact, report-supporting subsets under [`data_raw/phase1_timing_selected/`](data_raw/phase1_timing_selected/) and [`data_raw/phase3_timing_selected/`](data_raw/phase3_timing_selected/). Their manifests preserve the selection rule, complete one-million-sample arrays, run parameters, statistics, quality status and file hashes. Verify both subsets with:

```bash
python3 scripts/verify_selected_raw.py data_raw/phase1_timing_selected
python3 scripts/verify_selected_raw.py data_raw/phase3_timing_selected
```

The full evidence archives intentionally remain outside Git. They retain all raw distributions, alternate/unsuccessful attempts, source snapshots, compiler/environment records, command logs, address lists and idle observations, including material not selected for the compact Git subsets. Keep all three Phase-I archives available when moving the repository: the two listed below and the independent-load archive documented above. Cloning Git alone does not retrieve the exhaustive raw evidence. Phase-II estimator archives and Hazel timing data have separate inventories in [estimator_validation/README.md](estimator_validation/README.md) and [phase3/README.md](phase3/README.md).

The server currently stores them under `/gpfs_common/share03/rotenberg/hlee58/ECE592_proj1/artifacts/`:

| Archive | Bytes | SHA-256 |
|---|---:|---|
| `phase1-revised.zip` | 6924281580 | `66556285f9ed2d1af478deaf5a1c151cc69cb5f1f7018a57df9423dc25ac75c2` |
| `phase1-uncertainty.zip` | 2372753088 | `505f021d63a55feec38871be601aa0a9c7d80a8dc8a447fef3716dec515c555d` |

Use the actual location of those two files as `ARCHIVE_DIR`. Choose a new, empty directory outside both repositories as `EVIDENCE_WORKSPACE`; allow at least 20 GB for extraction, plus analysis output space. The helper verifies sizes, complete archive SHA-256 values and safe member paths before extraction. It restores the revised archive first, then the supplement, whose overlapping paths intentionally take precedence. It refuses nonempty destinations and symlink-containing destination paths; use `realpath` to resolve lab mount aliases. Interrupted extraction is marked incomplete; use a fresh destination for another restore.

```bash
ARCHIVE_DIR=/gpfs_common/share03/rotenberg/hlee58/ECE592_proj1/artifacts
EVIDENCE_WORKSPACE=/absolute/canonical/path/to/new-empty-workspace
python3 scripts/restore_phase1.py --archive-dir "$ARCHIVE_DIR" --check-only
python3 scripts/restore_phase1.py --archive-dir "$ARCHIVE_DIR" --workspace "$EVIDENCE_WORKSPACE"
python3 scripts/verify_restored_samples.py --workspace "$EVIDENCE_WORKSPACE" --output /tmp/phase1-raw-checks.json
python3 scripts/export_phase1_tables.py --workspace "$EVIDENCE_WORKSPACE" --output-dir /tmp/phase1-tables
```

The archives preserve their original experiment layout, including historical documents externally. Nothing in this restore imports report or slide files into the curated clone. No new raw distributions are acquired by these commands.

## Recompute Phase I from existing evidence

Run analysis only in the external restored workspace. To use the exact final toolkit retained here, copy its source, config and test directories over the corresponding restored directories first; this updates analysis implementation, not producing-source snapshots inside `machines/`. The import manifest and release validation record distinguish these from historical producing versions. Keep `CLONE_ROOT` set to the clone's absolute path before changing directories.

```bash
CLONE_ROOT="$PWD"
cp -a "$CLONE_ROOT/main_code/common/phase1/src" "$EVIDENCE_WORKSPACE/"
cp -a "$CLONE_ROOT/main_code/common/phase1/config" "$EVIDENCE_WORKSPACE/"
cp -a "$CLONE_ROOT/main_code/common/phase1/tests" "$EVIDENCE_WORKSPACE/"
cp -a "$CLONE_ROOT/main_code/common/phase1/scripts/." "$EVIDENCE_WORKSPACE/scripts/"
cp "$CLONE_ROOT/main_code/common/phase1/Makefile" "$EVIDENCE_WORKSPACE/Makefile"
cd "$EVIDENCE_WORKSPACE"
python3 scripts/analyze.py --final
python3 scripts/check_builds.py
python3 scripts/analyze_followup.py --final
python3 scripts/check_followup_metadata.py
python3 scripts/analyze_uncertainty.py --final
python3 "$CLONE_ROOT/main_code/common/phase1/scripts/plot_followup.py" --workspace "$EVIDENCE_WORKSPACE"
python3 "$CLONE_ROOT/main_code/common/phase1/scripts/plot_uncertainty.py" --workspace "$EVIDENCE_WORKSPACE"
python3 "$CLONE_ROOT/scripts/export_phase1_tables.py" --workspace "$EVIDENCE_WORKSPACE" --output-dir "$EVIDENCE_WORKSPACE/data_processed/final-tables"
```

Full raw recomputation can be lengthy. The baseline analysis also writes its historical inference-summary Markdown and additional plot formats in the external workspace; it does not change the curated clone. The two retained plotting-only modules produce SVG evidence without report/slide generation. Regenerated image bytes can vary with SVG metadata and plotting-library versions; data statistics, provenance and qualifications are the reproducibility targets.

## Repeat the Phase-I measurements

The commands below reproduce the recorded Phase-I workflow. They require SSH access to the eight configured `.ece.ncsu.edu` hosts and should run from a separate working copy of the toolkit. Baseline, follow-up and additional stages are resumable, with source/coverage gates and all retries retained. No reservations are assumed; workers wait for qualifying idle cores. Do not start a second controller over an active run. The frozen follow-up and additional plans were derived from this experiment's timing evidence and are intended to reproduce these machines' experiment, not to serve as hardware specifications.

```bash
make test
python3 scripts/phase1.py access
python3 scripts/phase1.py smoke
python3 scripts/phase1.py full
python3 scripts/phase1.py controls
python3 scripts/check_builds.py
python3 scripts/analyze.py --final
python3 scripts/followup.py smoke spatial capacity confirm conflict cross l2 l2confirm
python3 scripts/analyze_followup.py --final
python3 scripts/check_followup_metadata.py
python3 scripts/uncertainty.py access
python3 scripts/uncertainty.py smoke controls
python3 scripts/uncertainty.py conflict capacity spatial
python3 scripts/uncertainty.py repair_smoke repair --hosts crux thunderbird
python3 scripts/uncertainty.py capacity_repair --hosts sunbird charnwood crux upgrade
python3 scripts/analyze_uncertainty.py --final
```

Use `--hosts` on the acquisition controllers to resume an individual machine; repeat an interrupted stage after its controller has stopped. Raw data and completion markers decide what remains. The archived full verification and the curation checks separate successful measurement collection from unresolved physical interpretation. Do not consult PMUs, cache-reporting interfaces or published cache specifications during Phase I. The optional original `audit.py` expects the original project PDF in an external experiment root (the archives supply it). The separate Phase-II workflow is under `main_code/pmu/` and `estimator_validation/`.
