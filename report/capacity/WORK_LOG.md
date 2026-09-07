# Project work log

## 2026-09-07: replace unpublished import commits

User requested replacing the two earlier import commits with the cleaned current
state so excluded dataset artifacts do not enter the submitted branch history.
Verified remote main was still `d8161f1811f2ca0b2ac821ec99855935c44a5cd9`,
the parent of the local import commits `18c56a6` and `1690bcc`. Replaced those
local commits with a selected-only commit, preserving the working files and
original experiment directory. Used the user's supplied GitHub email
`hclee412@gmail.com` for this commit only. No push, force-push, or Phase I freeze.
The older entries below describe the state at the time they were recorded.

## 2026-09-07: repository dataset selection

At the user's explicit request, this checkout now retains only eight main
capacity sets: the seven non-Crux original full/refinement sets and Crux CPU 2's
full/refinement set. Pilots, Crux CPU 0 and additional three-repeat diagnostics,
including their copied raw/processed/plot artifacts, are excluded from this
checkout. The kept data are 918 million-sample distributions: 280 coarse and
638 refinement distributions. Source/build/run records for these sets remain.

The cleanup moves 1,417 copied artifacts, including 396 compressed raw files,
to `/tmp/capacity-selection-HMdBsv/removed`; every excluded artifact's original
in `/mnt/ncsudrive/h/hlee58/ECE592_proj1` was verified before the move and is
preserved. `data_processed/capacity_excluded_manifest.json` records the exclusions
and original checksums; it is not an input to dataset restoration. Main manifests,
current README/findings and reproduction instructions are updated for the selected
sets. The overview now uses Crux CPU 2, consistent with the refinement comparison.
No retained timing samples are changed and this is not a Phase I freeze.

Validation: restored and checksum-verified all 3,096 retained mapped files in a
new selected-only workspace. The existing analysis validated all 918 distributions
and reproduced 176 overlap comparisons; both comparison CSV checksums matched.
Regenerated and visually checked the eight-panel overview using Crux CPU 2.
Current README/findings links resolve and `git diff --check` passed. No new commit
or push was made. Existing restoration/analysis tools were reused.

The spec still requires all collected data for the final handoff. These excluded
datasets must accompany the final submission separately or through an approved
alternate handoff; they are not being discarded scientifically. No Git history
is rewritten. Entries below are historical and may refer to datasets no longer
copied into this checkout; use the original workspace/exclusion manifest for them.

## Scope and current status

The user reports that SSH access checks, Table 1, and two initial hypotheses are
complete. The current agreed milestone is a validated timing-only capacity pilot
on one assigned ECE host, followed by a discussion of its findings before full
measurements. This log records AI-assisted work; it does not replace the required
two-student contribution appendix or AI disclosure.

At log creation, no assigned-host pilot or full measurement had been collected. No cache
specifications or PMU counters have been consulted. No Hazel experiments have run.
No passwords or private keys are recorded here or in project code.

## Earlier preparation in this conversation

- Read the supplied project PDF, particularly access rules, global measurement
  requirements, starter timing code, phase ordering, and Section 8.2.
- Created `cache_capacity.c`: x86-64/AArch64 timer paths, randomized and sequential
  dependent pointer cycles, affinity enforcement, warm-up, empty-timer control,
  and unsigned 64-bit raw batch timings.
- Created `capacity.py`: collection with randomized configuration order, raw-data
  metadata, summary statistics, and vector capacity/box plots without grid lines.
- Created `CAPACITY_GUIDE.md`: commands and explanations for setup, compilation,
  assembly inspection, pilot, full sweep, and dense boundary refinement.
- Created `test_capacity.py`: short collection/analysis checks, invalid sample
  handling, overwrite protection, and truncated-file rejection.
- Earlier local smoke checks on grendel46 compiled with GCC at `-O0`, checked the
  x86 disassembly, and passed collection/statistics/PDF generation. These were
  software checks, not results from an assigned machine. Temporary test data were
  removed by the test's temporary-directory cleanup. Arm execution is unverified.
- Matplotlib was installed in `/tmp/ece592-capacity-venv` for local plot verification;
  no system-wide package installation was performed.

## 2026-09-06: start of authorized remote-work session

Execution environment: `grendel46.ece.ncsu.edu`; status checked at
`2026-09-06T10:42:44Z` (06:42:44 Eastern daylight time).

### Review against the assignment

Re-read PDF pages 3–5 and 13–15 and reviewed all existing benchmark, runner, and
test source. The current implementation provides these controls:

| Requirement | Implementation/status |
| --- | --- |
| Phase I uses timing only | No PMU or cache-parameter queries in collection |
| `-O0` and assembly inspection | Documented build; earlier x86 inspection passed; repeat on selected host |
| One pinned logical CPU | Runner uses `taskset`; C checks affinity count is exactly one |
| Local memory placement | First-touch after pinning; actual host policy/locality still needs checking |
| Dependent read loop | Explicit register-based load dependency; no stores in repeated load loop |
| Warm-up | Full-cycle validation plus two complete untimed traversals |
| Timer-overhead characterization | Separate raw empty timer-pair distribution; no automatic subtraction |
| One million samples per reported point | Runner defaults to 1,000,000 batches; shorter runs require `--pilot` |
| Preserve distributions | Raw batch durations plus sample count, steps, units, seed, and byte order |
| Prefetch control | Same footprint/node spacing in random and sequential modes |
| Statistics/plots | Mean, median, sample SD, quartiles, 5th/95th percentiles, outliers, box plots |
| Dense boundary evidence | Requires later refinement selected from measured transitions; not collected |

Remaining measurement qualifications: batched values are averages per dependent
access, not distributions of individual loads; loop/call overhead remains;
sample-buffer stores outside the timed loop can perturb cache state; random
traversal can expose TLB effects. Batch-length and noise controls must be validated
before drawing cache conclusions. No numerical cache claims have been made.

