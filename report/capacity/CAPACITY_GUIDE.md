# First experiment: timing-only cache levels and capacity

This implements the five steps we discussed, covering the first capacity/hierarchy
experiment in Section 8.2 (pages 13–15). It is **not yet the complete project suite**:
line size, associativity, controlled hit/miss latency, inclusion, the software-only
metric, PMU verification, and frozen predictions come later.

Use `cache_capacity.c` for measurements and `capacity.py` for collection and plots.
`test_capacity.py` is a short runnable correctness check, not experimental evidence.
The code contains both x86-64 and AArch64 timing/load paths. Read those paths before
using them; include the final main code in your report body as required by the spec.

## 1. Choose a lab host, record topology, and choose a CPU

Do this on an ECE lab machine. For example, from your own terminal:

```bash
ssh YOUR_UNITY_ID@sunbird.ece.ncsu.edu
```

If this project directory is on the shared drive, change to it on the remote host:

```bash
cd /mnt/ncsudrive/h/hlee58/ECE592_proj1
hostname
uname -a
grep -m1 -E 'model name|Hardware|Processor' /proc/cpuinfo
lscpu -e=CPU,CORE,SOCKET,NODE
taskset -pc $$
```

These commands identify the machine and topology without requesting cache fields.
Do not use plain `lscpu`, cache sysfs entries, CPU cache tables, or `perf` in Phase I.
Do not run this experiment on Hazel yet, including its compute nodes; its cache
experiments must wait until the lab-only prediction is frozen. Never benchmark on
a Hazel login node.

Choose a logical CPU from the allowed set. The `CPU` column is the logical CPU ID;
rows with the same `SOCKET` and `CORE` are SMT siblings. Check the reservation sheet
and current activity, coordinate with your teammate, and record whether the sibling
was idle, busy, or unknown. A reservation is useful if interference causes noise.

The examples below use CPU 4. **Replace 4 with your selected allowed logical CPU.**
The benchmark refuses to run unless pinned to exactly one logical CPU. Allocation
and initialization happen after pinning so first-touch placement favors local
memory under the normal OS memory policy. Record any existing NUMA policy or
container restrictions; first-touch does not override an imposed policy.

Also save/commit your two hypotheses and ensure your team GitHub and Overleaf
projects are shared as required. This directory currently has no usable Git
repository; use your team's actual clone for the reproducible commit history.

## 2. Compile and understand the pointer chase

Build separately on each host/ISA; do not run an x86 binary on Thunderbird.
Using a host-specific executable name avoids collisions on the shared drive.

```bash
gcc --version
gcc -O0 -g -std=c11 -Wall -Wextra -fno-omit-frame-pointer \
    -o cache_capacity.sunbird cache_capacity.c
```

Change the executable suffix when you change hosts. Keep `-O0`; do not add LTO or
replace the required baseline with an optimized build.

For a footprint W, `make_cycle` places a pointer every `spacing` bytes, shuffles
the node order with the recorded seed, then links the last node to the first:

```text
memory positions:    A    B    C    D    E
random cycle:        A -> D -> B -> E -> C -> A
timed operation:     p = *p;  (the loaded value is the next address)
```

Sequential mode links adjacent nodes in address order. Both modes touch the same
nodes, use the same footprint and load count, and differ only in traversal order.
The program checks that the chain visits all nodes before returning to the start.

The default 8-byte spacing packs pointers on these 64-bit architectures; **it is
not an assumed cache-line size**. Leave it at 8 for this first capacity sweep.
If you change spacing, remember that sparsely touched addresses can span more
bytes than the cache data they occupy. Do not infer line size from this sweep.

## 3. Validate the timer and inspect the loop

```bash
objdump -d --disassemble=chase ./cache_capacity.sunbird
objdump -d --disassemble=timer_start ./cache_capacity.sunbird
objdump -d --disassemble=timer_stop ./cache_capacity.sunbird
objdump -d --disassemble=main ./cache_capacity.sunbird
python3 test_capacity.py
```

In the x86 loop, identify the three-instruction sequence equivalent to:

```asm
mov (%rdx), %rdx
dec %rax
jnz ...
```

