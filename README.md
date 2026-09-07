# CSC591 Project 1 — selected timing-only capacity data

Repository: https://github.com/NovaCorz/CSC591-Project1

This checkout contains the **eight selected main sweep/follow-up sets**. It is
not a completed project or a Phase I freeze; some cache estimates remain uncertain.
See [capacity findings](report/capacity/CAPACITY_FINDINGS.md) and the
[work log](report/capacity/WORK_LOG.md).

## Included datasets

| Machines | Original campaign retained |
| --- | --- |
| Sunbird, Thunderbird, Skylark, Artemisia, Charnwood, Ookay, Upgrade | `capacity-20260906/<host>` |
| Crux, CPU 2 only | `crux-new-core-20260906T235055Z/crux` |

Each set includes `full`, `refine-small`, `refine-middle`, and `refine-large`, plus
the associated native source/build/disassembly, environment, run-command, placement
and activity records. Total: **918 distributions, each with 1,000,000 samples**
(280 coarse + 638 refinement). Both traversal modes and empty controls are kept.
No retained timing samples, outliers or inconsistent points were removed.

| Directory | Contents |
| --- | --- |
| `main_code/common/` | Portable x86-64/AArch64 C source and retained run snapshots |
| `scripts/` | Collectors, analyses, tests, plans and restoration helper |
| `data_raw/<host>/capacity/` | Selected `.bin.gz` raw files and provenance |
| `data_processed/<host>/capacity/` | Selected run statistics |
| `data_processed/all_machines/capacity/` | Selected eight-machine comparisons |
| `plots/capacity/` | Selected curves, box plots, and cross-run figures |
| `report/capacity/` | Current findings/guides and historical work records |

The architecture directories reference the shared main C source; native branches
must both appear in the final report listing. Other experiment folders remain
placeholders, not completed work.

## Excluded from this checkout, preserved separately

At the user's request, copied pilots/short tests, the old Crux CPU 0 campaign and
additional three-repeat diagnostics were removed, including their dataset-specific
plots, summaries, snapshots and logs. Their originals remain unchanged in
`/mnt/ncsudrive/h/hlee58/ECE592_proj1`. The
[exclusion manifest](data_processed/capacity_excluded_manifest.json) records exact
original/packaged paths, checksums and the recovery-copy location. Those records
are not restoration inputs. Historical diagnostic code and work-log entries are
retained for traceability but their excluded inputs are not in this checkout.

**Spec §12 still requires all collected data for the final handoff.** This selected
checkout alone is not the complete Moodle data submission. Supply the preserved
excluded data separately in the final package or arrange an approved alternate
handoff. This selection is organizational, not evidence that excluded results
were scientifically invalid or that the kept results are confirmed capacities.
At the user's request, the two unpublished import commits were replaced with a
selected-only commit. Excluded dataset artifacts are not in the new main-branch
history. Raw archives were never tracked by Git.

## Restore and reproduce

[The active manifest](data_processed/capacity_file_manifest.json) maps only the
retained files to their original relative layout and decoded SHA-256 checksums.
Original absolute paths in archived metadata record historical commands, not
paths to execute blindly in another checkout. Raw gzip archives remain locally
present and Git-ignored, as the spec permits; a fresh GitHub clone alone lacks them.

```bash
python3 scripts/restore_capacity_workspace.py /tmp/capacity-selected-workspace
cd /tmp/capacity-selected-workspace
python3 -m venv .venv
.venv/bin/python -m pip install numpy matplotlib
.venv/bin/python capacity_overview.py
.venv/bin/python capacity_refinement_analysis.py
```

Restoration needs a new destination and roughly 7.4 GB for decoded timing data.
It verifies all retained file checksums, requires no excluded dataset, and does
not launch benchmarks. To regenerate every selected run's statistics from raw:

```bash
for host in sunbird thunderbird skylark artemisia charnwood crux ookay upgrade; do
    run_dir="results/capacity-20260906/$host"
    if [ "$host" = crux ]; then
        run_dir="results/crux-new-core-20260906T235055Z/crux"
    fi
    for group in full refine-small refine-middle refine-large; do
        .venv/bin/python capacity.py plot "$run_dir/$group" || exit 1
    done
done
.venv/bin/python capacity_overview.py
.venv/bin/python capacity_refinement_analysis.py
```

Do not run the historical diagnostic comparison on this selected-only restore;
its additional datasets are intentionally absent. Do not use the historical
import-all packager on this checkout. For new experiments, use the methodology
guide with a new output directory and native builds on authorized ECE hosts.
Never execute old absolute-path commands blindly, overwrite retained runs, or
run these benchmarks on Hazel during Phase I.

## Limitations and unfinished requirements

Timing-only dependent chains, warmup, `-O0`, CPU pinning, first-touch placement,
recorded distributions and sequential controls are preserved. No PMU/cache-spec
lookup, Hazel run, overhead subtraction or Phase I freeze has occurred. No quiet
reservation was obtained; short preflight screens do not establish isolation.
Do not force exact middle/large cache sizes where the data are ambiguous.

Line size, associativity, controlled latency, inclusion, software-only metric,
later phases, frozen predictions, final report/slides/diagrams, student attribution
and final data handoff remain unfinished. Student Table 1/hypotheses were reported
complete but their files were not present to import. Overleaf URL and TA/instructor
access must be supplied/verified by the team. GitHub contribution attribution
depends on using a verified account email; no author identity is invented here.

AI assistance: OpenAI Codex helped implement, run, analyze and document the
timing-only experiments and organize this checkout. Students must review and
understand the work, accurately disclose assistance, and provide actual contributor
labels. No final student-authored report or contribution history is fabricated.