The directory still has no usable Git repository (`git status --short` reports
`fatal: not a git repository`). No commits, pushes, or phase-freeze tags were
created. Source/binary hashes are useful for pilots but do not replace the spec's
required team GitHub history and frozen commits.

### SSH access checks

Used existing authentication only, with the following read-only remote command:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes \
    hlee58@sunbird.ece.ncsu.edu hostname
```

The sandbox attempt failed DNS resolution. After network escalation, Sunbird
responded to SSH but failed host verification. The other seven hosts were checked
with the same options and a five-second connection timeout outside the sandbox.

| Host (`.ece.ncsu.edu`) | Result |
| --- | --- |
| sunbird | No known ED25519 host key; host key verification failed |
| thunderbird | No known ED25519 host key; host key verification failed |
| skylark | No known ED25519 host key; host key verification failed |
| artemisia | No known ED25519 host key; host key verification failed |
| charnwood | No known ED25519 host key; host key verification failed |
| crux | No known ED25519 host key; host key verification failed |
| ookay | No known ED25519 host key; host key verification failed |
| upgrade | No known ED25519 host key; host key verification failed |

Exact error pattern:

```text
No ED25519 host key is known for <hostname> and you have requested strict checking.
Host key verification failed.
```

These checks did not reach user authentication or execute remote `hostname`.
They establish that the hosts responded to SSH, not that account login succeeded.
No trust entries were added and no SSH settings were changed.

`ssh-add -l` returned `Could not open a connection to your authentication agent.`
`ssh -G sunbird.ece.ncsu.edu` reports no configured connection multiplexing
(`controlmaster false`, `controlpersist no`). Private-key contents were not read.

### Next steps

1. Establish a trusted, authenticated SSH connection from grendel46 to Sunbird,
   using authentication completed privately by the user or an available SSH key.
2. Inspect phase-safe topology, allowed CPUs, current activity and reservation
   information before selecting a core. Record SMT/locality limitations honestly.
3. Compile and inspect assembly on Sunbird; collect explicitly labeled short pilot
   distributions with 256, 1024, and 4096 dependent loads per batch.
4. Compare batch-length sensitivity, timer overhead, regular/random traversal,
   and raw-data/plot integrity. Explain findings before full collection.
5. Resolve the team Git repository before final evidence/phase-freeze work.

The other Section 8.2 experiments and all later phases remain outstanding.

### SSH access resolved; pilot preparation

An existing `~/.ssh/id_rsa` identity file was found (existence checked; contents
not read). A follow-up Sunbird connection used `StrictHostKeyChecking=accept-new`
and a project-local `ssh_known_hosts` file. This records first-use trust; it is
not an independently verified fingerprint. Future connections use strict checking
against this file. Global SSH settings and trust files were not modified.

The existing identity successfully authenticated as `hlee58`, and remote
`hostname` returned `sunbird.ece.ncsu.edu`. The disclosed password was not used.
Authentication on the other seven hosts has not yet been tested beyond the
initial strict host-key checks.

Phase-safe remote inspection confirmed:

- CPU identity: Intel Xeon E5-2680 v3; compiler GCC 11.5.0; Python 3.9.25.
- Kernel: `5.14.0-611.54.1.el9_7.x86_64`.
- Shared project source is available on Sunbird; SHA-256 of `cache_capacity.c`:
  `c456fd27326397763434282d6f566c6215c4b0701572bf48da814ef58017e754`.
- Allowed logical CPUs: `0-2,24-26`. CPU 2 is core 2, socket 0, NUMA node 0;
  its SMT sibling is CPU 26.
- Two-second `/proc/stat` activity check: CPUs 0/1 were 100% busy; CPU 2 was
  1.98% busy and sibling 26 was 0.5% busy. Selected CPU 2 for the short pilot.
  This is a point-in-time check, not proof of continued isolation.
- Approximately 124 GB of available system memory was reported; the pilot's
  largest footprint is 64 MiB plus its temporary shuffle/sample buffers.
- `mpstat` and `numactl` were not found. Use documented first-touch placement,
  not privileged configuration changes.

Attempted to read the course reservation sheet; its CSV export returned HTTP 401.
No reservation was made and reservation status is unknown. The spec describes
reservations as conditional on interference; proceed only with a short, low-noise
pilot, record the access limitation, and re-evaluate before full runs.

Planned pilot parameters: CPU 2, spacing 8 bytes, seed 592, 1,000 timed batches
per configuration, footprints 4/16/64/256/1024/4096/16384/65536 KiB, both random
and sequential traversals, batch lengths 256/1024/4096, plus empty controls.
These are diagnostic pilot samples, not final report evidence or frozen inferences.

### Pilot completed: artifacts and verification

All three sweeps completed successfully on Sunbird between 10:49:32 and 10:49:49
UTC (06:49 Eastern daylight time). Artifacts are in
`results/sunbird-pilot-20260906/`:

- `cache_capacity`: native Sunbird executable; SHA-256
  `fb3b755d7fe3d7b129cfa97e5d0edf805cb9d3a7f31c9d6ef031bceaad156ba8`.
- `benchmark.dis`: full source-interleaved disassembly. Reviewed `chase`, the
  fenced timer instructions, and the timer/chase call sequence in `main`.
- `smoke-test.log`: Sunbird compilation, collection, input/overwrite protection,
  truncated-data rejection, summary statistics, and PDF-generation checks passed.
  The check ran under `taskset -c 2` to avoid busy CPUs 0/1.
- `n256`, `n1024`, `n4096`: one complete run per batch length. Each contains raw
  `.bin` distributions, point JSON/diagnostics, `environment.json`, `COMPLETE`,
  `summary.csv`, `capacity.pdf`, and `boxes.pdf`.

The build used:

```bash
gcc -O0 -g -std=c11 -Wall -Wextra -Werror -fno-omit-frame-pointer \
  -o results/sunbird-pilot-20260906/cache_capacity cache_capacity.c
