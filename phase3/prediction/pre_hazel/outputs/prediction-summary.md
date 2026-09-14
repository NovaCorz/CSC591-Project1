# Lab-only Hazel prediction summary

No Hazel measurements were used or accessed.

## Selected models

- **L2-like effective capacity:** server-only anchored log-linear model, 0.358491 log2(KiB)/year, doubling time 2.79 years, anchored R² 0.925. The 95% model intervals are intentionally wide.
- **L1-like capacity:** constant server median 41.951 KiB; observed server envelope 32--72 KiB.
- **L1 conditional associativity:** constant server median 8 ways; observed range 4--12.
- **L1-like dependent latency:** constant server median 1.510 ns/access; observed server medians 1.272--2.625 ns/access. Per-run empirical timer calibration provides the conversion.
- **L2 conditional associativity:** constant server median 8 ways; observed supported range 8--16.
- **LLC-like effective capacity:** constant server median 16.971 MiB; observed bracket envelope 8--32 MiB. Exact sharing normalization is unavailable.
- **Smallest visible spatial boundary:** constant 64 bytes on all eight lab systems.
- **Software timing metric:** constant server median 99.9009%; threshold-sensitivity envelope 0.7233--99.9988%. It is not a hardware hit rate.
- **Inclusion/exclusion:** uncertain for every target because all eight lab classifications remain uncertain.

## Unsupported quantitative predictions

- exact physical cache-level count
- physical L1 miss penalty
- physical L2 hit latency
- physical L2 miss penalty
- physical LLC hit latency
- LLC-to-memory miss penalty
- LLC associativity/effective bound
- LLC sharing-normalized capacity
- resolved inclusion/exclusion class
- PMU-derived metrics

See `hazel-predictions.csv` for every target and `model-parameters.json` for exact equations and uncertainty construction.