Register names can differ. The loaded pointer must replace the register used as
the next address. On Arm, look for `ldr`, `subs`, and `b.ne`. There should be no
stores **inside the repeated load loop**. Function setup/return can use the stack.
In `main`, verify that the calls to the start and stop timers surround `chase`.

The small explicit assembly loop prevents `-O0` from inserting pointer/counter
stack accesses on every iteration. It still has branch and function-call overhead;
this is measured dependent-traversal cost, not a magically isolated load latency.
Save the disassembly excerpts with your experiment notes.

The timing paths follow Section 6's starter methodology:

- x86: fenced `RDTSC`/`RDTSCP`, reported as **TSC ticks/access**, not core cycles.
- Arm: barrier-ordered `CNTVCT_EL0`, reported as **Arm counter ticks/access**.
  `CNTFRQ_EL0` is recorded. If that frequency is trustworthy, convert using
  `ns/access = ticks/access * 1e9 / timer_hz`.

If the architectural timer is unavailable (for example, an Arm counter read traps),
stop and document the error. This version deliberately has no silent fallback;
an alternative unprivileged timer must be chosen and validated on that host.

Run a small pilot to verify collection and estimate runtime:

```bash
python3 capacity.py run \
    --cpu 4 --binary ./cache_capacity.sunbird \
    --out results/sunbird-pilot \
    --pilot --samples 1000 --steps 256 \
    --sizes-kib 4 16 256 4096 \
    --build-command 'gcc -O0 -g -std=c11 -Wall -Wextra -fno-omit-frame-pointer -o cache_capacity.sunbird cache_capacity.c' \
    --notes 'REPLACE: reservation/time, SMT sibling activity, NUMA policy, interference'
```

Replace the notes with actual observations. Pilot samples and plot labels are
explicitly marked; they do not meet the assignment's final sample requirement.
Every output directory must be new, preventing accidental replacement of old data.
An interrupted run retains partial files but has no `COMPLETE` marker. Investigate
the failure, then rerun into a new directory.

The runner measures an empty timer pair, then shuffles the size/mode job order
with the recorded seed. Each non-empty sample is:

```text
start timer -> N dependent loads -> stop timer
raw batch ticks = stop - start
ticks/access = raw batch ticks / N
```

It warms the chain before sampling and carries the current pointer between batches.
It stores batch timings in memory, then writes the raw file after the measurement
loop; no disk writes occur inside that loop. Output-buffer stores between batches
can still disturb cache state. Inspect sensitivity to batch length, especially
near small-cache boundaries. Samples within a run may also be correlated; a million
samples is not a substitute for independent reruns with different seeds/times.

Check batch-length sensitivity by repeating the pilot into separate directories
with `--steps 1024` and `--steps 4096`. Prefer a batch length where the empty-pair
cost divided by N is small compared with measured ticks/access, timer quantization
is small, and the curve is stable as N increases. The empty control characterizes
timer overhead only; it does not remove loop/call overhead. No overhead value is
automatically subtracted.

## 4. Collect the coarse capacity sweep

After choosing a suitable batch length, collect full distributions:

```bash
python3 capacity.py run \
    --cpu 4 --binary ./cache_capacity.sunbird \
    --out results/sunbird-coarse \
    --samples 1000000 --steps 256 --seed 592 \
    --build-command 'gcc -O0 -g -std=c11 -Wall -Wextra -fno-omit-frame-pointer -o cache_capacity.sunbird cache_capacity.c' \
    --notes 'REPLACE with actual run conditions'
```

Replace `256` with the validated batch length if necessary. Default sizes are
powers of two from 4 KiB through 256 MiB. These are exploratory sweep limits,
not claims about any machine's cache sizes. Extend the range if it does not show
the smallest resident regime or reach a stable regime beyond the final cache
transition. Check your allocation and shared-machine memory limits first.

Each size gets both random and sequential traversals with **1,000,000 timed
batches each**. At N=256 this is 256 million dependent loads per size per mode,
plus warm-up. The full sweep can take substantial time, especially at large sizes;
estimate it from the pilot rather than assuming it fits a one-hour reservation.

