# Kuethe–Lee laws: Hazel evaluation and future scaling

The equations, fitted observations, and parameters are unchanged from `frozen-inputs/team-cache-laws.md` and `model-parameters.json`. No Hazel observation was used to refit either law.

## Kuethe–Lee L2 Capacity Law

Frozen rule: log2(C_KiB) = log2(2172.232032) + 0.358490566 × (year − 2023). The four pooled ECE servers span 2014–2023; the reported doubling time is 2.79 years and anchored R² is 0.925. The response is a timing-bracket midpoint, not independently identified physical L2.

| Hazel target | Predicted KiB | Timing bracket KiB | Point inside bracket? |
|---|---:|---:|---|
| haswell | 232.091 | 256–288 | False |
| cascadelake | 803.971 | None–None | unresolved |
| icelake_8358 | 1321.52 | None–None | unresolved |
| genoa | 1694.3 | 1024–1152 | False |
| turin | 2784.98 | 1024–1152 | False |

The Haswell prediction falls below its narrow timing bracket, while Genoa is overpredicted; their heuristic model intervals still overlap their timing brackets. Turin is overpredicted by 156.42% relative to the bracket midpoint, and its timing bracket does not overlap the frozen heuristic 95% prediction interval. This fails the model’s 2024 future-year test. Cascade Lake and Ice Lake cannot test L2 accuracy with the frozen unresolved timing evidence. This weakens the exponential rule as a transferable prediction; it does not invalidate the original four-point descriptive fit.

Scaling cannot continue indefinitely. SRAM area, leakage, access energy, wire delay, and banking/interconnect overhead constrain capacity. Device density and wire delay are technology limits; die-area budgets, SKU segmentation and acceptable hit latency are design/economic choices. A stepwise or piecewise rule is more plausible than indefinite exponential growth. These observations do not locate a numerical wall or its year.

## Kuethe–Lee Spatial Granularity Law

Frozen rule: B(year) = 64 bytes. Eight ECE machines from 2014–2023 support the original constant behavior rule; all five Hazel boundaries match exactly, including 2024 Turin. The Hazel evidence supports this scoped rule. An observed range of 64–64 is not a probabilistic guarantee outside the sample.

A fixed transfer granularity balances spatial reuse and tag overhead against false sharing, wasted transfers, and bandwidth/energy cost. Interconnect and energy costs impose physical constraints; coherence granularity and compatibility are design choices. Larger vector widths or caches do not force larger lines. The likely continuation is flat or a design-driven step; sectoring or a different access pattern could expose a different boundary. No exact change date is supported. This is the behavior law rather than a latency-cost law because isolated deeper-cache cost measurements are unsupported.

## Five years beyond the newest measured generation

The newest measured generation is Turin (2024), making 2029 the required approximately five-year target. The existing frozen 2029 row therefore meets the horizon without modification. L2-like capacity: **9.421 MiB**, heuristic 95% interval **3.737–23.752 MiB**; visible spatial boundary: **64 bytes**. Exact values are in `frozen-inputs/future-predictions.csv`. The 2028 row is five years beyond the newest lab system and is retained as a separate earlier forecast.

The 2029 values are model-conditional forecasts, not validated hardware claims. Hazel’s failure to follow the L2 point forecast reduces confidence in extrapolating it further. We preserve the original model rather than conceal that weakness by refitting. Future cache partitioning, 3D stacking, chiplet organization, and server design goals may cause large deviations. At least three original lab observations remain on the future figure, with the unchanged dashed continuation.

Compared with Moore’s component-count observation, this dataset is small, heterogeneous and based partly on operational timing brackets. It supports scoped empirical descriptions and a tested constant boundary, not a universal exponential cache law.
