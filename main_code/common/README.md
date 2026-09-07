# Portable timing-only capacity implementation

`cache_capacity.c` contains both the x86-64 and AArch64 timer and dependent-load
paths, selected at native compilation. This is shared main code, not a cache-spec
lookup. Both architecture-specific paths must appear in the final report listing.

`snapshots/` preserves the exact source/collector copies saved with earlier runs.
Native binaries, disassembly, build commands and environment records are under
`data_raw/<host>/capacity/<campaign>/`. Use the root file manifest to locate them.
See the repository README for restoration and reproduction; Phase I is not frozen.
