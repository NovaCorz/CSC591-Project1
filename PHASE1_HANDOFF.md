# Phase-I handoff

Start from the annotated `phase1-timing-only` tag. It preserves the acquired timing-only results and their limitations; it is not a claim that every experimental requirement was satisfied. `phase1-freeze.json` identifies the separately maintained report, specification and raw archives by size and SHA-256.

## Start Phase II

1. Read the repository README and the separately supplied report, especially Table IV (inferences), Table VIII (coverage), Section IV-G (inclusion) and Section IV-F (latency). Architecture/year citations remain for the team to complete.
2. Create a working branch from the frozen checkpoint, for example `git switch -c phase2 phase1-timing-only`. Keep the original Phase-I estimates, raw data and qualification flags unchanged. New timing/control experiments after the freeze must be identified as follow-up work.
3. On each of the eight lab machines, discover the available PMU events and repeat representative capacity, line/stride and associativity workloads with one million workload repetitions per verified point. Preserve the workload, affinity, timer units, compiler options and seeds for comparisons; retain noise and unsuccessful attempts. The suite's idle-core checks remain applicable.
4. Build the required comparison tables: **Timing Inference / PMU Evidence / Published-System Value / Source-Page / Error-Agreement**. Hardware evidence can agree or disagree with the frozen estimate. Do not replace the original estimate with a reference value. Document inaccessible counters and differences in event semantics.
5. Complete the software-estimator comparison against a hardware-derived hit/miss rate, with absolute/relative error. Its fast-classification percentage is not yet a validated hardware hit rate. Complete the separate exactly-eight-event study across the three standardized workloads as specified in Sections 8.4–8.5.
6. Use the lab dataset for chronology and predictions after verification. Account for server/desktop class as well as year and architecture. Freeze lab-only predictions before any Hazel cache experiment; Hazel is held-out evaluation.

## Known experimental limitations

- Inclusion pressure tests did not establish lower-only eviction and ran before the later L2 calibration/confirmation. No post-refinement inclusion repeat is available. Keep the policy uncertain; a follow-up needs residency and eviction controls.
- Dependent timing distributions and candidate L1-like medians are available, but isolated physical L2/LLC hit times and first-access miss penalties are not established. Effective class increments are descriptive measurements.
- Capacity brackets and upper-level ways/sets are conditional inferences. LLC ways, exact sharing domains and inclusion policy remain unresolved. The repeated 64-byte spatial boundary does not independently identify every physical level's line size.
- The independent-load diagnostic is complete: 48/48 qualified pairs demonstrate overlap. It is throughput evidence, not a substitute cache-hit latency.
- Architecture/year citations and contributor attribution remain deferred. The separately supplied report was built before this Git checkpoint, so its freeze TODO is superseded by the tag and this manifest; its scientific values and limitations remain unchanged.

## Files to use

- Shared code/configuration/tests: `main_code/common/phase1/`.
- Per-host evidence: `data_processed/<host>/baseline-inference.json`, `followup-inference.json`, `final-inference.json` and corresponding records. Fields in these files separate experiment families; preserved empty subdirectories do not mean the data are absent.
- Consolidated inferences: `data_processed/all_machines/inferred-cache-table.csv`; latency distributions: `followup-latency-classes.csv` in the same folder.
- Diagnostic: `data_processed/independent-load/` and `plots/independent-load/distributions.svg`.
- Run `python3 scripts/verify_phase1_import.py` after cloning. The repository inventory includes this handoff and the public SSH host keys; no private keys are included.

The report and slides remain outside Git. The current report files are under `/gpfs_common/share03/rotenberg/hlee58/ECE592_proj1/report/`: `HW1_report.pdf` and the complete `phase1-report-source.zip`. Upload the source ZIP as a complete Overleaf project; uploading only `report.tex` omits required tables/figures/listings. The detailed audit is `report/latex-phase1/phase1-requirements-audit.md` in that experiment workspace.

The three full raw archives are in `/gpfs_common/share03/rotenberg/hlee58/ECE592_proj1/artifacts/`: `phase1-revised.zip`, `phase1-uncertainty.zip` and `phase1-independent-load.zip`. Cloning Git does not download them. Arrange access or transfer separately; verify the manifest hashes and follow the README restoration instructions before raw reanalysis. The first two form an ordered overlay; the diagnostic restores separately. The final Moodle submission still needs all required data, report and slides.
