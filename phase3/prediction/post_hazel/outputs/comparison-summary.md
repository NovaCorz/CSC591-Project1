# Frozen predictions evaluated against Hazel

The original ECE-only models and prediction curves are unchanged. This package uses Hazel only for evaluation. Native timing inferences and published information remain separate. The source freeze manifests identify their actual timestamps; this comparison does not establish a pre-execution prediction freeze.

## Reading the comparisons

Errors use prediction minus observation. Capacity point comparisons use the same geometric bracket-midpoint convention as the frozen training dataset; they are not new physical capacity estimates. The original capacity candidates and brackets are retained in the master table. Error bounds use bracket endpoints. Bracket overlap is compatibility, not accurate identification. Latency bars are P5–P95 sample-distribution spans, not confidence intervals on the median. Software bars show threshold sensitivity; they are not hardware hit-rate confidence intervals.

Only Turin (2024) is later than the newest ECE training year (2023). Haswell, Cascade Lake, Ice Lake and Genoa test transfer to unseen machines at years within the training span. Original future dashed curve samples are copied byte-for-byte; historical target predictions appear as plus signs. Solid connections are confined to the same vendor/ISA, avoiding an implied cross-vendor lineage.

## Quantitative comparison

| Metric | Machine | Frozen prediction | Observed point [range] | Absolute error | Interpretation |
|---|---|---:|---:|---:|---|
| l1_capacity (KiB) | haswell | 41.9506 | 33.9411 [32, 36] | 8.00943 | point outside measurement range |
| l1_associativity (ways) | haswell | 8 | 8 [8, 8] | 0 | point within measurement range |
| l1_latency (ns/access) | haswell | 1.51018 | 1.59141 [1.58547, 1.59396] | 0.0812299 | point outside measurement range |
| l2_capacity (KiB) | haswell | 232.091 | 271.529 [256, 288] | 39.4379 | point outside measurement range |
| l2_associativity (ways) | haswell | 8 | 8 [8, 8] | 0 | point within measurement range |
| llc_capacity (MiB) | haswell | 16.9706 | 45.2548 [16, 128] | 28.2843 | point within measurement range |
| line_size (bytes) | haswell | 64 | 64 [64, 64] | 0 | point within measurement range |
| software_metric (%) | haswell | 99.9009 | 89.4925 [3.2065, 99.9946] | 10.4085 | point within measurement range |
| l1_capacity (KiB) | cascadelake | 41.9506 | 33.9411 [32, 36] | 8.00943 | point outside measurement range |
| l1_associativity (ways) | cascadelake | 8 | 8 [8, 8] | 0 | point within measurement range |
| l1_latency (ns/access) | cascadelake | 1.51018 | unresolved | — | unresolved observation |
| l2_capacity (KiB) | cascadelake | 803.971 | unresolved | — | unresolved observation |
| l2_associativity (ways) | cascadelake | 8 | unresolved | — | unresolved observation |
| llc_capacity (MiB) | cascadelake | 16.9706 | unresolved | — | unresolved observation |
| line_size (bytes) | cascadelake | 64 | 64 [64, 64] | 0 | point within measurement range |
| software_metric (%) | cascadelake | 99.9009 | 99.9255 [0.7973, 99.9443] | 0.02455 | point within measurement range |
| l1_capacity (KiB) | icelake_8358 | 41.9506 | 49.96 [48, 52] | 8.00943 | point outside measurement range |
| l1_associativity (ways) | icelake_8358 | 8 | 12 [12, 12] | 4 | point outside measurement range |
| l1_latency (ns/access) | icelake_8358 | 1.51018 | 2.03614 [2.03614, 2.03614] | 0.525963 | point outside measurement range |
| l2_capacity (KiB) | icelake_8358 | 1321.52 | unresolved | — | unresolved observation |
| l2_associativity (ways) | icelake_8358 | 8 | unresolved | — | unresolved observation |
| llc_capacity (MiB) | icelake_8358 | 16.9706 | unresolved | — | unresolved observation |
| line_size (bytes) | icelake_8358 | 64 | 64 [64, 64] | 0 | point within measurement range |
| software_metric (%) | icelake_8358 | 99.9009 | 85.564 [9.3986, 94.2905] | 14.337 | point outside measurement range |
| l1_capacity (KiB) | genoa | 41.9506 | 33.9411 [32, 36] | 8.00943 | point outside measurement range |
| l1_associativity (ways) | genoa | 8 | 8 [8, 8] | 0 | point within measurement range |
| l1_latency (ns/access) | genoa | 1.51018 | 2.11268 [2.09312, 2.11268] | 0.602505 | point outside measurement range |
| l2_capacity (KiB) | genoa | 1694.3 | 1086.12 [1024, 1152] | 608.182 | point outside measurement range |
| l2_associativity (ways) | genoa | 8 | unresolved | — | unresolved observation |
| llc_capacity (MiB) | genoa | 16.9706 | 22.6274 [8, 64] | 5.65685 | point within measurement range |
| line_size (bytes) | genoa | 64 | 64 [64, 64] | 0 | point within measurement range |
| software_metric (%) | genoa | 99.9009 | 98.4675 [47.6465, 99.1322] | 1.43345 | point outside measurement range |
| l1_capacity (KiB) | turin | 41.9506 | 49.96 [48, 52] | 8.00943 | point outside measurement range |
| l1_associativity (ways) | turin | 8 | 12 [12, 12] | 4 | point outside measurement range |
| l1_latency (ns/access) | turin | 1.51018 | 1.25189 [1.25189, 1.27145] | 0.258289 | point outside measurement range |
| l2_capacity (KiB) | turin | 2784.98 | 1086.12 [1024, 1152] | 1698.87 | point outside measurement range |
| l2_associativity (ways) | turin | 8 | unresolved | — | unresolved observation |
| llc_capacity (MiB) | turin | 16.9706 | 45.2548 [32, 64] | 28.2843 | point outside measurement range |
| line_size (bytes) | turin | 64 | 64 [64, 64] | 0 | point within measurement range |
| software_metric (%) | turin | 99.9009 | 99.9696 [89.6577, 99.982] | 0.06865 | point within measurement range |

