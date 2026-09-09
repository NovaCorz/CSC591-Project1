# Independent-load diagnostic: prospective plan

This supplement closes the missing diagnostic in specification §8.2 (page 14),
also requested in §11. It does not change prior cache inferences or use cache
discovery, PMUs, or published cache answers.

Use the same 1 KiB, 128-node randomized pointer ring in both kernels. One kernel
executes four serialized loads per loop iteration; the other executes one load
from each of four independent registers, initialized one quarter-ring apart.
The four chains are mutually independent, while each chain remains internally
dependent. Both traverse the same addresses, use the same total load count, and
execute one loop branch per four loads. Full batches start at 4,096 loads and
contain complete traversals in both kernels. The footprint is a hot-working-set
diagnostic, not a new measurement of any physical cache size or hit latency.

Retain the original serialized TSC/CNTVCT timers and compile with GCC at -O0.
Inspect native disassembly for four dependent loads using one register versus
four loads using distinct registers; inspect loop bodies for stack traffic.
Runtime checks verify one iteration and full-cycle pointer identities. Warm the
selected kernel for at least 100 ms before recording samples. Wrapper and timer
costs are retained, not subtracted. Timer and empty-loop controls are separate.

Every full configuration has 1,000,000 intervals, including controls. Require a
clean same-core calibration cohort and timer median <=5% of the faster kernel's
batch median. Double the common batch only if a clean calibration fails that
fraction, through 32,768 loads; preserve all calibration attempts. Smoke uses
2,048 intervals per mode and is excluded from conclusions.

Use three fixed seeds, each in both execution orders (one then four streams;
four then one). A pair qualifies only when both runs are clean, on the same
logical CPU, with matching ring hashes. Retry both arms up to three times, taking
the first qualifying pair regardless of effect. A core becoming busy may cause
reselection; a resulting mismatched pair is retained and cannot establish a
matched comparison. Use the existing two one-second <=5% idle windows for the
physical core and all SMT siblings. Wait and recheck if none is idle. Existing
context-switch, SMT-activity, affinity, major-fault, timer-resolution and block
drift flags remain in force.

Report all six qualified pair ratios (dependent median / independent median),
their median and range by host, per-configuration full descriptive statistics,
and combined distribution plots. Do not treat million correlated intervals as
independent repetitions. Fewer than six qualified pairs must be stated. Faster
independent timing demonstrates overlap/throughput under this construction;
it is not an alternative hit-latency estimate or a physical port-count inference.
Reset pointers per interval and function argument/return overhead are limitations.

The new round lives in `machines/<host>/independent-load-v1/`. Source-digest
directories, native builds, command logs, environments, idle evidence, all raw
intervals, unsuccessful runs and selection reasons remain auditable. Re-running
the controller resumes integrity-checked clean records; unresolved attempts are
preserved. No reservations are assumed.

## Calibration repair and reproduction

Charnwood's ordinary calibration attempts were blocked by noise or core changes.
The explicitly recorded repair waits for 20 consecutive one-second idle windows,
then acquires fresh cohorts with a generation identifier, retaining the original
three-attempt policy. This prevents reusing individually clean calibration arms
from different acquisition times/cores. Each repair saves the previous gate,
driver source/hash, policy and all quiet-window evidence. This is a quality repair,
not a choice based on the size or direction of a timing difference.

From a working copy of the toolkit with SSH credentials and trusted host keys in
`access/known_hosts`:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
python3 scripts/independent_load.py access
python3 scripts/independent_load.py smoke
python3 scripts/independent_load.py full
# Only if calibration remains blocked by quality/core mismatch:
python3 scripts/independent_load.py repair --hosts charnwood
python3 scripts/analyze_independent.py
python3 scripts/plot_independent.py
```

The plotter requires Matplotlib (the checked environment uses 3.9.4). Acquisition,
raw verification and archive restoration use the Python standard library. SSH
uses the site's authentication configuration; no password is stored in the code.
The full raw supplement is `artifacts/phase1-independent-load.zip`; the archive
size/hash and member readback check are in
`data_processed/independent-load/archive-manifest.json`. Restore into a separate,
new directory to avoid modifying the curated repository:

```bash
python3 scripts/restore_independent.py --archive /path/to/phase1-independent-load.zip \
  --manifest data_processed/independent-load/archive-manifest.json \
  --workspace /absolute/canonical/path/to/new-workspace
```