```

Exact collection commands and notes are retained in each `environment.json` and
each point's `invocation` field. Analysis used:

```bash
python3 capacity.py plot results/sunbird-pilot-20260906/n256
python3 capacity.py plot results/sunbird-pilot-20260906/n1024
python3 capacity.py plot results/sunbird-pilot-20260906/n4096
```

An additional raw-file check passed: all 51 distributions have exactly 1,000
positive timer durations (8,000 bytes/file), correct metadata, CPU 2 recorded,
and corresponding summary rows. Total: 51,000 diagnostic timed batches, including
three empty controls. No data were discarded or promoted to full measurements.

### Pilot findings, not cache specifications or final inferences

| Dependent loads per batch | Empty-pair median (TSC ticks/pair) | Empty cost divided by batch length (ticks/access) |
| --- | --- | --- |
| 256 | 85 | 0.3320 |
| 1024 | 72 | 0.0703 |
| 4096 | 80 | 0.0195 |

Batching substantially reduces the timer-pair contribution. The empty control
does not measure every component of call/loop overhead; no subtraction was applied.

Selected randomized traversal medians, all in TSC ticks/access:

| Footprint | N=256 | N=1024 | N=4096 |
| --- | --- | --- | --- |
| 4 KiB | 6.668 | 5.981 | 5.580 |
| 16 KiB | 6.289 | 5.649 | 8.370 |
| 64 KiB | 12.656 | 17.513 | 12.999 |
| 16 MiB | 43.641 | 43.430 | 43.388 |
| 64 MiB | 147.852 | 142.896 | 146.078 |

For N=4096 at 64 MiB, sequential traversal's median is 4.178 ticks/access versus
146.078 for random traversal. The separation is consistent with regular access
benefiting from spatial locality/prefetching. It does not, by itself, establish
cache size or isolate the effect of a particular prefetcher.

The collection/analysis pipeline works, and some large-footprint medians are
repeatable. However, the 16/64 KiB points change substantially across batch runs.
Batch length and run time/order changed together, so these runs cannot distinguish
batch effects from frequency changes, scheduling/interference, or other confounds.
Do not infer exact capacities or validated per-level hit latencies from this pilot.

### Handoff after the first pilot

The agreed first experiment has produced diagnostic data and plots; stable
measurement methodology still needs further validation. Before full collection:

1. Repeat selected small-footprint points at a fixed batch length with different
   seeds and record CPU/sibling activity during the runs, not just beforehand.
2. Check warm-up/batch sensitivity and resolve the small-footprint variation;
   use the reservation sheet if interference prevents clean measurement.
3. Locate/use the actual team Git repository and preserve both members' work and
   identities. This directory's unusable `.git` placeholder was left untouched.
4. Only then collect >=1,000,000 samples/configuration, sweep more densely around
   observed transitions, and repeat on the remaining assigned machines.

No full measurement campaign, cache-value freeze, phase transition, or Hazel
execution was performed in this session. Benchmark/analysis source was reviewed
but unchanged; this session added the log, project-local SSH host record, and
generated pilot artifacts.

## 2026-09-06: three repeats with fixed settings

User requested the next reliability check: repeat footprints 4, 16, and 64 KiB
three times at 4,096 dependent reads/batch. Unlike the earlier proposed
different-seed diagnostic, this authorized check keeps seed 592 fixed so that
address order, as well as batch length, stays unchanged.

Added `repeat_capacity.py`, a small driver that reuses the existing collector and
plotter without changing the benchmark. The driver checks it is on Sunbird and
CPU 2 is allowed, creates a new timestamped directory, runs all three repeats,
records before/after OS CPU activity, and combines summary rows. Invocation:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/mnt/ncsudrive/h/hlee58/ECE592_proj1/ssh_known_hosts \
  hlee58@sunbird.ece.ncsu.edu \
  'cd /mnt/ncsudrive/h/hlee58/ECE592_proj1 && python3 repeat_capacity.py'
```

The initial sandbox connection failed DNS resolution; network escalation allowed
the existing trusted-key login. No password was used. Confirmed the original
Sunbird executable SHA-256 remained
`fb3b755d7fe3d7b129cfa97e5d0edf805cb9d3a7f31c9d6ef031bceaad156ba8`.
The benchmark source hash also matched the original pilot.

Results: `results/sunbird-repeat-20260906T110920Z/` (started 11:09:20 UTC,
07:09:20 Eastern daylight time). `repeat1`, `repeat2`, and `repeat3` each contain
raw samples, metadata, statistics, plots, and a completion marker. The parent
directory holds `comparison.csv`, collection logs, and activity JSON files.

Fixed settings: Sunbird CPU 2/core 2/socket 0/NUMA 0; original `-O0` executable;
1,000 samples/point; 4,096 loads/batch; seed 592; spacing 8 bytes; identical
configuration order; random and sequential modes plus an empty timer control.
Warm-up and first-touch method are unchanged. No cache specifications or PMU
counters were queried. These remain short diagnostics, not final evidence.

### Results

Randomized traversal medians (TSC ticks/access):

| Footprint | Repeat 1 | Repeat 2 | Repeat 3 |
| --- | --- | --- | --- |
| 4 KiB | 6.277344 | 5.908203 | 6.277588 |
| 16 KiB | 6.277344 | 6.277344 | 6.277344 |
| 64 KiB | 13.001953 | 13.018799 | 12.994385 |

The 16 KiB median is identical across these repeats; the range of the 64 KiB
medians is less than 0.2% of the smallest. The 4 KiB range is approximately 6.3%
of its smallest median. Means, percentiles, SD, outliers, and both traversal modes
are preserved in `comparison.csv`; equality of medians does not imply identical
full distributions.

Empty-pair medians were 88, 64, and 88 TSC ticks/pair, respectively (roughly
0.016–0.021 ticks/access after dividing by 4,096). No subtraction was applied.

CPU 26 activity over each complete collection interval was 14.3%, 6.8%, and 6.5%.
These intervals include Python/process startup and setup, not just timed loads;
the unpinned driver can itself run on CPU 26. These observations cannot prove
another user's work interfered during measurement. No quiet reservation was made;
the earlier reservation-sheet access limitation remains.

