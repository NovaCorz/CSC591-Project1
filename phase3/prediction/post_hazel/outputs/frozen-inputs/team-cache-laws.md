# Kuethe--Lee lab-only cache laws

These are scoped empirical summaries, not universal hardware laws. They use no Hazel measurements.

## Kuethe--Lee L2 Capacity Law

**Statement.** Across the four ECE lab servers from 2014--2023, the midpoint of the timing-derived L2-like capacity bracket approximately doubles every **2.79 years**.

**Rule.** `log2(C_KiB) = log2(2172.232032) + 0.358490566*(year-2023)`.

**Evidence.** Four lab servers (Sunbird, Skylark, Thunderbird, Artemisia), spanning Intel x86, AMD x86, and Arm/AArch64. The anchored fit has R^2=0.925; unanchored leave-one-out RMSE is 0.682 log2 KiB versus 1.491 for a constant model. The fit uses geometric midpoints of operational timing brackets.

**Limits.** The sample is small and pooled across vendors. Timing classes do not establish physical L2 identity independently, and SKU, server topology, cache sharing, and design goals are omitted. Growth cannot continue indefinitely: SRAM area and leakage, access energy, wire delay, banking/interconnect cost, and the latency cost of a larger structure can force flattening or a piecewise design. These data do not locate a numerical wall.

## Kuethe--Lee Spatial Granularity Law

**Statement.** The smallest timing-visible spatial boundary is **64 bytes** on all eight ECE systems from 2014--2023, so the frozen Hazel prediction is 64 bytes for every target generation.

**Rule.** `B(year) = 64 bytes`; observed empirical range 64--64 bytes (eight machines).

**Scope choice and limits.** This is the behavior law because the verified data do not support physical L2/LLC hit or miss-cost laws. It describes the shared timing-visible boundary, not an independently isolated physical line size for every cache level. Sectoring, heterogeneous structures, transfer-size changes, or a benchmark that exposes a smaller/larger boundary could weaken it. The constant may remain a design convention rather than a physics law; the data provide no date for a future change.

## Frozen future values

- 2028 L2-like point: 7.348 MiB; heuristic 95% model interval 3.019--17.889 MiB. Spatial boundary: 64 bytes.
- 2029 L2-like point: 9.421 MiB; heuristic 95% model interval 3.737--23.752 MiB. Spatial boundary: 64 bytes.