## Interpretation by quantity

- **Capacity:** L1 remains a small, stepwise structure; the constant model cannot identify the 32 versus 48 KiB choice. The L2 exponential rule describes the four pooled lab servers but must be judged against both measured brackets and the separate published organization. Broad LLC brackets cannot verify a precise constant-capacity forecast. Cascade Lake and Ice Lake deeper capacities are unresolved, so no error is assigned.
- **Associativity:** The eight-way L1 point prediction matches Haswell, Cascade Lake and Genoa, but underpredicts Ice Lake and Turin by four ways (33.33% of the observed value). The empirical training range contains all five. Only Haswell has a supported Hazel L2 way inference; missing values do not count as successes.
- **Latency and penalties:** The four available matched L1-like representatives use recorded empirical timer rates for ns/access. Cascade Lake has no qualifying stride64 class row, so substituting its baseline median would change the measurement definition. Neither ns nor TSC ticks are asserted to be core cycles. Physical L2/LLC hit latencies and incremental cache/memory penalties remain unsupported; empirical class statistics are supplied separately without physical labels. The data do not support a general monotonically increasing latency law.
- **Line size and inclusion:** All five Hazel timing boundaries equal the 64-byte prediction. This supports the scoped spatial-granularity law, not an independently measured line size for every level. All inclusion classifications remain uncertain and are not counted as successful categorical predictions.
- **Residency proxy:** All thirteen machines use the same 1 MiB standardized workload. Point errors can be large even though threshold-sensitivity ranges overlap. This demonstrates sensitivity to classifier calibration and workload residence; it does not establish a hardware hit-rate trend.
- **Cross-architecture and platform effects:** The frozen server model pools Intel, AMD and Arm; it is not an AMD-specific law. The small sample cannot separate year, ISA, server/desktop class, chiplet topology, frequency, and memory-platform effects. The figures retain desktop observations but the frozen forecasts use the selected lab-server subset.

## Published verification

See `prediction-timing-published.csv` for the three-way comparison, source locators, and scope qualifications. Manufacturer MB/KB cache labels are represented as binary MiB/KiB. Intel socket LLCs and AMD per-CCD LLCs are compared conditionally with the effective domain observed by a pinned core. The AMD 384 MiB package sum is never substituted for a 32 MiB CCD domain. `llc-domain-normalization.csv` provides explicitly conditional MiB/core normalization. Missing published latencies/ways are left unestablished; generic core latency claims are not used as SKU-specific nanosecond targets.

The closest well-defined prediction is the 64-byte spatial boundary. The L1 way prediction misses the two twelve-way cores. Hardware capacity agreement can be checked where the timing brackets exist; wide LLC containment provides weak evidence. Architecture and sharing-domain differences are plausible explanations, not experimentally isolated causes.

## Requirements and remaining unsupported work

The fifteen required chronological plot categories are tracked in `requirements-status.csv`. Unsupported physical quantities have explicitly labeled panels instead of invented values. Two comparable PMU trend series require the partner’s Phase-II data. No PMU collection or ECE hardware verification is performed here. Report/slides integration is separate from these analysis outputs.

## Sources