All three driver runs and plots completed. Additional checks verified all 21 raw
distributions had exactly 1,000 positive durations, correct lengths (8,000 bytes),
the requested identical settings, and completion markers: 21,000 total diagnostic
samples, including empty controls. The driver's summary assertions also passed.

### Interpretation and remaining work

Holding settings fixed produced substantially better repeatability at 16 and
64 KiB than the original three different-batch runs. This supports continuing
method development with N=4096, but does not establish the earlier discrepancy's
cause or eliminate the remaining 4 KiB variability. No exact cache capacity or
per-level hit latency is claimed. Longer runs and dense boundary sampling still
need the spec's full sample counts and interference/placement checks.

The requested three-repeat check is complete. The next project stage is a full
capacity sweep with adequate run-condition records, followed by refinement around
measured boundaries; the team Git repository must also be resolved for final
reproducibility and phase freezes. No full sweep or phase transition was started.

## 2026-09-06: full capacity campaign started

User authorized the full capacity sweep and extending the validated method to the
other ECE machines. User will make commits personally after Phase I. No Git
metadata was changed and no commits were made. The benchmark still uses timing
only; no PMU, cache specification queries, or Hazel execution.

Added `lab_capacity.py` to prepare native builds and invoke the existing collector
for a short pilot or a full run. Each host has a source snapshot, native binary,
build command, source-interleaved disassembly, and phase-safe preflight metadata
under `results/capacity-20260906/<host>/`. Existing pilot artifacts are preserved.
The preflight samples OS CPU activity for two seconds and chooses an allowed CPU
whose physical core/siblings are <=10% busy in that sample. This is an initial
screen, not exclusive access or a guarantee against later interference.

| Host | Access/build status | Selected CPU | Core/socket/NUMA | Initial maximum sibling busy |
| --- | --- | --- | --- | --- |
| Sunbird | SSH/native compile passed; full sweep launched | 2 | 2/0/0 | 1.49% |
| Thunderbird | SSH/native Arm compile passed; pilot launched | 0 | 0/0/0 | 0% |
| Skylark | SSH/native compile passed; pilot launched | 0 | 0/0/0 | 0% |
| Artemisia | SSH/native compile passed; pilot launched | 5 | 5/0/0 | 7% |
| Charnwood | SSH/native compile passed; pilot launched | 2 | 2/0/0 | 0% |
| Crux | Existing SSH key rejected; no benchmark run | — | — | — |
| Ookay | Existing SSH key rejected; no benchmark run | — | — | — |
| Upgrade | Existing SSH key rejected; no benchmark run | — | — | — |

New host keys were recorded using SSH first-use acceptance in project-local
`ssh_known_hosts`; subsequent calls use strict checking. No global SSH changes or
password use. The three inaccessible hosts return `Permission denied
(publickey,gssapi-keyex,gssapi-with-mic,password,keyboard-interactive)`.
The user was asked asynchronously to enable the existing public key or provide
reusable authenticated sessions. No TA message was sent; the user must report
any unresolved machine exception as required by the spec.

Reviewed the four new native dependent loops: x86 `mov/dec/jne` and Arm
`ldr/subs/b.ne`, with no stores inside the repeated loop. Reviewed Arm counter
reads, barrier ordering, and the enclosing timer/chase call sequence.

Sunbird full collection uses 1,000,000 batches per point, 4,096 dependent
loads/batch, 8-byte node spacing, seed 592, random and sequential traversal,
and powers-of-two footprints from 4 KiB to 256 MiB, plus an empty timer control.
This is an initial coarse sweep; dense boundary refinement remains necessary.
Each full run produces 35 distributions (280 MB raw data). Processes allocate
at most approximately two times the maximum footprint during shuffle plus the
8 MB sample buffer; shuffle storage is freed before timing.

Sunbird collection runs through `nohup`, with PID in `sunbird/full.pid` and
progress/errors in `sunbird/full.log`. This allows the authorized run to survive
an SSH disconnect. A `full/COMPLETE` marker indicates collection success only;
statistics/plot inspection and boundary validation follow separately.

Reservations have not been made: the reservation sheet previously returned HTTP
401. All runs retain that limitation in their notes and use first-touch placement
after CPU pinning without changing system settings. Pilot results on the four
new hosts must be checked before launching their full runs.

### New-host pilots checked; full collection expanded

Thunderbird, Skylark, Artemisia, and Charnwood pilot collection and analysis all
completed. Each pilot contains 17 distributions of 1,000 samples, both traversal
modes, environment metadata, and PDF plots. No workload point had a zero duration.
Thunderbird's empty timer sequence had 104/1,000 zero durations because the timer
is coarse; its smallest non-empty batches had about 138 counter ticks, so the
batched workload is resolvable. The empty median was one Arm counter tick/pair.
The x86 empty medians were 72 (Skylark), 62 (Artemisia), and 84 (Charnwood) TSC
ticks/pair. No raw tick comparison across different ISAs is being used as a
latency comparison.

The pilots show footprint-dependent shifts, with wider distributions at some
intermediate footprints (notably Artemisia). These are reasons to preserve full
distributions and uncertainty, not assign textbook cache sizes. No cache-size
claims were made from the pilots.

Following inspection, full 1,000,000-sample sweeps were launched on these four
hosts with the same settings as Sunbird. Each has `full.log` and `full.pid` in
its own campaign directory. Raw durations are buffered and written after each
point, so a `.bin` file may remain empty while its point is still running.
The `.json` metadata written afterward marks a successfully collected point;
`full/COMPLETE` marks all 35 collected points. Plots are generated after collection.

All five accessible machines are running independently, one pinned benchmark
process per machine. The three SSH authentication failures remain outstanding.

Launch verification: Sunbird PID 852451 (started 11:17:30 UTC); Thunderbird
2225774 (11:19:56); Skylark 1056155 (11:19:57); Artemisia 3534308 (11:19:58);
Charnwood 853912 (11:20:00). These are host-local driver PIDs, not portable IDs.
Early progress checks found 3/1/3/2/1 completed distributions respectively, out
of 35 per host. Every completed point checked had exactly 1,000,000 samples,
4,096 loads/batch, and an 8,000,000-byte raw file. Collection is still in progress;
no completed full-sweep result or final capacity claim is available yet.

