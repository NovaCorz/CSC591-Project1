# Quantitative Hazel predictions

All values below were computed from the four ECE lab servers only. Brackets on constant models are empirical server envelopes; L2 brackets are heuristic 95% model prediction intervals. `U` means the verified Phase-I observations do not support a quantitative prediction.

| Constraint | Year | L1-like KiB | L1 ways | L1-like ns/access | L2-like KiB | L2 ways | LLC-like MiB | Boundary | Inclusion | Software metric |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| haswell | 2014 | 41.95 [32, 72] | 8 [4, 12] | 1.510 [1.272, 2.625] | 232.1 [80.7, 667.2] | 8 [8, 16] | 16.97 [8, 32] | 64 B | uncertain | 99.9009% [0.7233, 99.9988] |
| broadwell | 2016 | 41.95 [32, 72] | 8 [4, 12] | 1.510 [1.272, 2.625] | 381.5 [145.4, 1000.8] | 8 [8, 16] | 16.97 [8, 32] | 64 B | uncertain | 99.9009% [0.7233, 99.9988] |
| skylake | 2017 | 41.95 [32, 72] | 8 [4, 12] | 1.510 [1.272, 2.625] | 489.1 [194.0, 1233.1] | 8 [8, 16] | 16.97 [8, 32] | 64 B | uncertain | 99.9009% [0.7233, 99.9988] |
| cascadelake | 2019 | 41.95 [32, 72] | 8 [4, 12] | 1.510 [1.272, 2.625] | 804.0 [340.2, 1899.9] | 8 [8, 16] | 16.97 [8, 32] | 64 B | uncertain | 99.9009% [0.7233, 99.9988] |
| icelake_6326 | 2021 | 41.95 [32, 72] | 8 [4, 12] | 1.510 [1.272, 2.625] | 1321.5 [582.8, 2996.7] | 8 [8, 16] | 16.97 [8, 32] | 64 B | uncertain | 99.9009% [0.7233, 99.9988] |
| icelake_8358 | 2021 | 41.95 [32, 72] | 8 [4, 12] | 1.510 [1.272, 2.625] | 1321.5 [582.8, 2996.7] | 8 [8, 16] | 16.97 [8, 32] | 64 B | uncertain | 99.9009% [0.7233, 99.9988] |
| sapphirerapids | 2023 | 41.95 [32, 72] | 8 [4, 12] | 1.510 [1.272, 2.625] | 2172.2 [971.7, 4856.1] | 8 [8, 16] | 16.97 [8, 32] | 64 B | uncertain | 99.9009% [0.7233, 99.9988] |
| genoa | 2022 | 41.95 [32, 72] | 8 [4, 12] | 1.510 [1.272, 2.625] | 1694.3 [755.2, 3801.3] | 8 [8, 16] | 16.97 [8, 32] | 64 B | uncertain | 99.9009% [0.7233, 99.9988] |
| turin | 2024 | 41.95 [32, 72] | 8 [4, 12] | 1.510 [1.272, 2.625] | 2785.0 [1241.3, 6248.3] | 8 [8, 16] | 16.97 [8, 32] | 64 B | uncertain | 99.9009% [0.7233, 99.9988] |

For every target, physical L1 miss penalty, L2/LLC hit latency, L2/LLC miss penalty, LLC associativity, exact LLC sharing normalization, and PMU metrics are `U`. The hierarchy prediction is limited to at least three cache-like timing classes plus a memory-like class; exact physical level count is `U`.