Raw storage is 8 bytes/sample: about 8 MB per point, or 280 MB for the default
34 traversal points plus one empty control. Each benchmark process also needs the
footprint and a temporary shuffle array (roughly another footprint at spacing 8).
The shuffle array is freed before timing. The sample buffer adds another 8 MB.

Keep these outputs:

| File | Meaning |
| --- | --- |
| `environment.json` | Host, CPU identity/topology, compiler/build command, Git status/commit, source/binary hashes, settings, notes |
| `random_4KiB.json` | Point parameters, timer unit/frequency, warm-up, byte order, invocation |
| `random_4KiB.bin` | Native-endian unsigned 64-bit batch durations; JSON records byte order |
| `sequential_4KiB.*` | Regular-access control for the same footprint |
| `empty_4KiB.*` | Empty timer-pair distribution, in ticks/pair |
| `*.stderr` | Benchmark diagnostics |
| `COMPLETE` | Written only after every point succeeds |

The runner queries only identity/topology and software versions, never PMU/cache
specifications. It records Git failures instead of inventing a commit; fix your
repository setup before collecting final report evidence.

## 5. Plot, inspect, and refine

Plotting requires NumPy and Matplotlib. Collection requires only Python's standard
library. You can plot on your own computer after copying the results there. If
these packages are not installed, create a virtual environment on that computer
or an appropriate lab host:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install numpy matplotlib
python capacity.py plot results/sunbird-pilot
python capacity.py plot results/sunbird-coarse
```

This creates vector `capacity.pdf`, `boxes.pdf`, and `summary.csv`. The CSV contains
mean, median, sample standard deviation, Q1/Q3, 5th/95th percentiles, sample count,
zero count, and outlier count. Outliers use the Tukey rule: outside
`[Q1 - 1.5*IQR, Q3 + 1.5*IQR]`. They are retained in raw data and all statistics;
only individual flier dots are omitted from box plots. Whiskers span the most
extreme inlier values. There are no background grid lines.

The distributions describe **batch-average ticks/access**, not individually timed
loads. State this in captions; a batch average cannot reveal every individual
hit/miss mode. No plot automatically assigns cache labels or guesses capacities.

Read the plots in this order:

1. Find repeatable plateaus and upward transitions in the randomized curve.
2. Check whether sequential traversal stays faster at larger footprints. That is
   evidence consistent with prefetching, not proof of a larger cache.
3. Inspect box plots and tails around transitions. Repeat noisy points with another
   seed and check placement, interference, and batch-length sensitivity.
4. Add dense sizes just below, near, and above a candidate boundary, each with
   the full sample requirement. Use a new output directory.

For example, **only if your own coarse data locate a transition somewhere between
128 and 256 KiB**, refine that interval using:

```bash
python3 capacity.py run \
    --cpu 4 --binary ./cache_capacity.sunbird \
    --out results/sunbird-refine \
    --samples 1000000 --steps 256 --seed 593 \
    --sizes-kib 128 144 160 176 192 208 224 240 256 \
    --build-command 'gcc -O0 -g -std=c11 -Wall -Wextra -fno-omit-frame-pointer -o cache_capacity.sunbird cache_capacity.c' \
    --notes 'REPLACE with actual run conditions and reason for selected interval'
python capacity.py plot results/sunbird-refine
```

These numbers illustrate refinement, not an expected cache boundary. Refine further
if needed and include representative below/near/above box plots for every claimed
boundary. Random traversal can expose TLB/page-walk effects as well as caches;
do not label every jump a new cache level. Record page size, repeat across seeds
and footprints, and treat ambiguous boundaries as provisional until supported
by the later independent geometry/latency experiments.

Your first deliverable is one machine's capacity plot, distributions, recorded
method, and a short explanation of candidate boundaries and uncertainty. Then
repeat the validated method across all eight ECE machines, compiling the native
binary on each. Add the access-pattern diagram and primary contributor below
each report figure/table. Record this AI assistance in the required appendix.

Do **not** freeze all of Phase I after this experiment alone: first complete the
other timing-only properties in Section 8.2, then commit/tag the full Phase-I
results before PMU/specification verification. The lab-based prediction freeze
is a separate later checkpoint before Hazel cache testing.
