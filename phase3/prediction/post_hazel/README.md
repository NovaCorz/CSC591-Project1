# Hazel evaluation of the unchanged ECE-only predictions

This directory contains post-measurement analysis only. It does not run benchmarks or refit predictions. The original inputs remain in `../pre_hazel/outputs` and `/share/ece592f26/hlee58/tmp/hazel-phase3-20260911`.

Submit from the repository root:

```bash
sbatch --output=prediction/post_hazel/logs/compare.%j.stdout \
       --error=prediction/post_hazel/logs/compare.%j.stderr \
       prediction/post_hazel/run.slurm
```

The job requests one CPU, 3 GiB, and 20 minutes, runs a data-validation smoke first, then writes a separate `results-JOBID` directory. It needs the existing Python/matplotlib environment. Never run the builder on a login node. The job checks the original prediction manifest, the Hazel timing freeze, and the frozen raw-record inventory before using selected latency summaries. Raw timing arrays are not reprocessed.

Key outputs:

- `comparison-summary.md`: interpretation and citations.
- `chronological-master.csv`: all eight ECE and five Hazel systems, ordered by generation introduction year; original inferences remain separate from published values.
- `prediction-errors.csv`: point errors, bracket-relative error bounds, overlap checks, and unresolved quantities.
- `prediction-timing-published.csv`: prediction, timing inference, published value, source URL/locator, and domain qualification.
- `llc-domain-normalization.csv`: explicitly conditional domain normalization, separate from original observations.
- `team-laws-and-future.md`: evaluation of the unchanged two laws and the already prepared 2029 forecast.
- `plots/`: PDF, SVG and PNG figures; `required-chronological-plots.pdf` covers supported and explicitly unsupported categories.
- `requirements-status.csv`: all fifteen required plot categories, including the Phase-II PMU dependency.
- `frozen-inputs/`: unchanged prediction table, parameters, future forecast and dashed-curve samples.
- `input-manifest.json`, `output-manifest.json`, `provenance.json`, `validation.json`: audit and verification.

Capacity midpoint values are geometric summaries of the original brackets, matching the training convention. They are not replacement physical inferences. Errors against those midpoints are accompanied by bracket bounds. Timing quantiles and software threshold-sensitivity ranges have different meanings and are not labeled as statistical confidence intervals. The L2 model's interval is the original heuristic 95% interval.

No ECE Phase-II data are used. Published information is confined to Hazel comparison and domain annotation. Report/slides are not changed. The prior request's excluded Hazel generations remain outside this selected five-generation analysis.

Job 817282 failed the provenance lookup before analysis: latency run hashes belong to the frozen raw-record inventory, not the top-level file manifest. A cancellation was requested after it was observed pending, but accounting confirms it had already executed and failed. Job 817284 passed the data smoke, then failed rendering because the plotting package path was missing. The job script now reuses the existing Hazel plotting packages and checks the import first. Logs and partial outputs are retained. No experiment or frozen input was changed.

## Verified final package

Use [latest/comparison-summary.md](latest/comparison-summary.md), pointing to `results-817293`. Job **817293** completed both generation and the independent audit. The audit verified 78 output hashes, 31 quantitative comparisons, 13 chronological rows, the unchanged frozen curves, and all 15 pages of the required-category PDF. See `audit-results-817293.json` and `final-job.json`. The `final.slurm` script runs the final builder and audit; `run.slurm` additionally performs a separate data smoke. Earlier versions and failed attempts remain for traceability.