## 2026-09-06: remaining SSH access resolved; all eight sweeps launched

After the user installed the public key using `ssh-copy-id`, verified noninteractive
SSH login on Crux, Ookay, and Upgrade using strict host-key checking. No password
was supplied to commands or stored. The earlier authentication blocker is resolved.

Executed `python3 lab_capacity.py prepare results/capacity-20260906` on each of
these three hosts. Native `-O0` compilation succeeded; saved and inspected the
dependent `mov/dec/jne` loop, fence/timer instructions, and surrounding timing
calls. All three selected core/sibling groups were 0% busy in their two-second
preflight checks:

| Host | Selected CPU | Core/socket/NUMA | SMT group |
| --- | --- | --- | --- |
| Crux | 0 | 0/0/0 | 0 |
| Ookay | 0 | 0/0/0 | 0,4 |
| Upgrade | 1 | 1/0/0 | 1,7 |

Ran `lab_capacity.py pilot` on each host, then generated statistics and both PDF
plots using the existing analysis script. Each pilot completed all 17 points of
1,000 samples. Summary inspection found zero zero-duration samples, low empty
timer-pair cost relative to 4,096-load batches, and footprint-dependent latency
changes. Empty-pair medians: Crux 40, Ookay 54, Upgrade 46 TSC ticks/pair. These
pilots are diagnostic, not final cache-size evidence.

Launched their full sweeps using the same source snapshots/settings as the five
earlier machines: 1,000,000 samples per point, 4,096 dependent loads per batch,
8-byte spacing, seed 592, powers of two from 4 KiB through 256 MiB, both traversal
modes, and an empty control. Each runs through `nohup` with its own `full.log`,
`full.pid`, and raw-data directory. Newly launched driver PIDs and times:

- Crux: PID 705850, 11:26:11 UTC.
- Ookay: PID 770950, 11:26:12 UTC.
- Upgrade: PID 1540520, 11:26:12 UTC.

Launch/progress verification found completed-point counts of 10/35 on Sunbird,
3/35 each on Thunderbird/Skylark/Artemisia/Charnwood, and 1/35 each on the three
new hosts. All completed points checked have 1,000,000 samples, 4,096 loads per
batch, and an 8,000,000-byte raw file. No full run has a `COMPLETE` marker yet;
these counts are a snapshot, not a claim of finished sweeps.

All eight assigned hosts are now included. Reservation/locality limitations from
the earlier log still apply. No commits, PMU work, cache-specification lookup,
or Hazel execution was performed. Next: check collection completion, analyze
full distributions, and select dense boundary refinements from the timing data.

## 2026-09-06 16:59 UTC: full collection completion verified

Status check confirmed `full/COMPLETE` and successful collection log endings on
all eight assigned ECE hosts. Each has 35 completed distributions: 17 footprint
sizes in two traversal modes plus one empty timer control. Across all hosts,
280 distributions contain 280 million timed samples (including empty controls).

Checked metadata and raw file sizes for every completed point: each records
1,000,000 samples and 4,096 configured loads per batch, with an 8,000,000-byte
raw file. Empty controls contain no workload loads. This verifies collection
completeness and file lengths, not final scientific validity or inferred geometry.

Full-sweep statistics/plots and dense boundary refinement remain the next tasks.
Completion of this coarse capacity collection does not complete all of Phase I.

## 2026-09-06: full analysis and data-selected refinement

Generated `full/summary.csv`, `full/capacity.pdf`, and `full/boxes.pdf` for every
host from its complete raw data using the existing plotter. All eight analysis
invocations succeeded. Each CSV contains all 35 configurations and the required
mean, median, sample standard deviation, quartiles, 5th/95th percentiles, and
outlier count. Empty controls remain in timer ticks/pair, workload distributions
in ticks/access. No raw samples were modified or removed.

Added `capacity_overview.py` and generated `capacity_overview.pdf` and `.png` in
the campaign directory. The overview uses separate panels/units per host and
logarithmic axes; visually inspected the rendered image. Its assertions check
35 summary rows per host, 17 rows per traversal, and one million samples per row.
These checks passed. Shaded percentile bands are distributions, not confidence
intervals. No raw-clock comparisons across ISAs are made.

Added `CAPACITY_FINDINGS.md` with links to the full plots/statistics, measured
transition regions, qualifications, and refinement rationale. Observations include
a first pronounced rise at 32–64 KiB on most x86 hosts, 64–128 KiB on Thunderbird,
and a non-monotonic middle region plus broad large-footprint distributions on
Artemisia. These are observed timing regions, not final cache-size claims.

Created `refinement_plan.json` with explicit per-host sizes selected from those
coarse measurements, and `refine_capacity.py`, which reuses the unchanged native
binary and saved collector on the same CPU. Three groups cover small, middle,
and large transition regions. All groups use one million samples per point,
4,096 dependent loads/batch, seed 592, 8-byte spacing, both traversals, and an
empty control. Overlapping coarse sizes are deliberately repeated to check
cross-run agreement before combining evidence.

Validated all eight plans for positive, sorted, unique sizes in each group. The
plans have 79/81/77/89/75/81/75/81 distributions for
Sunbird/Thunderbird/Skylark/Artemisia/Charnwood/Crux/Ookay/Upgrade, respectively.
This is 638 planned distributions including empty controls. Each host keeps a
plan/driver snapshot and current CPU-activity preflight in its campaign directory.

The refinement driver samples the original core/siblings again for two seconds
and defers if any exceed 10% busy. Initial launches passed on Sunbird, Thunderbird,
Skylark, Artemisia, and Ookay; Upgrade status is being checked. Charnwood and Crux
deferred because their original core/siblings exceeded the threshold. No benchmark
was forced onto those busy cores. Logs and driver PIDs are stored per host as
`refinement.log` and `refinement.pid`. Collection is not yet complete.

