# Lab-only Hazel prediction artifact

This directory builds the chronological ECE dataset, model audit, Hazel prediction table, vector plots, and two scoped Kuethe--Lee cache laws. The builder has an explicit Phase-I input allowlist and does not scan or read the Hazel workspace. No Hazel measurements were used or accessed.

## Rebuild

On the repository login node, this is lightweight analysis of eight summary rows:

```bash
module load gnuplot/5.4.10
python3 prediction/pre_hazel/build.py
```

For a dependency-free data/model validation without rendering PDFs:

```bash
python3 prediction/pre_hazel/build.py --output /tmp/pre-hazel-smoke --no-plots --timestamp 2000-01-01T00:00:00+00:00
```

Do not point the builder at a Hazel directory. To compare later, read `outputs/hazel-predictions.csv` as immutable input and join it to separately processed Hazel observations by `constraint`; never rerun or refit this builder with Hazel measurements.

Key outputs:

- `outputs/lab-only-chronological-master.csv`: one row per ECE machine, including unsupported fields explicitly;
- `outputs/hazel-predictions.csv` and `outputs/hazel-predictions.md`: frozen-form prediction rows for every specification target;
- `outputs/model-parameters.json` and `outputs/model-comparison.csv`: exact models and selection evidence;
- `outputs/required-plot-status.csv`: all 15 specification plot requirements and current support status;
- `outputs/plots/chronological-supported.pdf`: supported/qualified chronological panels;
- `outputs/plots/team-law-predictions.pdf` and `outputs/team-cache-laws.md`: the two laws and future projections;
- `outputs/input-manifest.json`: exact Phase-I input hashes; and
- `outputs/freeze-manifest.json`: output hashes, timestamp, Git state, and data-isolation statement; and
- `outputs/validation.json`: row-count, sample-count, model-selection, input-isolation, and figure checks.
