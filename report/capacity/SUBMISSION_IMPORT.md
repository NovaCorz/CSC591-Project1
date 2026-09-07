# Submission repository import — 2026-09-07 UTC

**Superseded in part by the user's dataset selection:** the original full import
described below is historical. This checkout now contains only the eight main
full/refinement sets (918 raw distributions). Pilots, Crux CPU 0 and additional
diagnostics were removed from the checkout, with originals preserved separately.
See the current README, WORK_LOG and exclusion manifest. The original import
commits were subsequently replaced at the user's request with a selected-only
commit. The old commits were unpublished; no force-push was needed. The account
email supplied by the user, `hclee412@gmail.com`, is used for the replacement
commit only, without changing persistent Git configuration.

User authorized copying the work into `/mnt/ncsudrive/h/hlee58/CSC591-Project1`
and committing it. The destination initially had a clean worktree and directory
placeholder READMEs. Existing experiment-category placeholders were preserved.

Copied 4,513 workspace files into the existing purpose/architecture/machine layout.
All 1,314 raw timing files were losslessly gzip-compressed: 8,849,664,000 decoded
bytes to 2,035,465,952 compressed bytes. Every copied raw file was decompressed and
SHA-256 checked against its source. All other non-Markdown files also matched
their original SHA-256; Markdown links were mechanically relocated. The manifest
records original and packaged paths, sizes and checksums. Original runs remain
untouched, including pilots, deferred attempts, and inconsistent distributions.

Main code is in `main_code/common` with both architecture branches; architecture
READMEs point there. Saved per-run sources are in `main_code/common/snapshots`.
Collection/analysis/test programs and plan JSON are in `scripts`; raw metadata,
build commands, binaries, disassembly and logs are under per-host `data_raw`;
CSV results are in `data_processed`; figures are in `plots`; findings/guides/work
history are under `report/capacity`. No final report/slides or student-authored
Table 1/hypothesis documents were available to import; their absence is noted.

Added root/per-machine reproduction instructions, AI-assistance disclosure draft,
raw-data Git exclusions, and a checksum-verifying restoration helper. The existing
diagnostic analysis was adjusted to resolve its archived baseline under the
restored workspace instead of depending on the old absolute mount path. Native
benchmark code and historical experiment metadata were not rewritten.

The spec permits multi-gigabyte raw datasets outside Git. Raw `.bin.gz` files are
present locally for the Moodle package but intentionally not committed. Their
metadata/checksums, source, processed results and plots are committed. A Git-only
clone/archive is not the complete Moodle submission. No SSH trust file, private
keys, credentials, virtual environment, bytecode cache, or course handout was
copied. Secret-pattern screening found no candidate secrets in exported text.

This is a progress checkpoint, **not Phase I completion or a freeze/tag**. No new
benchmark, PMU/cache lookup, Hazel job, reservation, or TA message was performed.
The local commit uses the server's existing Git author configuration; association
of that email with the student's GitHub account still needs student verification.
No push was requested or performed. The unchanged main experiment directory is
retained as the working source; this import is a separate submission snapshot.

Validation: fully restored and checksum-verified all 4,513 packaged files into a
separate temporary workspace. The restoration test passed lossless decoding,
checksum, overwrite-refusal, and unsafe-path-refusal checks. In that restored
workspace, the arithmetic tests and both comparison analyses passed: 918 selected
coarse/refinement distributions with 176 overlaps, and 153 diagnostic distributions
with 198 historical comparisons and 2,100 chronological chunks. Packaged file-size
checks and the checked report/data links passed. No benchmark was launched by
these tests. The full temporary restore is a verification copy, not a submission
requirement or replacement for the packaged raw archives.