The reservation sheet remains inaccessible; no reservation is claimed. User
continues to handle Git commits. No PMU, cache-specification lookup, or Hazel
execution took place. Student attribution and the final source/diagram/report
requirements remain to be completed by the team; the analysis does not invent
contributor identities.

Launch follow-up: Upgrade also passed its fresh activity check, so six hosts are
collecting refinement data. Charnwood CPU 2 and Crux CPU 0 were still 100% busy
in a second two-second check; their refinements remain deferred with no collected
points. No retry was launched onto those occupied cores and no unrelated process
was stopped.

Early completed-point checks passed for every new point available: one million
samples, 4,096 loads per batch, and 8,000,000 raw bytes per point. Current small-group
counts were Sunbird 14, Thunderbird 16, Skylark 18, Artemisia 8, Ookay 19, and
Upgrade 21. These are progress snapshots; no refinement group was complete at
this check. Final small/middle/large inference and overlap comparison await the
remaining measurements. Deferred hosts need a quiet interval on their original
cores before this same-core refinement plan can proceed.

## 2026-09-06 21:55 UTC: Charnwood/Crux retry

At the user's request, retried the existing follow-up driver on both hosts.
Preserved previous preflight records as `refinement-preflight-attempt1.json` and
kept the original logs. Retry output is in `refinement-retry1.log`, with attempted
driver PIDs in `refinement-retry1.pid`; those drivers exited after the checks.

- Charnwood, 21:55:55 UTC: selected CPU 2 was 0.5% busy, but its SMT sibling
  CPU 6 was 100% busy. The physical core therefore failed the quiet-core check.
- Crux, 21:55:56 UTC: selected CPU 0 was 100% busy and failed the same check.

Neither follow-up benchmark started; no `refine-small` directories or new timing
samples were created on these two hosts. No other processes were stopped or
system settings changed. These measurements need a quiet interval on the original
cores, or a separately documented move to another core with overlap controls.

## 2026-09-06 22:35 UTC: Charnwood follow-ups started

At the user's request, launched Charnwood's unchanged refinement plan after a
fresh two-second activity check. At 22:35:51 UTC, CPU 2 and its SMT sibling CPU 6
were both 0% busy, so the driver passed its preflight and started collection.

Driver PID: 866985 on Charnwood. Progress/errors: `refinement-retry2.log`;
PID record: `refinement-retry2.pid`, both under
`results/capacity-20260906/charnwood/`. Preserved the previous preflight as
`refinement-preflight-attempt2.json`; earlier attempt logs remain unchanged.

Verified `refine-small/environment.json` exists and the log shows the empty
control followed by the first workload configuration. Small, middle, and large
groups will run sequentially with the existing settings: 1,000,000 samples/point,
4,096 dependent loads/batch, seed 592, and the original CPU/native binary.
This confirms launch, not completion. No new Crux run was started.

## 2026-09-06 23:55 UTC: Crux moved to a quiet core; both runs scheduled

User authorized another CPU and both a powers-of-two sweep and follow-up there.
Created `results/crux-new-core-20260906T235055Z/crux/`; original CPU 0 results and
deferred-attempt records remain untouched. The new selected placement is CPU 2,
physical core 2, socket 0, NUMA node 0, with sibling list `[2]`. Initial preparation
and the fresh two-second launch check at 23:55:03 UTC both measured 0% busy there.
This is a short activity screen, not a reservation or proof of isolation. Other
cores can still compete for shared resources. Reservation-sheet access remains
unavailable; no system settings or unrelated processes were changed.

Prepared native `-O0` build, source snapshots, build command, and disassembly.
The C source hash matches the original campaign; inspected the register-dependent
load loop with no stores inside it. The new-core pilot completed all 17
distributions with 1,000 samples each, 4,096 loads/batch, CPU 2 placement, correct
8,000-byte files, and no zero durations. Generated statistics and PDF plots and
visually inspected the capacity plot. Empty median: 40 TSC ticks/pair, without
subtraction. Pilot results are diagnostic, not the required full-count evidence.

Reused existing drivers. `refine_capacity.py` now accepts an optional campaign
directory, retaining the original default; its notes identify the original
coarse campaign as the source of the existing data-selected refinement plan.
The new full and refinement runs use the same new native binary and CPU 2.

Launched a disconnect-safe serial sequence, host-local PID 722678, recorded in
`sequence.pid`; exact commands are in `sequence-command.txt` in the new directory:

1. `full`: powers-of-two footprints from 4 KiB through 256 MiB, both traversals
   and empty control, 35 distributions. Progress/errors are in `full.log`.
2. After successful full collection, the existing Crux small/middle/large
   refinement plan: 81 distributions including three empty controls. The driver
   repeats its quiet-core check and defers if CPU 2 exceeds 10% busy; it does not
   automatically retry a failed check. Progress/errors will be in `refinement.log`.

Both use 1,000,000 samples per point, 4,096 dependent loads/batch, seed 592,
8-byte spacing, and random plus sequential traversal. They run sequentially, not
concurrently. The follow-up sizes were selected from the original CPU 0 coarse
measurements; repeated powers-of-two points allow comparison on the new core.
Final analysis must compare the new sweep and refinements before combining
evidence; additional boundaries revealed by the new sweep may need later review.

Launch verification found the sequence, full driver, and benchmark alive, with
`full/environment.json` recording CPU 2 and all requested settings. The completed
empty control had exactly 1,000,000 samples and 8,000,000 raw bytes; the first
random workload was running. Full collection is not complete and refinement has
not started yet. Analysis/plots of full-count data remain separate subsequent
work. No PMU/cache-specification lookup, Hazel execution, or Git commits occurred.

## 2026-09-07 UTC: completed refinement analysis and same-placement comparison

User authorized the next analysis step. All eight hosts' capacity refinement
collections were complete, including Crux's new CPU 2 sequence. Crux collection
durations were 33.03 minutes for the coarse sweep, then 1.90/5.37/47.69 minutes
for small/middle/large refinements. Completion markers and the final driver log
confirm successful collection; these durations do not imply exclusive access.