- **intel3**: [Intel third-generation Xeon Scalable overview](https://www.intel.com/content/www/us/en/developer/articles/technical/third-generation-xeon-scalable-family-overview.html), Table 1. Cascade Lake: L1D 32 KiB, private L2 1 MiB, 14 nm. Ice Lake-SP: L1D 48 KiB, private L2 1.25 MiB, 10 nm.
- **haswellsku**: [Intel Xeon E5 v3 family product table](https://www.intel.com/content/www/us/en/ark/products/series/78583/intel-xeon-processor-e5-v3-family.html), E5-2650 v3 row. 10 cores, 25 MB Smart Cache, Q3 2014.
- **cascadesku**: [Intel Xeon Gold 6226R specifications](https://www.intel.com/content/www/us/en/products/sku/199347/intel-xeon-gold-6226r-processor-22m-cache-2-90-ghz/specifications.html), Essentials and CPU Specifications. 16 cores, 22 MB cache; SKU launch 2020 differs from generation year 2019.
- **icesku**: [Intel Ice Lake product table](https://www.intel.com/content/www/us/en/ark/products/codename/74979/products-formerly-ice-lake.html), Xeon Platinum 8358 row. 32 cores, 48 MB cache, Q2 2021.
- **intelcache**: [Intel cache hierarchy changes](https://www.intel.com/content/www/us/en/support/articles/000027820/processors/intel-xeon-processors.html), Resolution. Prior E5 architectures use inclusive shared LLC; Xeon Scalable shifts to non-inclusive LLC.
- **fog**: [Agner Fog, The microarchitecture of Intel, AMD, and VIA CPUs](https://www.agner.org/optimize/microarchitecture.pdf), 2026-05-23 edition: Tables 10.2 (p147), 11.2 (p160), 12.3 (p169), 25.1 (p258); generic core references only. Haswell core L1D 32 KiB/8 ways/64 B; L2 256 KiB/8 ways/64 B. Ice Lake core L1D 48 KiB/12 ways/64 B. Generic core reference; client LLC figures are not used for Xeon.
- **intelopt**: [Intel Optimization Reference Manual Volume 1](https://cdrdv2-public.intel.com/814198/248966-Optimization-Reference-Manual-V1-049.pdf), section 2.5.1.1. Skylake-server lineage private L2: 1 MiB, 16 ways, 64-byte line; applied to Cascade Lake with Intel generation-overview capacity corroboration.
- **genoa**: [AMD EPYC 9004 BIOS and Workload Tuning Guide](https://docs.amd.com/api/khub/documents/goX~9ubv8i5r60A_Qrp3Rw/content), 58011 rev1.4, sections 2.5–2.8, printed pp4–6 (PDF pp10–12). Genoa: 5nm cores, L1D 32 KiB/8 ways; private L2 1 MiB; all line sizes 64 B. Eight cores share 32 MiB L3 in a non-X Genoa CCD.
- **genoasku**: [AMD EPYC 9654 specifications](https://www.amd.com/en/products/processors/server/epyc/4th-generation-9004-and-8004-series/amd-epyc-9654.html), General Specifications. 96 cores, package L3 384 MB, launch 2022-11-10.
- **turin**: [AMD fifth-generation EPYC architecture white paper](https://docs.amd.com/api/khub/documents/UIqhAbjRhgnzgzzdVU4pUw/content), 70353 revB; printed pp6,8 (PDF pp6,8). Zen5: 48 KiB L1D, 1 MiB L2 per core, 32 MiB L3 shared by eight cores in a CCD. Core dies use 4 nm; I/O die uses 6 nm (as in Genoa); printed p5.
- **turinsku**: [AMD EPYC 9655 specifications](https://www.amd.com/en/products/processors/server/epyc/9005-series/amd-epyc-9655.html), General Specifications. 96 cores, package L3 384 MB, launch 2024-10-10.
- **zen5slides**: [AMD Zen5 Architecture Deep Dive, Tech Day 2024 (AMD-authored slides, mirrored)](https://www.slideshare.net/slideshow/amd-zen-5-architecture-deep-dive-from-tech-day/270466492), slides 13–14. Zen4 L1D 32 KiB/8 ways and L2 1 MiB/8 ways; Zen5 L1D 48 KiB/12 ways and L2 1 MiB/16 ways. Zen5 complex L3 32 MiB/16 ways, filled from L2 victims. Core-level evidence, not a SKU latency guarantee.
- **haswellinclusive**: [Intel, Enabling NFV to Deliver on its Promise](https://www.intel.com/content/dam/www/public/us/en/documents/solution-briefs/nfv-packet-processing-brief.pdf), E5-2600 v3 cache hierarchy diagram (Inclusive Shared L3 Cache). E5-2600 v3 has an inclusive shared L3 cache.