Generated `summary.csv`, `capacity.pdf`, and `boxes.pdf` using the existing
`capacity.py plot` for all 24 refinement groups plus Crux's CPU 2 full sweep.
All 25 invocations completed successfully. Used the existing temporary Python
environment `/tmp/ece592-capacity-venv` and Matplotlib config directory; no new
dependency or remote benchmark was introduced. Raw timing files were unchanged.

Added `capacity_refinement_analysis.py`, reusing the summary format and existing
plotting dependencies. It compares the original seven other hosts' coarse runs
against their refinements, and Crux's new CPU 2 coarse run against its CPU 2
refinements. Crux CPU 0 artifacts remain preserved and excluded from this
same-placement comparison. The script's runnable assertions passed for all
918 selected distributions (280 coarse + 638 refinement), checking completion,
expected sizes/modes, million-sample counts, 8,000,000-byte raw lengths, seed 592,
4,096 loads/batch, 8-byte spacing, matching CPU and binary/source hashes within
each host's runs, units, zero-free workload durations, and ordered percentiles.
The existing plotter read the new raw distributions and checked sample lengths.

Created `results/capacity-20260906/refinement-analysis/` with all 918 summary rows,
176 overlapping-point comparisons (both traversal modes), a path/CPU/hash/time
manifest, and separate small/middle/large comparison PDF and PNG figures.
Visually inspected all three rendered comparison images. They show separate
randomized curves and p5–p95 distribution bands, not confidence intervals; no
pooling, smoothing, outlier removal, cross-ISA clock comparison, or overhead
subtraction was performed. Per-group plots retain the sequential sanity check
and randomized box plots. Thunderbird's empty-control zeros remain recorded;
none of its workload distributions contained zero durations.

Expanded `CAPACITY_FINDINGS.md` with artifact links, reproducible commands,
observed onset brackets, repeatability results, and unresolved limitations.
The first sustained rise is localized to 32–36 KiB on six x86 hosts, 48–52 KiB
on Artemisia, and 64–72 KiB on Thunderbird. These are observed brackets, not
final physical cache capacities or statistical confidence intervals.
Sunbird's large-region onset near 24–26 MiB and Skylark's near 16–18 MiB are
clearer; several other middle/large transitions remain broad or non-monotonic.

Randomized overlapping medians within a descriptive 5% screen were:
Sunbird 9/10, Thunderbird 8/11, Skylark 10/10, Artemisia 7/13,
Charnwood 1/11, Crux CPU 2 6/11, Ookay 10/11, Upgrade 9/11.
This threshold is not mandated by the spec and is not a significance test.
Largest issues include Charnwood +73.6% at 4 MiB, Artemisia +64.9% at 2 MiB,
and Crux CPU 2 +26.2% at 256 KiB. Same-core placement does not eliminate
frequency, allocation/page, or shared-resource effects; no cause is proven.
Conflicting runs were retained separately instead of selecting textbook-looking
values. Syntax compilation and all local artifact-link checks also passed.

This authorized analysis step is complete. Final capacity claims still require
treatment of the identified ambiguities; additional controlled measurements
were recommended but not launched. No line-size/associativity/latency/inclusion
or software-metric run, Phase-I freeze, PMU query, cache-specification lookup,
Hazel execution, Git change, or external message occurred. Reservation access
remains unresolved and the user still handles commits. Student attribution,
experiment diagrams, source listings, and final report preparation remain team
responsibilities; no contributor identities were invented.

## 2026-09-07 02:01 UTC: targeted repeatability investigation launched

User authorized investigating the unresolved Charnwood/Crux/Artemisia differences.
First inspected saved OS activity and chronological chunks of existing raw data.
Several discrepancies persisted through the runs, rather than being explained by
a few outliers. Charnwood's 4 MiB ten chunk medians were approximately 66.04–66.23
in the coarse run versus 114.55–115.27 in refinement; Crux CPU 2's 256 KiB chunks
were approximately 8.26 versus 10.41–10.45. Saved 130 descriptive chunk records in
`results/capacity-diagnostic-20260907/prior_chunk_medians.csv`: ten consecutive
100,000-sample chunks per selected distribution, median(raw ticks)/4,096.
No samples were removed or changed. Whole-run Charnwood sibling CPU 6 averages
were low (0.5% coarse, 1.3% large refinement), but averages cannot rule out short
bursts or shared-resource interference. No cause has been established.

Added `CAPACITY_DIAGNOSTIC_PLAN.md` and `diagnostic_capacity.py`, reusing saved
native binaries and collectors. Three repeats use identical per-host lists,
CPU placement, 1,000,000 samples/point, 4,096 loads/batch, seed 592, 8-byte spacing,
both traversal modes and empty controls. Charnwood targets small controls and
2–5 MiB including denser 2–4 MiB points; Crux targets small/middle controls and
4–8 MiB; Artemisia targets a small control and 1.5–3 MiB around its inconsistent
dip. The plan totals 153 distributions across three hosts if all complete.
Relative pointer order is fixed, but fresh processes/allocations do not hold
physical page mapping fixed. The configuration order is identical across the
new repeats, but differs from earlier sweeps because their size lists differ.

Added and ran `test_diagnostic_capacity.py`; activity calculations, fixed settings,
footprint lists, output/native-binary paths, and full sample counts passed.
Syntax compilation passed. The driver verifies the saved binary/source hashes
and original CPU and performs a fresh two-second quiet-core/sibling screen before
each repeat; a busy check exits without automatic retry or deleting existing data.

Launched disconnect-safe drivers, with logs/PIDs in
`results/capacity-diagnostic-20260907/<host>-launch.log` and `.pid`:

| Host | Driver PID | First preflight | Status |
| --- | --- | --- | --- |
| Charnwood | 880314 | 02:01:38 UTC: CPU 2 1.01%, sibling 6 0.51% | Repeat 1 started |
| Crux | 727865 | 02:01:37 UTC: CPU 2 0% | Repeat 1 started |
| Artemisia | 113769 | 02:01:37 UTC: CPU 5 99.50%, sibling 61 99.50% | Driver deferred before collection |

Each launched host keeps snapshots, `plan.json`, `repeatN-preflight.json`,
`repeatN.log`, and eventually whole-repeat activity records and completion markers.
Early completed-point checks on Charnwood and Crux confirmed million-sample
counts, correct 8,000,000-byte raw files, seed 592, and 4,096 loads/batch; run
environment records confirm CPU 2. Collection is still in progress. Artemisia
has no new timing data and needs a quiet interval on its original core; no move
to another CPU or repeated retry was made.

The fresh browser attempt to access the reservation sheet also failed (tool
reported a non-retryable open error; prior access had returned HTTP 401). No
reservation or exclusive access is claimed. These are screened, unreserved
repeatability checks, not proof that interference has been eliminated. If
interference prevents clean measurements, reservation coordination remains
required by the spec. No system settings, unrelated processes, old data, Git
metadata, or external messages were changed; no PMU/cache-spec queries or Hazel
execution occurred. Follow-up analysis and any final capacity claims await the
new collections. Phase I remains open.

## 2026-09-07 02:42 UTC: Artemisia diagnostic retry started

At the user's request, checked the original CPU 5 and sibling 61 again. Both
were 0% busy during the two-second check at 02:41:39 UTC. Retried the unchanged
authorized three-repeat diagnostic in a new directory,
`results/capacity-diagnostic-20260907-retry1/artemisia/`, preserving all records
of the earlier deferred attempt. No benchmark or driver code was changed.

The driver's own fresh preflight at 02:42:05 UTC measured CPU 5 at 0.50% busy
and sibling 61 at 0%, and repeat 1 started. Verified driver PID 131171 alive,
the empty control followed by the first randomized workload in `repeat1.log`,
and environment settings CPU 5, one million samples, 4,096 loads/batch, spacing 8,
seed 592. Placement remains core 5/socket 0/NUMA 0. Launch log and PID are in
the retry campaign parent as `artemisia-launch.log` and `artemisia-launch.pid`.

All three repeats are scheduled sequentially with a fresh quiet-core check
before each; busy checks defer without automatic retry. Collection is underway,
not finished. No reservation or isolation guarantee is claimed. No old data,
system settings, unrelated processes, or Git metadata were changed.

## 2026-09-07 UTC: targeted diagnostic analysis completed

Implemented the user-approved analysis plan after all nine repeats completed.
Analyzed Charnwood and Crux from `capacity-diagnostic-20260907`, and Artemisia
from its successful `capacity-diagnostic-20260907-retry1` campaign. The deferred
Artemisia attempt was excluded, and Crux historical comparisons use CPU 2 only.

Reused `capacity.py plot` for nine summaries, capacity curves, and randomized
box plots; all invocations succeeded. Added `diagnostic_capacity_analysis.py`,
reusing `read_run` and CSV-writing helpers from the existing refinement analysis.
No benchmark implementation or driver was changed and no new benchmark ran.

Generated `results/capacity-diagnostic-20260907/analysis/` containing:
153 diagnostic summary rows, 51 three-repeat median/spread rows, 198 historical
comparison rows retaining both traversal modes and required statistics,
2,100 time-ordered chunk rows (1,440 diagnostic and 660 matched historical),
15 selected/sibling activity rows, an input/placement/hash manifest, and one
two-panel comparison PDF/PNG per host. All runs remain separate. Each chunk
contains 100,000 consecutive samples; chunks are descriptive, not independent
experimental repeats. Single-point controls use p5–p95 bars, other curves bands;
these are distributions, not confidence intervals. Visually inspected the three
comparison images and the revised Artemisia single-point bars.

Validation passed for all 153 million-sample distributions: completion markers,
configuration lists, byte/sample counts, zero-free workload durations, CPU,
matching source/binary hashes, seed 592, 8-byte spacing, 4,096 loads/batch, units,
and ordered percentiles. `test_diagnostic_analysis.py` passed known-value tests
for signed changes, median spread, footprint matching, and zero-baseline rejection.
Syntax checks, final output row-count checks, and all findings artifact links
passed. Existing raw durations and outliers were untouched; no pooling or empty
overhead subtraction occurred. Used the existing temporary analysis environment.

Results remain inconsistent. Charnwood's 4 MiB repeat medians were
128.734/120.167/111.270 TSC ticks/access (15.7% spread relative to the minimum).
Its first 2 MiB run changed from approximately 88 ticks/access in the first eight
chunks to 55 in the final two; sibling CPU 6 averaged 23.05% busy over that
whole repeat, versus 3.05%/2.67% for repeats 2/3. This is not a point-aligned
causal measurement, and the unpinned driver may contribute to activity.

Crux's 256 KiB medians were 8.248/8.120/11.894 (46.5% spread), despite stable
chunks within each of those distributions. Its 6 MiB spread was 35.4%; all new
4–8 MiB median curves rise monotonically, but magnitudes remain inconsistent.

Artemisia's 2 MiB medians were 30.290/28.603/16.105 (88.1% spread): the old dip
returned in repeat 3, not consistently across repeats. Its 32 KiB control spread
was under 0.01%. Sibling CPU 61 whole-repeat busy averages were 2.36%, 5.74%,
and 18.68%. These observations argue against a single uniform timing multiplier
but do not identify the cause of the dip or attribute interference.

Expanded `CAPACITY_FINDINGS.md` with linked artifacts, exact reproduction commands,
results and limitations. No final middle/large capacity or cache hierarchy was
claimed. Before more interference-focused experiments, the recommendation is
quiet-hour reservation coordination, not indefinite repeats of this unchanged
plan. No reservation, TA message, further experiment, PMU/cache-spec lookup,
Hazel execution, Git commit, or Phase-I freeze occurred. This analysis step is
complete; remaining experimental and report requirements are still open.
